"""Always-on-top subtitle overlay for gaming / fullscreen use.

Frameless, translucent, draggable. Optional mouse click-through via Win32
(WS_EX_TRANSPARENT) so it never interferes with the game.
"""
from __future__ import annotations

import ctypes
from collections import deque

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (QFrame, QGraphicsDropShadowEffect,
                               QGraphicsOpacityEffect, QHBoxLayout, QLabel,
                               QVBoxLayout, QWidget)

from ..config import OverlayConfig
from ..langs import lang_name
from . import theme
from .transcript import lang_color

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020


def _fade_in(w: QWidget, ms: int = 180) -> None:
    eff = QGraphicsOpacityEffect(w)
    w.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b"opacity", w)
    anim.setDuration(ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.finished.connect(lambda: w.setGraphicsEffect(None))
    w._fade_anim = anim  # keep alive
    anim.start()


def _pill(text: str, bg: str, fg: str = "#14151b") -> QLabel:
    lab = QLabel(text)
    lab.setStyleSheet(
        f"background: {bg}; color: {fg}; border-radius: 8px;"
        "padding: 0px 7px; font-size: 11px; font-weight: 700;")
    lab.setFixedHeight(17)
    return lab


class _Line(QWidget):
    """One subtitle entry: pill-tagged original + bold translation."""

    def __init__(self, cfg: OverlayConfig, lang: str, speaker: str,
                 original: str, translation: str | None):
        super().__init__()
        self.setAttribute(Qt.WA_StyledBackground, False)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(1)

        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(5)
        h.addWidget(_pill(lang_name(lang), lang_color(lang)))
        if speaker:
            h.addWidget(_pill(speaker, "#3a3e52", "#dfe3f0"))
        self.orig = QLabel(original)
        self.orig.setObjectName("o")
        self.orig.setWordWrap(True)
        h.addWidget(self.orig, 1)
        v.addWidget(row)

        self.tr: QLabel | None = None
        if translation:
            self.tr = QLabel(translation)
            self.tr.setObjectName("t")
            self.tr.setWordWrap(True)
            v.addWidget(self.tr)
        if not cfg.show_original:
            row.hide()
        self._orig_row = row
        self._style(cfg)

    def _style(self, cfg: OverlayConfig) -> None:
        fs = cfg.font_size
        self.orig.setStyleSheet(
            f"color: #b8bccd; font-size: {max(10, fs - 8)}px;"
            "background: transparent;")
        if self.tr is not None:
            self.tr.setStyleSheet(
                f"color: #ffffff; font-size: {fs}px; font-weight: 700;"
                "background: transparent;")

    def apply_cfg(self, cfg: OverlayConfig) -> None:
        self._orig_row.setVisible(cfg.show_original or self.tr is None)
        self._style(cfg)


class OverlayWindow(QWidget):
    def __init__(self, cfg: OverlayConfig):
        super().__init__()
        self.cfg = cfg
        self._drag_pos: QPoint | None = None
        self._lines: deque[_Line] = deque()
        self._interim: QLabel | None = None

        flags = (Qt.FramelessWindowHint | Qt.Tool
                 | (Qt.WindowStaysOnTopHint if cfg.always_on_top else 0))
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        if cfg.click_through:
            self.setAttribute(Qt.WA_TransparentForMouseEvents)

        self._frame = QFrame(self)
        self._frame.setObjectName("ov")
        self._layout = QVBoxLayout(self._frame)
        self._layout.setContentsMargins(16, 10, 16, 10)
        self._layout.setSpacing(6)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)  # room for the drop shadow
        outer.addWidget(self._frame)
        self.resize(760, 120)
        self._apply_style()
        self._apply_click_through()

    # ---------------- styling ----------------

    def _apply_style(self) -> None:
        a = self.cfg.bg_opacity
        self._frame.setStyleSheet(
            f"#ov {{ background: rgba(16,17,23,{a});"
            " border: 1px solid rgba(255,255,255,22);"
            " border-radius: 14px; }}")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 4)
        shadow.setColor(Qt.black)
        self._frame.setGraphicsEffect(shadow)
        for line in self._lines:
            line.apply_cfg(self.cfg)
        if self._interim is not None:
            self._interim.setStyleSheet(self._interim_style())

    def _interim_style(self) -> str:
        return (
            f"color: {theme.ACCENT}; font-style: italic;"
            f"font-size: {max(10, self.cfg.font_size - 6)}px;"
            "background: transparent;")

    def _apply_click_through(self) -> None:
        hwnd = int(self.winId())
        if not hwnd:
            return
        ex = ctypes.windll.user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        ex |= WS_EX_LAYERED
        if self.cfg.click_through:
            ex |= WS_EX_TRANSPARENT
        else:
            ex &= ~WS_EX_TRANSPARENT
        ctypes.windll.user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)

    def update_config(self, cfg: OverlayConfig) -> None:
        self.cfg = cfg
        flags = (Qt.FramelessWindowHint | Qt.Tool
                 | (Qt.WindowStaysOnTopHint if cfg.always_on_top else 0))
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, cfg.click_through)
        self._apply_style()
        self._apply_click_through()
        self.show()

    # ---------------- content ----------------

    def add_line(self, lang: str, speaker: str, original: str,
                 translation: str | None, action: str) -> None:
        line = _Line(self.cfg, lang, speaker, original, translation)
        self._layout.addWidget(line)
        self._lines.append(line)
        if self._interim is not None:
            # interim 行が残っている場合は末尾へ差し戻す（確定行の下に来ないよう）
            self._layout.removeWidget(self._interim)
            self._layout.addWidget(self._interim)
        _fade_in(line)
        self._trim()

    def add_interim(self, text: str) -> None:
        """Interim text replaces the previous interim line."""
        lab = self._interim
        if lab is None:
            lab = QLabel()
            lab.setWordWrap(True)
            lab.setStyleSheet(self._interim_style())
            self._layout.addWidget(lab)
            self._interim = lab
            _fade_in(lab, 120)
        lab.setText(f"… {text}")

    def clear_interim(self) -> None:
        lab = getattr(self, "_interim", None)
        if lab is not None:
            self._layout.removeWidget(lab)
            lab.deleteLater()
            self._interim = None

    def _trim(self) -> None:
        while len(self._lines) > self.cfg.max_lines:
            line = self._lines.popleft()
            self._layout.removeWidget(line)
            line.deleteLater()

    def clear(self) -> None:
        while self._lines:
            line = self._lines.popleft()
            self._layout.removeWidget(line)
            line.deleteLater()
        self.clear_interim()

    # ---------------- drag ----------------

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if self._drag_pos is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        self._drag_pos = None
