"""Modern dark theme (QSS) applied app-wide."""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

BG = "#14151b"
BG_PANEL = "#1d1f27"
BG_INPUT = "#191b22"
BORDER = "#2e3140"
TEXT = "#e8eaf2"
TEXT_DIM = "#9aa0b4"
ACCENT = "#5b8cff"
ACCENT_HOV = "#739dff"
ACCENT_DIM = "#31477e"
DANGER = "#ff5b6e"
OK = "#3fce8f"

QSS = f"""
* {{
    font-family: "Yu Gothic UI", "Segoe UI", sans-serif;
    font-size: 13px;
    color: {TEXT};
    outline: none;
}}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget {{ background: {BG}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}

QGroupBox {{
    background: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 10px;
    margin-top: 14px;
    padding: 12px 10px 10px 10px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: {TEXT_DIM};
    font-weight: 600;
}}

QPushButton {{
    background: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 16px;
    min-height: 20px;
}}
QPushButton:hover {{ background: #262936; border-color: #3d4257; }}
QPushButton:pressed {{ background: #20222d; }}
QPushButton:disabled {{ color: #565b6e; background: #191b22; }}
QPushButton:checked {{ background: {ACCENT_DIM}; border-color: {ACCENT}; }}
QPushButton#primary {{
    background: {ACCENT};
    color: #ffffff;
    font-weight: 700;
    border: none;
}}
QPushButton#primary:hover {{ background: {ACCENT_HOV}; }}
QPushButton#primary:disabled {{ background: {ACCENT_DIM}; color: #9db3e8; }}
QPushButton#danger {{ background: {DANGER}; color: #fff; font-weight: 700; border: none; }}
QPushButton#danger:hover {{ background: #ff7284; }}
QPushButton#danger:disabled {{ background: #5a2f38; color: #b98a92; }}

QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 5px 8px;
    selection-background-color: {ACCENT};
}}
QComboBox:hover, QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
    border-color: #3d4257;
}}
QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: url({{ARROW_IMG}}); width: 10px; height: 6px; }}
QComboBox QAbstractItemView {{
    background: {BG_PANEL};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT_DIM};
    selection-color: #fff;
}}

QPlainTextEdit, QTextEdit {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px;
    selection-background-color: {ACCENT};
}}

QTableWidget {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    gridline-color: {BORDER};
    selection-background-color: {ACCENT_DIM};
}}
QTableWidget::item {{ padding: 4px; }}
QHeaderView::section {{
    background: {BG_PANEL};
    color: {TEXT_DIM};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px;
    font-weight: 600;
}}

QTabWidget::pane {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 8px;
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_DIM};
    padding: 9px 20px;
    margin-right: 4px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}}
QTabBar::tab:hover {{ color: {TEXT}; background: {BG_PANEL}; }}
QTabBar::tab:selected {{
    color: #fff;
    background: {BG_PANEL};
    border-bottom: 2px solid {ACCENT};
}}

QProgressBar {{
    background: {BG_INPUT};
    border: none;
    border-radius: 4px;
    text-align: center;
    color: {TEXT_DIM};
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border-radius: 4px;
    border: 1px solid {BORDER};
    background: {BG_INPUT};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    image: url({{CHECK_IMG}});
}}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #3a3e52;
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: #4a4f6b; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #3a3e52;
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QToolTip {{
    background: {BG_PANEL};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 5px 8px;
    border-radius: 6px;
}}

QLabel#dim {{ color: {TEXT_DIM}; }}
"""


def _check_png() -> str:
    """Generate a white check-mark PNG in the app data dir; return its
    forward-slashed path for QSS url(). Cached after first call."""
    from pathlib import Path
    from ..config import app_data_dir
    p = Path(app_data_dir()) / "assets" / "check.png"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        from PySide6.QtCore import Qt as _Qt
        from PySide6.QtGui import QPainter, QPainterPath, QPen, QPixmap
        pm = QPixmap(12, 12)
        pm.fill(_Qt.transparent)
        pa = QPainter(pm)
        pa.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#ffffff"), 2.2)
        pen.setCapStyle(_Qt.RoundCap)
        pen.setJoinStyle(_Qt.RoundJoin)
        pa.setPen(pen)
        path = QPainterPath()
        path.moveTo(2.4, 6.4)
        path.lineTo(5.0, 9.2)
        path.lineTo(9.8, 3.0)
        pa.drawPath(path)
        pa.end()
        pm.save(str(p))
    return str(p).replace("\\", "/")


def _arrow_png() -> str:
    """Small down-pointing caret PNG for combo boxes; cached on disk."""
    from pathlib import Path
    from ..config import app_data_dir
    p = Path(app_data_dir()) / "assets" / "arrow_down.png"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        from PySide6.QtCore import Qt as _Qt
        from PySide6.QtGui import QPainter, QPainterPath, QPixmap
        pm = QPixmap(20, 12)
        pm.fill(_Qt.transparent)
        pa = QPainter(pm)
        pa.setRenderHint(QPainter.Antialiasing)
        pa.setPen(_Qt.NoPen)
        pa.setBrush(QColor(TEXT_DIM))
        path = QPainterPath()
        path.moveTo(3, 3)
        path.lineTo(17, 3)
        path.lineTo(10, 9)
        path.closeSubpath()
        pa.drawPath(path)
        pa.end()
        pm.save(str(p))
    return str(p).replace("\\", "/")


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setFont(QFont("Yu Gothic UI", 10))
    pal = app.palette()
    pal.setColor(QPalette.Window, QColor(BG))
    pal.setColor(QPalette.WindowText, QColor(TEXT))
    pal.setColor(QPalette.Base, QColor(BG_INPUT))
    pal.setColor(QPalette.Text, QColor(TEXT))
    pal.setColor(QPalette.Button, QColor(BG_PANEL))
    pal.setColor(QPalette.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.PlaceholderText, QColor(TEXT_DIM))
    app.setPalette(pal)
    qss = QSS.replace("{CHECK_IMG}", _check_png()).replace(
        "{ARROW_IMG}", _arrow_png())
    app.setStyleSheet(qss)
