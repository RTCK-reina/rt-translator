"""Speech-to-text via faster-whisper (CTranslate2, CUDA)."""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass

import numpy as np

# Whisper hallucinations on silence/noise (ja/en common cases).
_HALLUCINATIONS = {
    "ご視聴ありがとうございました", "ご視聴ありがとうございました。",
    "最後までご視聴ありがとうございました", "チャンネル登録をお願いします",
    "チャンネル登録お願いします", "字幕は自動生成です",
    "thank you for watching", "thanks for watching",
    "thank you for watching!", "thanks for watching!",
    "thank you.", "thank you", "bye.", "bye",
    "subtitles by", "字幕作成",
}


@dataclass
class SttResult:
    text: str
    lang: str
    lang_prob: float
    start: float  # seconds, relative to input audio
    end: float
    avg_logprob: float
    no_speech_prob: float


class SttEngine:
    """Lazy-loaded faster-whisper wrapper. One engine per loaded model."""

    def __init__(self, model_name: str, device: str = "cuda", compute_type: str = "int8"):
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self._model = None
        self._lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        from .cudaenv import register_cuda_dlls
        register_cuda_dlls()
        from faster_whisper import WhisperModel

        with self._lock:
            if self._model is None:
                self._model = WhisperModel(
                    self.model_name,
                    device=self.device,
                    compute_type=self.compute_type,
                    cpu_threads=4,
                    num_workers=1,
                )

    def unload(self) -> None:
        with self._lock:
            self._model = None

    def transcribe(self, audio: np.ndarray, beam_size: int = 1,
                   language: str | None = None) -> list[SttResult]:
        assert self._model is not None, "call load() first"
        audio = np.ascontiguousarray(audio, dtype=np.float32)
        with self._lock:
            segments, info = self._model.transcribe(
                audio,
                beam_size=beam_size,
                language=language,
                vad_filter=False,
                word_timestamps=False,
                condition_on_previous_text=False,
                no_speech_threshold=0.6,
                log_prob_threshold=-1.2,
                temperature=0.0,
            )
            out = []
            for s in segments:
                text = (s.text or "").strip()
                if not text:
                    continue
                if _is_hallucination(text, s.no_speech_prob, s.avg_logprob):
                    continue
                out.append(SttResult(
                    text=text,
                    lang=info.language or "unknown",
                    lang_prob=info.language_probability or 0.0,
                    start=s.start, end=s.end,
                    avg_logprob=s.avg_logprob,
                    no_speech_prob=s.no_speech_prob,
                ))
            return out


def _is_hallucination(text: str, no_speech: float, logprob: float) -> bool:
    t = text.strip().lower().rstrip("。.!！?？")
    if t in _HALLUCINATIONS:
        return True
    if no_speech > 0.85 and logprob < -0.7:
        return True
    # repeated single token e.g. "ああああああ" / "AAAA"
    if len(t) >= 6 and len(set(t)) <= 2:
        return True
    if re.fullmatch(r"(.)\1{5,}", t):
        return True
    return False
