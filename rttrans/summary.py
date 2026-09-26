"""Extractive summary + keyword stats.

Works offline, no model downloads. Optional abstractive summary via
llama-cpp-python if the user provides a GGUF path in settings.
"""
from __future__ import annotations

import math
import re
from collections import Counter

_SENT_SPLIT = re.compile(r"(?<=[。！？.!?])\s*|\n+")
_TOKEN = re.compile(r"[A-Za-z0-9]{2,}|[\u4e00-\u9fff\u3040-\u30ff]{2,}")
_STOP_JA = {
    "こと", "もの", "それ", "これ", "ため", "よう", "さん", "です", "ます",
    "ます。", "ない", "ある", "いる", "する", "なる", "できる", "ところ",
    "ちょっと", "やっぱり", "そう", "こう", "どう", "まあ", "なんか",
}
_STOP_EN = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were",
    "to", "of", "in", "on", "for", "with", "that", "this", "it", "i",
    "you", "we", "they", "he", "she", "be", "been", "have", "has",
    "do", "does", "did", "not", "no", "so", "if", "at", "by", "as",
    "yeah", "yes", "okay", "ok", "like", "just", "really", "know",
    "think", "right", "going", "gonna", "uh", "um",
}


def split_sentences(text: str) -> list[str]:
    parts = [s.strip() for s in _SENT_SPLIT.split(text) if s and s.strip()]
    return parts


def _tokens(sent: str) -> list[str]:
    return _TOKEN.findall(sent)


def keywords(text: str, top_k: int = 12) -> list[tuple[str, int]]:
    cnt = Counter(t.lower() for t in _tokens(text))
    for w in list(cnt):
        if w in _STOP_EN or w in _STOP_JA or len(w) < 2:
            del cnt[w]
    return cnt.most_common(top_k)


def extractive_summary(text: str, max_sentences: int = 7) -> list[str]:
    """Frequency/position scored sentence selection (ja+en friendly)."""
    sents = split_sentences(text)
    if len(sents) <= max_sentences:
        return sents
    freq = Counter(t.lower() for s in sents for t in _tokens(s))
    for w in _STOP_EN | _STOP_JA:
        freq.pop(w, None)
    if not freq:
        return sents[:max_sentences]
    max_f = max(freq.values())

    scored = []
    for i, s in enumerate(sents):
        toks = [t.lower() for t in _tokens(s)]
        if not toks:
            continue
        score = sum(freq.get(t, 0) / max_f for t in toks) / math.sqrt(len(toks))
        score *= 1.0 + 0.15 * math.exp(-i / (0.2 * len(sents)))  # lead bias
        scored.append((score, i, s))
    top = sorted(scored, key=lambda x: -x[0])[:max_sentences]
    return [s for _, _, s in sorted(top, key=lambda x: x[1])]


def speaker_stats(segments: list[dict]) -> dict:
    """Per-speaker: talk time, segment count, languages, word/char counts."""
    stats: dict[str, dict] = {}
    for s in segments:
        sp = s.get("speaker") or "?"
        d = stats.setdefault(sp, {"time": 0.0, "segments": 0,
                                  "langs": Counter(), "chars": 0})
        d["time"] += max(0.0, (s.get("end") or 0) - (s.get("start") or 0))
        d["segments"] += 1
        d["langs"][s.get("lang") or "?"] += 1
        d["chars"] += len(s.get("text") or "")
    for d in stats.values():
        d["langs"] = dict(d["langs"])
    return stats


def maybe_llm_summary(text: str, gguf_path: str, max_tokens: int = 512) -> str | None:
    """Abstractive summary if llama-cpp-python + GGUF are configured."""
    if not gguf_path:
        return None
    try:
        from llama_cpp import Llama
    except ImportError:
        return None
    try:
        llm = Llama(model_path=gguf_path, n_ctx=8192, n_gpu_layers=-1, verbose=False)
        prompt = (
            "以下の文字起こしを日本語で簡潔に要約してください。"
            "要点を箇条書きで示してください。\n\n"
            f"{text[:12000]}\n\n要約:")
        out = llm(prompt, max_tokens=max_tokens, temperature=0.3)
        return out["choices"][0]["text"].strip()
    except Exception:
        return None
