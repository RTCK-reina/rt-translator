"""Capture thread: device -> mono float32 PCM at 16 kHz.

Uses soundcard (WASAPI). Works for both real microphones and loopback
devices (speaker output capture). Resamples with soxr.
"""
from __future__ import annotations

import queue
import threading
from typing import Callable

import numpy as np
import soxr

TARGET_RATE = 16000


class CaptureThread(threading.Thread):
    """Push 16 kHz mono float32 chunks into `out_q`; optional `on_chunk` tap."""

    def __init__(
        self,
        device_id: str,
        out_q: "queue.Queue[np.ndarray]",
        on_chunk: Callable[[np.ndarray], None] | None = None,
        capture_rate: int = 48000,
        block_ms: int = 100,
    ):
        super().__init__(daemon=True, name="capture")
        self.device_id = device_id
        self.out_q = out_q
        self.on_chunk = on_chunk
        self.capture_rate = capture_rate
        self.block_frames = int(capture_rate * block_ms / 1000)
        self._stop_ev = threading.Event()
        self.error: Exception | None = None

    def stop(self) -> None:
        self._stop_ev.set()

    def run(self) -> None:
        import soundcard as sc

        try:
            mic = sc.get_microphone(self.device_id, include_loopback=True)
            with mic.recorder(samplerate=self.capture_rate) as rec:
                while not self._stop_ev.is_set():
                    data = rec.record(numframes=self.block_frames)
                    if data is None or data.size == 0:
                        continue
                    mono = np.asarray(data, dtype=np.float32)
                    if mono.ndim == 2:
                        mono = mono.mean(axis=1)
                    if self.capture_rate != TARGET_RATE:
                        mono = soxr.resample(mono, self.capture_rate, TARGET_RATE)
                    mono = np.ascontiguousarray(mono, dtype=np.float32)
                    if self.on_chunk is not None:
                        try:
                            self.on_chunk(mono)
                        except Exception:
                            pass
                    try:
                        self.out_q.put_nowait(mono)
                    except queue.Full:
                        pass  # consumer overloaded; drop audio rather than grow latency
        except Exception as e:  # device lost, etc.
            self.error = e
