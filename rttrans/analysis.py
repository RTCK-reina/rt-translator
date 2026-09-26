"""Offline analysis for recordings: re-transcribe, diarize, summarize, export."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import numpy as np
import soundfile as sf

from .config import Config
from .langs import lang_name, normalize
from .speakers import diarize_offline
from .stt import SttEngine
from .store import Recording, Store
from .summary import (extractive_summary, keywords, maybe_llm_summary,
                      speaker_stats, split_sentences)
from .translator import NllbTranslator

ProgressCb = Callable[[str, float], None]


def load_audio_16k(path: str) -> np.ndarray:
    audio, sr = sf.read(path, dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    if sr != 16000:
        import soxr
        audio = soxr.resample(audio, sr, 16000)
    return np.ascontiguousarray(audio, dtype=np.float32)


def retranscribe(rec: Recording, cfg: Config, store: Store,
                 model_name: str, compute_type: str,
                 translate_missing: bool = True,
                 progress: ProgressCb | None = None) -> int:
    """Re-run whisper on the recording; replaces stored segments.

    VAD-segments the file first so transcription never splits mid-sentence.
    """
    from .vad import VadSegmenter

    audio = load_audio_16k(rec.path)
    eng = SttEngine(model_name, device="cuda", compute_type=compute_type)
    try:
        eng.load()

        # 1) VAD the whole file -> speech regions, merged into <=25 s blocks
        vad = VadSegmenter(threshold=0.5, min_silence_ms=500, pad_ms=150,
                           min_speech_ms=200, max_speech_s=25.0)
        regions: list[tuple[int, int]] = []
        blk = 25 * 16000
        for i in range(0, len(audio), blk):
            for seg in vad.feed(audio[i:i + blk]):
                regions.append((seg.start, seg.end))
        tail = vad.flush()
        if tail is not None:
            regions.append((tail.start, tail.end))

        # merge adjacent regions into blocks <= 25 s (gap < 3 s)
        blocks: list[tuple[int, int]] = []
        for a, b in regions:
            if (blocks and a - blocks[-1][1] < 3 * 16000
                    and b - blocks[-1][0] <= blk):
                blocks[-1] = (blocks[-1][0], b)
            else:
                blocks.append((a, b))
        if not blocks:
            blocks = [(0, len(audio))]

        # 2) transcribe each block
        segments: list[dict] = []
        for bi, (a, b) in enumerate(blocks):
            chunk = audio[a:b]
            results = eng.transcribe(chunk, beam_size=5)
            base = a / 16000.0
            for r in results:
                segments.append({
                    "start": base + r.start, "end": base + r.end,
                    "lang": normalize(r.lang), "speaker": "",
                    "text": r.text, "translation": None, "prob": r.avg_logprob,
                })
            if progress:
                progress("文字起こし", (bi + 1) / len(blocks) * 0.9)
    finally:
        eng.unload()  # free VRAM for the next operation / gaming

    if translate_missing and cfg.translation_enabled:
        tr = NllbTranslator(cfg.nllb_dir, "cpu", "int8")
        if tr.model_ready():
            tr.load()
            by_lang: dict[str, list[int]] = {}
            for idx, s in enumerate(segments):
                by_lang.setdefault(s["lang"], []).append(idx)
            for lang, idxs in by_lang.items():
                if lang == cfg.target_lang:
                    continue
                texts = [segments[i]["text"] for i in idxs]
                outs = tr.translate_batch(texts, lang, cfg.target_lang)
                for i, t in zip(idxs, outs):
                    segments[i]["translation"] = t

    store.clear_segments(rec.id)
    store.add_segments(rec.id, segments)
    store.set_analyzed(rec.id, True)
    return len(segments)


def diarize(rec: Recording, cfg: Config, store: Store,
            num_speakers: int = -1, cluster_threshold: float = 0.5,
            progress: ProgressCb | None = None) -> int:
    """Offline diarization; assigns speaker labels to stored segments."""
    if not Path(cfg.segmentation_model).exists():
        raise RuntimeError(f"セグメンテーションモデル未導入: {cfg.segmentation_model}")
    if not Path(cfg.speaker_model).exists():
        raise RuntimeError(f"話者埋め込みモデル未導入: {cfg.speaker_model}")

    audio = load_audio_16k(rec.path)
    if progress:
        progress("話者分離", 0.1)
    turns = diarize_offline(audio, cfg.segmentation_model, cfg.speaker_model,
                            num_speakers=num_speakers,
                            cluster_threshold=cluster_threshold)
    if progress:
        progress("話者分離", 0.8)

    segs = store.segments(rec.id)
    updates: list[tuple[int, str]] = []
    for s in segs:
        mid = (s["start"] + s["end"]) / 2.0
        best_sp, best_ov = None, 0.0
        for (a, b, sp) in turns:
            ov = min(b, s["end"]) - max(a, s["start"])
            if ov > best_ov:
                best_ov, best_sp = ov, sp
        if best_sp is None:
            # nearest turn by midpoint distance
            if turns:
                best_sp = min(turns, key=lambda t: abs((t[0] + t[1]) / 2 - mid))[2]
        if best_sp is not None:
            updates.append((s["id"], f"SPEAKER_{best_sp:02d}"))
    store.update_segment_speakers(updates)
    if progress:
        progress("話者分離", 1.0)
    return len(turns)


def analyze(rec: Recording, cfg: Config, store: Store) -> dict:
    """Summary package: extractive summary, keywords, per-speaker stats."""
    segs = store.segments(rec.id)
    full_text = " ".join((s.get("translation") or s.get("text") or "") for s in segs)
    orig_text = " ".join((s.get("text") or "") for s in segs)

    out = {
        "duration_s": rec.duration_s,
        "segment_count": len(segs),
        "summary_extractive": extractive_summary(full_text or orig_text),
        "keywords": keywords(full_text or orig_text),
        "speaker_stats": speaker_stats(segs),
        "lang_dist": _lang_dist(segs),
        "sentences": len(split_sentences(full_text or orig_text)),
    }
    llm = maybe_llm_summary(orig_text, cfg.llm_gguf_path)
    if llm:
        out["summary_llm"] = llm
    return out


def _lang_dist(segs: list[dict]) -> dict:
    d: dict[str, float] = {}
    for s in segs:
        name = lang_name(s.get("lang") or "?")
        d[name] = d.get(name, 0.0) + max(0.0, (s.get("end") or 0) - (s.get("start") or 0))
    return d


# ---------------- export ----------------

def _fmt_ts(t: float, srt: bool = False) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    sep = "," if srt else "."
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def export_recording(rec: Recording, store: Store, fmt: str, out_path: str) -> str:
    segs = store.segments(rec.id)
    p = Path(out_path)
    if fmt == "srt":
        lines = []
        for i, s in enumerate(segs, 1):
            txt = s.get("text") or ""
            if s.get("translation"):
                txt += f"\n{s['translation']}"
            lines.append(f"{i}\n{_fmt_ts(s['start'], True)} --> {_fmt_ts(s['end'], True)}\n{txt}\n")
        p.write_text("\n".join(lines), encoding="utf-8")
    elif fmt == "json":
        p.write_text(json.dumps(
            {"recording": rec.__dict__, "segments": segs},
            ensure_ascii=False, indent=2), encoding="utf-8")
    elif fmt == "md":
        lines = [f"# {rec.name}", f"- 日時: {rec.started_at}",
                 f"- 長さ: {rec.duration_s:.1f}s / {len(segs)} セグメント", ""]
        for s in segs:
            sp = f"[{s['speaker']}]" if s.get("speaker") else ""
            line = f"- `{_fmt_ts(s['start'])}` {sp}({s.get('lang','?')}) {s.get('text','')}"
            if s.get("translation"):
                line += f" → {s['translation']}"
            lines.append(line)
        p.write_text("\n".join(lines), encoding="utf-8")
    else:  # txt
        lines = []
        for s in segs:
            sp = f"[{s['speaker']}]" if s.get("speaker") else ""
            line = f"[{_fmt_ts(s['start'])}] {sp} {s.get('text','')}"
            if s.get("translation"):
                line += f"  →  {s['translation']}"
            lines.append(line)
        p.write_text("\n".join(lines), encoding="utf-8")
    return str(p)
