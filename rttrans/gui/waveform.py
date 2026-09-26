"""Live input waveform visualizer (QPainter, no extra deps)."""
from __future__ import annotations

from collections import deque

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from . import theme


class WaveformWidget(QWidget):
    """Scrolling waveform built from 'level' events (64-bin envelopes)."""

    BINS = 640  # ~10s history at 10 events/s

    def __init__(self, parent=None):
        super().__init__(parent)
        self._amps: deque[float] = deque([0.0] * self.BINS, maxlen=self.BINS)
        self._active = False
        self.setMinimumHeight(64)
        self.setMaximumHeight(64)

    def push(self, wave: list[float]) -> None:
        if wave:
            self._amps.extend(min(1.0, float(v) * 2.2) for v in wave)
            self.update()

    def set_active(self, speaking: bool) -> None:
        if speaking != self._active:
            self._active = speaking
            self.update()

    def clear(self) -> None:
        self._amps = deque([0.0] * self.BINS, maxlen=self.BINS)
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        mid = h / 2

        # frame
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.setBrush(QColor(theme.BG_INPUT))
        p.drawRoundedRect(0, 0, w - 1, h - 1, 8, 8)

        # center line
        p.setPen(QPen(QColor(46, 49, 64), 1))
        p.drawLine(8, int(mid), w - 8, int(mid))

        amps = list(self._amps)
        n = len(amps)
        usable = w - 16
        step = usable / n

        base = QColor(theme.ACCENT) if self._active else QColor(theme.TEXT_DIM)
        grad = QLinearGradient(0, 0, 0, h)
        c1 = QColor(base)
        c1.setAlpha(230)
        c2 = QColor(base)
        c2.setAlpha(40)
        grad.setColorAt(0.0, c1)
        grad.setColorAt(0.5, c2)
        grad.setColorAt(1.0, c1)

        path = QPainterPath()
        path.moveTo(8, mid)
        for i, a in enumerate(amps):
            x = 8 + i * step
            path.lineTo(x, mid - a * (mid - 6))
        for i in range(n - 1, -1, -1):
            x = 8 + i * step
            path.lineTo(x, mid + amps[i] * (mid - 6))
        path.closeSubpath()
        p.fillPath(path, grad)

        if self._active:
            # right edge "live" dot
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.OK))
            p.drawEllipse(int(w - 14), 6, 6, 6)
        p.end()
