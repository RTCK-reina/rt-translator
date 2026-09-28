"""Chat-style transcript view: one styled card per segment."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QHBoxLayout,
                               QLabel, QScrollArea, QVBoxLayout, QWidget)

from . import theme

MAX_CARDS = 150

_LANG_COLORS = {
    "ja": "#9d8fff", "en": "#4fc3f7", "zh": "#ff7f7f", "ko": "#ffd54f",
    "de": "#90caf9", "fr": "#ce93d8", "es": "#ffab91", "pt": "#80cbc4",
    "ru": "#a5d6a7", "it": "#fff59d", "vi": "#ffcc80", "th": "#b39ddb",
    "id": "#80deea", "ar": "#bcaaa4",
}
_FALLBACK = ["#7f9fff", "#5fd0a5", "#f6a5c0", "#f6cf8d", "#8fd0f6", "#c5a5f6"]


def lang_color(code: str) -> str:
    c = _LANG_COLORS.get(code)
    if c:
        return c
    # stable pick (python hash() is randomized per process)
    h = sum(ord(ch) * 31 ** i for i, ch in enumerate(code))
    return _FALLBACK[h % len(_FALLBACK)]


def _pill(text: str, bg: str, fg: str = "#14151b") -> QLabel:
    lab = QLabel(text)
    lab.setStyleSheet(
        f"background: {bg}; color: {fg}; border-radius: 8px;"
        "padding: 1px 8px; font-size: 11px; font-weight: 700;")
    lab.setFixedHeight(18)
    return lab


def fmt_time(t: float) -> str:
    m, s = divmod(int(t), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


class SegmentCard(QFrame):
    """One segment: lang badge + speaker + time / original / translation."""

    def __init__(self, s: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setStyleSheet(
            f"#card {{ background: {theme.BG_PANEL};"
            f"border: 1px solid {theme.BORDER}; border-radius: 10px; }}")

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 8, 12, 8)
        v.setSpacing(4)

        head = QHBoxLayout()
        head.setSpacing(6)
        head.addWidget(_pill(s.get("lang_name") or s["lang"],
                             lang_color(s["lang"])))
        sp = s.get("speaker")
        if sp:
            head.addWidget(_pill(sp, "#3a3e52", "#dfe3f0"))
        ts = QLabel(fmt_time(s["start"]))
        ts.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 11px;")
        head.addWidget(ts)
        head.addStretch(1)
        v.addLayout(head)

        orig = QLabel(s["text"])
        orig.setWordWrap(True)
        orig.setTextInteractionFlags(Qt.TextSelectableByMouse)
        orig.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 12px;")
        v.addWidget(orig)

        tr = s.get("translation")
        if tr:
            lab = QLabel(tr)
            lab.setWordWrap(True)
            lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lab.setStyleSheet(
                f"color: #ffffff; font-size: 14px; font-weight: 600;")
            v.addWidget(lab)


class TranscriptView(QScrollArea):
    """Vertically stacked cards, auto-scrolls to newest."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self._body = QWidget()
        self._lay = QVBoxLayout(self._body)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(8)
        self._lay.addStretch(1)
        self.setWidget(self._body)
        self._anims: list[QPropertyAnimation] = []
        self._last_max = 0
        # レイアウト反映は非同期（かつスクロールバー出現時の幅変更で
        # 複数回流れてくる）ため、追加直後に maximum() を読んでも古い。
        # 範囲が実際に更新された時点で「直前まで最下部にいたか」を見て追従する。
        self.verticalScrollBar().rangeChanged.connect(self._on_range_changed)

    def add_segment(self, s: dict) -> None:
        card = SegmentCard(s)
        self._lay.insertWidget(self._lay.count() - 1, card)
        self._fade_in(card)
        self._trim()

    def clear(self) -> None:
        while self._lay.count() > 1:
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _fade_in(self, w: QWidget) -> None:
        eff = QGraphicsOpacityEffect(w)
        w.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", w)
        anim.setDuration(220)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(lambda: (w.setGraphicsEffect(None),
                                       self._anims.remove(anim)))
        self._anims.append(anim)
        anim.start()

    def _trim(self) -> None:
        # keep last stretch item; remove oldest cards beyond cap
        while self._lay.count() - 1 > MAX_CARDS:
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_range_changed(self, _minimum: int, maximum: int) -> None:
        sb = self.verticalScrollBar()
        if sb.value() >= self._last_max - 8:
            sb.setValue(maximum)
        self._last_max = maximum
