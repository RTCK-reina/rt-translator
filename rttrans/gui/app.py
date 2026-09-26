"""QApplication bootstrap."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from ..config import Config, app_data_dir
from ..pipeline import Pipeline
from ..store import Store
from .main_window import Bridge, MainWindow


def run() -> int:
    import os
    from ..config import portable_root

    # portable package: whisper/HF cache shipped inside the exe folder
    pr = portable_root()
    if pr is not None:
        hf = pr / "hf_cache"
        if hf.exists():
            os.environ.setdefault("HF_HOME", str(hf))

    app = QApplication(sys.argv)
    app.setApplicationName("RT Translator")
    from .theme import apply_theme
    apply_theme(app)

    cfg = Config.load()
    # DB lives in app data (stable); WAV files go to the user-chosen record_dir.
    store = Store(str(app_data_dir()))
    bridge = Bridge()
    pipeline = Pipeline(cfg, store, bridge.event.emit)

    win = MainWindow(cfg, store, pipeline, bridge)
    win.show()

    # first run: offer to download missing models
    from .model_dialog import ensure_models_gui
    ensure_models_gui(cfg, win)

    return app.exec()
