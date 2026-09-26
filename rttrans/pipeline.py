"""Live pipeline: capture -> VAD -> STT -> lang filter -> translate -> events.

Qt-free; the GUI layer subscribes via `on_event(kind, payload)` and bridges
to Qt signals. Kinds: status, level, speech, interim, segment, error,
recording.
"""
from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from .capture import TARGET_RATE, CaptureThread
from .config import Config
from .langs import ACTION_IGNORE, ACTION_TRANSLATE, lang_name, normalize
from .speakers import OnlineSpeakerTracker, SpeakerEmbedder
from .store import Store, WavWriter, new_recording_path
from .stt import SttEngine
from .translator import NllbTranslator
from .vad import VadSegmenter

EventCb = Callable[[str, dict], None]


@dataclass
class EngineSet:
    """Lazily shared model instances across sessions."""
    stt_engines: dict = None  # (model_name, compute) -> SttEngine
    translator: NllbTranslator | None = None
    embedder: SpeakerEmbedder | None = None

    def __post_init__(self):
        if self.stt_engines is None:
            self.stt_engines = {}


class Pipeline:
    def __init__(self, cfg: Config, store: Store, on_event: EventCb):
        self.cfg = cfg
        self.store = store
        self.on_event = on_event
        self.engines = EngineSet()
        self._cap: CaptureThread | None = None
        self._worker: threading.Thread | None = None
        self._stop = threading.Event()
        self._q: queue.Queue[np.ndarray] = queue.Queue(maxsize=100)
        self._wav: WavWriter | None = None
        self._rec_id: int | None = None
        self._running = False
        self._seg_rows: list[dict] = []

    # ---------------- public API ----------------

    @property
    def running(self) -> bool:
        return self._running

    def start(self, device_id: str, record: bool = False) -> None:
        if self._running:
            return
        preset = self.cfg.preset()
        self._stop.clear()
        self._seg_rows = []

        self._emit("status", {"text": f"モデル読み込み中 ({preset.whisper_model})..."})
        try:
            self._prepare_models()
        except Exception as e:
            self._emit("error", {"text": f"モデル初期化失敗: {e}"})
            return

        # recording arm
        if record:
            Path(self.cfg.record_dir).mkdir(parents=True, exist_ok=True)
            path, name = new_recording_path(self.cfg.record_dir)
            self._wav = WavWriter(path)
            self._rec_id = self.store.create_recording(
                path, name, self.cfg.device_name or device_id, self.cfg.mode)
            self._emit("recording", {"state": "started", "path": path, "id": self._rec_id})

        self._cap = CaptureThread(
            device_id, self._q,
            on_chunk=(self._wav.write if self._wav else None),
            capture_rate=self.cfg.capture_rate,
            block_ms=self.cfg.capture_block_ms,
        )
        self._worker = threading.Thread(
            target=self._run, args=(preset,), daemon=True, name="pipeline-worker")
        self._cap.start()
        self._worker.start()
        self._running = True
        self._emit("status", {"text": f"開始 ({self.cfg.mode}) — {self.cfg.device_name or device_id}"})

    def stop(self) -> None:
        if not self._running:
            return
        self._stop.set()
        if self._cap:
            self._cap.stop()
        if self._worker:
            self._worker.join(timeout=10)
        if self._cap:
            self._cap.join(timeout=5)
        dur = 0.0
        if self._wav:
            dur = self._wav.close()
            self._wav = None
        if self._rec_id is not None:
            if self._seg_rows:
                self.store.add_segments(self._rec_id, self._seg_rows)
            self.store.finish_recording(self._rec_id, dur)
            self._emit("recording", {"state": "stopped", "id": self._rec_id, "duration": dur})
            self._rec_id = None
        self._seg_rows = []
        self._running = False
        self._emit("status", {"text": "停止"})

    # ---------------- internals ----------------

    def _emit(self, kind: str, payload: dict) -> None:
        try:
            self.on_event(kind, payload)
        except Exception:
            pass

    def _prepare_models(self) -> None:
        preset = self.cfg.preset()
        model_ref = self.cfg.whisper_model_path or self.cfg.resolve_whisper(
            preset.whisper_model)
        key = (model_ref, preset.compute_type)
        if key not in self.engines.stt_engines:
            self.engines.stt_engines[key] = SttEngine(
                key[0], device="cuda", compute_type=key[1])
        eng = self.engines.stt_engines[key]
        if not eng.loaded:
            eng.load()
        self._stt = eng

        if self.cfg.translation_enabled:
            if self.engines.translator is None or \
               self.engines.translator.model_dir != self.cfg.nllb_dir:
                dev = "cpu" if self.cfg.mode == "eco" else "cuda"
                ct = "int8" if dev == "cpu" else "int8_float16"
                self.engines.translator = NllbTranslator(self.cfg.nllb_dir, dev, ct)
            tr = self.engines.translator
            if not tr.model_ready():
                raise RuntimeError(
                    f"翻訳モデル未ダウンロード: {self.cfg.nllb_dir}\n"
                    "設定タブの「翻訳モデルをダウンロード」を実行してください")
            if not tr.loaded:
                tr.load()
        else:
            self.engines.translator = None

        self._tracker = None
        if preset.enable_speakers:
            if self.engines.embedder is None or \
               self.engines.embedder.model_path != self.cfg.speaker_model:
                self.engines.embedder = SpeakerEmbedder(self.cfg.speaker_model)
            if self.engines.embedder.available():
                if not self.engines.embedder.loaded:
                    self.engines.embedder.load()
                self._tracker = OnlineSpeakerTracker(
                    self.engines.embedder, self.cfg.speaker_threshold)
            else:
                self._emit("status", {"text": "話者モデル未導入のため話者分離は無効"})

    def _run(self, preset) -> None:
        vad = VadSegmenter(
            threshold=0.5,
            min_silence_ms=preset.vad_silence_ms,
            pad_ms=150,
            max_speech_s=preset.max_segment_s,
        )
        was_speaking = False
        last_interim = 0.0
        t_level = 0.0
        speech_audio: list[np.ndarray] = []  # mirrors vad current speech for interim

        while not self._stop.is_set():
            try:
                chunk = self._q.get(timeout=0.05)
            except queue.Empty:
                chunk = None
            if chunk is None:
                continue

            now = time.monotonic()
            if now - t_level > 0.1:
                rms = float(np.sqrt(np.mean(chunk ** 2) + 1e-12))
                # downsampled abs envelope for the GUI waveform (64 bins)
                nb = 64
                n = chunk.size // nb * nb
                if n >= nb:
                    amps = np.abs(chunk[:n].reshape(-1, nb)).max(axis=0).tolist()
                else:
                    amps = [float(np.abs(chunk).max()) if chunk.size else 0.0] * nb
                self._emit("level", {"rms": min(1.0, rms * 4), "wave": amps})
                t_level = now

            if vad.speaking:
                speech_audio.append(chunk)
            segments = vad.feed(chunk)

            if vad.speaking and not was_speaking:
                speech_audio = [chunk]
                self._emit("speech", {"state": "start"})
            elif not vad.speaking and was_speaking:
                speech_audio = []
                self._emit("speech", {"state": "end"})
            was_speaking = vad.speaking

            # interim transcription while speech continues
            if (preset.interim_results and vad.speaking
                    and now - last_interim > self.cfg.interim_interval_s
                    and vad.speech_elapsed_s > self.cfg.interim_interval_s):
                last_interim = now
                audio = np.concatenate(speech_audio)[-int(16000 * 6):]
                if audio.size > 16000 * 0.5:
                    self._interim(audio)

            if segments:
                speech_audio = []  # emitted audio is done; interim restarts fresh
            for seg in segments:
                self._handle_segment(seg, preset)

        # flush tail
        tail = vad.flush()
        if tail is not None:
            self._handle_segment(tail, preset)

    def _interim(self, audio: np.ndarray) -> None:
        try:
            preset = self.cfg.preset()
            results = self._stt.transcribe(audio, beam_size=1)
            if results:
                text = " ".join(r.text for r in results)
                self._emit("interim", {"text": text, "lang": normalize(results[0].lang)})
        except Exception:
            pass

    def _handle_segment(self, seg, preset) -> None:
        try:
            results = self._stt.transcribe(seg.audio, beam_size=preset.beam_size)
        except Exception as e:
            self._emit("error", {"text": f"STT失敗: {e}"})
            return
        if not results:
            return

        lang = normalize(results[0].lang)
        action = self.cfg.action_for_lang(lang)
        if action == ACTION_IGNORE:
            return

        speaker = ""
        if self._tracker is not None:
            speaker = self._tracker.identify(seg.audio)

        t0, t1 = seg.start / TARGET_RATE, seg.end / TARGET_RATE
        texts = [r.text for r in results]
        translations: list[str | None] = [None] * len(texts)

        if action == ACTION_TRANSLATE and self.cfg.translation_enabled \
                and self.engines.translator is not None:
            tgt = self.cfg.target_lang
            try:
                translations = self.engines.translator.translate_batch(
                    texts, lang, tgt, beam_size=2)
            except Exception as e:
                self._emit("error", {"text": f"翻訳失敗: {e}"})

        for r, tr in zip(results, translations):
            row = {
                "start": t0 + r.start, "end": t0 + r.end,
                "lang": lang, "lang_name": lang_name(lang),
                "speaker": speaker, "text": r.text,
                "translation": tr, "prob": r.avg_logprob,
                "action": action,
            }
            if self._rec_id is not None:
                self._seg_rows.append(row)
            self._emit("segment", row)
