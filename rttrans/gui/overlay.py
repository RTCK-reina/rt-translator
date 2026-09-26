"""Always-on-top subtitle overlay for gaming / fullscreen use.

Frameless, translucent, draggable. Optional mouse click-through via Win32
(WS_EX_TRANSPARENT) so it never interferes with the game.
"""
from __future__ import annotations

import ctypes
from collections import deque

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from ..config import OverlayConfig
from ..langs import lang_name

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020


class OverlayWindow(QWidget):
    def __init__(self, cfg: OverlayConfig):
        super().__init__()
        self.cfg = cfg
        self._drag_pos: QPoint | None = None
        self._lines: deque[tuple[QLabel, QLabel | None]] = deque()
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
        self._layout.setContentsMargins(14, 8, 14, 8)
        self._layout.setSpacing(4)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._frame)
        self.resize(760, 120)
        self._apply_style()
        self._apply_click_through()

    # ---------------- styling ----------------

    def _apply_style(self) -> None:
        a = self.cfg.bg_opacity
        self._frame.setStyleSheet(
            f"#ov {{ background: rgba(12,12,16,{a}); border-radius: 10px; }}")
        self._style_lines()

    def _style_lines(self) -> None:
        fs = self.cfg.font_size
        for orig, tr in self._lines:
            orig.setStyleSheet(
                f"color: #b8b8c0; font-size: {max(10, fs - 8)}px; "
                "background: transparent;")
            if tr is not None:
                tr.setStyleSheet(
                    f"color: #ffffff; font-size: {fs}px; font-weight: 600;"
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
        self._reflow()
        self.show()

    # ---------------- content ----------------

    def add_line(self, lang: str, speaker: str, original: str,
                 translation: str | None, action: str) -> None:
        tag = f"[{lang_name(lang)}]"
        if speaker:
            tag += f"[{speaker}]"
        orig = QLabel(f"{tag} {original}")
        orig.setWordWrap(True)
        orig.setTextInteractionFlags(Qt.TextSelectableByMouse)
        tr: QLabel | None = None
        if translation:
            tr = QLabel(translation)
            tr.setWordWrap(True)
            tr.setTextInteractionFlags(Qt.TextSelectableByMouse)
            tr.setStyleSheet(
                f"color: #ffffff; font-size: {self.cfg.font_size}px; "
                "font-weight: 600; background: transparent;")
        if not self.cfg.show_original and tr is not None:
            orig.hide()
        orig.setStyleSheet(
            f"color: #b8b8c0; font-size: {max(10, self.cfg.font_size - 8)}px; "
            "background: transparent;")

        self._layout.addWidget(orig)
        if tr is not None:
            self._layout.addWidget(tr)
        self._lines.append((orig, tr))
        self._trim()

    def add_interim(self, text: str) -> None:
        """Interim text replaces the previous interim line."""
        self.clear_interim()
        lab = QLabel(f"… {text}")
        lab.setWordWrap(True)
        lab.setStyleSheet(
            f"color: #7f9fff; font-size: {max(10, self.cfg.font_size - 6)}px; "
            "background: transparent;")
        self._layout.addWidget(lab)
        self._interim = lab

    def clear_interim(self) -> None:
        lab = getattr(self, "_interim", None)
        if lab is not None:
            self._layout.removeWidget(lab)
            lab.deleteLater()
            self._interim = None

    def _trim(self) -> None:
        while len(self._lines) > self.cfg.max_lines:
            orig, tr = self._lines.popleft()
            self._layout.removeWidget(orig)
            orig.deleteLater()
            if tr is not None:
                self._layout.removeWidget(tr)
                tr.deleteLater()

    def _reflow(self) -> None:
        self._apply_style()

    def clear(self) -> None:
        while self._lines:
            orig, tr = self._lines.popleft()
            self._layout.removeWidget(orig)
            orig.deleteLater()
            if tr is not None:
                self._layout.removeWidget(tr)
                tr.deleteLater()
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
