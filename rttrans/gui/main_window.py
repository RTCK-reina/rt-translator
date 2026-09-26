"""Main window with tabs."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMainWindow, QTabWidget

from ..config import Config
from ..pipeline import Pipeline
from ..store import Store
from .live_panel import LivePanel
from .recordings_panel import RecordingsPanel
from .settings_panel import SettingsPanel


class Bridge(QObject):
    """Pipeline events -> Qt signal (thread-safe queued delivery)."""
    event = Signal(str, dict)


class MainWindow(QMainWindow):
    def __init__(self, cfg: Config, store: Store, pipeline: Pipeline,
                 bridge: Bridge):
        super().__init__()
        self.cfg = cfg
        self.pipeline = pipeline
        self.setWindowTitle("RT Translator")
        self.resize(980, 720)

        tabs = QTabWidget()
        self.live = LivePanel(cfg, pipeline)
        self.recs = RecordingsPanel(cfg, store)
        self.settings = SettingsPanel(cfg, pipeline)
        tabs.addTab(self.live, "ライブ翻訳")
        tabs.addTab(self.recs, "録音・分析")
        tabs.addTab(self.settings, "設定")
        self.setCentralWidget(tabs)

        self.settings.saved.connect(self.live.refresh_overlay)
        bridge.event.connect(self._dispatch)

    def _dispatch(self, kind: str, payload: dict) -> None:
        self.live.on_event(kind, payload)
        if kind == "recording" and payload.get("state") == "stopped":
            self.recs.refresh()

    def closeEvent(self, e) -> None:
        self.pipeline.stop()
        self.cfg.save()
        super().closeEvent(e)
