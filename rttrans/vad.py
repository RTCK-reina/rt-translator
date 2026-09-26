"""Silero VAD (ONNX) speech segmenter.

Feed arbitrary float32 16 kHz chunks; get back speech segments as
(audio, start_sample, end_sample) tuples with absolute sample indices.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

WINDOW = 512  # silero requirement @16kHz (32 ms)


def _silero_onnx_path() -> Path:
    """Bundled copy first (exe-safe), else the silero-vad package file.

    Uses find_spec so the silero_vad package (which imports torch) is never
    actually imported at runtime.
    """
    bundled = Path(__file__).resolve().parent / "assets" / "silero_vad.onnx"
    if bundled.exists():
        return bundled
    import importlib.util
    spec = importlib.util.find_spec("silero_vad")
    if spec and spec.submodule_search_locations:
        p = Path(spec.submodule_search_locations[0]) / "data" / "silero_vad.onnx"
        if p.exists():
            return p
    raise FileNotFoundError("silero_vad.onnx not found (rttrans/assets or package)")


@dataclass
class Segment:
    audio: np.ndarray
    start: int  # absolute sample index
    end: int
    forced: bool = False  # cut by max length, not silence


@dataclass
class VadSegmenter:
    threshold: float = 0.5
    min_silence_ms: int = 500
    pad_ms: int = 120
    min_speech_ms: int = 250
    max_speech_s: float = 10.0

    _model: object = field(default=None, init=False, repr=False)
    _pending: np.ndarray = field(default_factory=lambda: np.empty(0, np.float32), init=False)
    _pre: deque = field(default_factory=lambda: deque(maxlen=5), init=False)  # windows before trigger
    _seg_windows: list = field(default_factory=list, init=False)
    _abs_pos: int = field(default=0, init=False)          # absolute idx of next window start
    _triggered: bool = field(default=False, init=False)
    _speech_start: int = field(default=0, init=False)
    _last_speech_end: int = field(default=0, init=False)
    _silence: int = field(default=0, init=False)

    def __post_init__(self):
        # Run the bundled silero ONNX model directly via onnxruntime so the
        # live pipeline never touches torch (keeps the eco mode lean).
        import onnxruntime

        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self._sess = onnxruntime.InferenceSession(
            str(_silero_onnx_path()), providers=["CPUExecutionProvider"],
            sess_options=opts)
        self._reset_state()

    def _reset_state(self) -> None:
        self._state = np.zeros((2, 1, 128), np.float32)
        self._context = np.zeros((1, 64), np.float32)

    @property
    def speaking(self) -> bool:
        return self._triggered

    @property
    def speech_elapsed_s(self) -> float:
        if not self._triggered:
            return 0.0
        return max(0, self._abs_pos - self._speech_start) / 16000.0

    def reset(self) -> None:
        self._pending = np.empty(0, np.float32)
        self._pre.clear()
        self._seg_windows.clear()
        self._triggered = False
        self._silence = 0
        self._reset_state()

    def feed(self, chunk: np.ndarray) -> list[Segment]:
        self._pending = np.concatenate([self._pending, chunk]) if self._pending.size else chunk
        out: list[Segment] = []
        while self._pending.size >= WINDOW:
            win = self._pending[:WINDOW]
            self._pending = self._pending[WINDOW:]
            seg = self._process(win)
            if seg is not None:
                out.append(seg)
        return out

    def flush(self) -> Segment | None:
        if self._triggered:
            return self._emit(self._last_speech_end + self._pad_samples(), forced=True)
        return None

    # ---------------- internals ----------------

    def _pad_samples(self) -> int:
        return int(16000 * self.pad_ms / 1000)

    def _prob(self, win: np.ndarray) -> float:
        x = np.concatenate([self._context, win[None]], axis=1)
        outs = self._sess.run(None, {
            "input": x.astype(np.float32),
            "state": self._state,
            "sr": np.array(16000, dtype=np.int64),
        })
        self._state = outs[1]
        self._context = x[:, -64:]
        return float(outs[0].reshape(-1)[0])

    def _process(self, win: np.ndarray) -> Segment | None:
        w_start = self._abs_pos
        w_end = w_start + WINDOW
        self._abs_pos = w_end
        p = self._prob(win)

        if not self._triggered:
            self._pre.append(win)
            if p >= self.threshold:
                self._triggered = True
                self._speech_start = max(0, w_start - self._pad_samples())
                self._last_speech_end = w_end
                self._seg_windows = list(self._pre) + [win]
                self._pre.clear()
                self._silence = 0
            return None

        # triggered
        self._seg_windows.append(win)
        if p >= self.threshold:
            self._silence = 0
            self._last_speech_end = w_end
        else:
            self._silence += WINDOW

        seg_len_s = (w_end - self._speech_start) / 16000.0
        if self._silence * 1000 // 16000 >= self.min_silence_ms:
            return self._emit(self._last_speech_end + self._pad_samples())
        if seg_len_s >= self.max_speech_s:
            return self._emit(w_end, forced=True)
        return None

    def _emit(self, end_abs: int, forced: bool = False) -> Segment | None:
        audio = np.concatenate(self._seg_windows)
        total = audio.size
        base = self._abs_pos - total  # absolute index of audio[0]
        end_rel = min(total, end_abs - base)
        start_rel = max(0, self._speech_start - base)
        seg_audio = audio[start_rel:end_rel]
        start, end = base + start_rel, base + end_rel

        self._triggered = False
        self._silence = 0
        self._seg_windows = []

        if (end - start) < int(16000 * self.min_speech_ms / 1000):
            return None
        return Segment(seg_audio, start, end, forced)
