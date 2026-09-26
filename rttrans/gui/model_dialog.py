"""First-run model download dialog (also usable from settings)."""
from __future__ import annotations

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel,
                               QPlainTextEdit, QProgressBar, QVBoxLayout)

from .. import modeldl as dm
from ..config import Config
from .recordings_panel import run_bg


class ModelDownloadDialog(QDialog):
    """Shows missing model components and downloads them on demand."""

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._task = None
        self.setWindowTitle("モデルのダウンロード")
        self.setMinimumWidth(480)

        v = QVBoxLayout(self)
        missing = dm.missing_labels(cfg)
        self.info = QLabel(
            "以下のモデルが未ダウンロードです。\n"
            "初回のみインターネット接続が必要です(以降は完全オフラインで動作):\n\n  - "
            + "\n  - ".join(missing))
        self.info.setWordWrap(True)
        v.addWidget(self.info)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.hide()
        v.addWidget(self.bar)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.log.hide()
        v.addWidget(self.log)

        self.buttons = QDialogButtonBox()
        self.btn_dl = self.buttons.addButton(
            "ダウンロード開始", QDialogButtonBox.AcceptRole)
        self.btn_skip = self.buttons.addButton(
            "あとで (設定タブからDL可)", QDialogButtonBox.RejectRole)
        self.buttons.accepted.connect(self._start)
        self.buttons.rejected.connect(self.reject)
        v.addWidget(self.buttons)

    def _start(self) -> None:
        self.btn_dl.setEnabled(False)
        self.btn_skip.setEnabled(False)
        self.bar.show()
        self.log.show()
        self.adjustSize()
        self._task = run_bg(
            self,
            lambda prog: dm.ensure_models(
                self.cfg, lambda m, f: prog(m, f)),
            on_done=self._done,
            on_fail=self._fail)
        self._task.progress.connect(
            lambda m, f: (self.bar.setValue(int(f * 100)),
                          self.log.appendPlainText(str(m))))

    def _done(self, _res) -> None:
        self.bar.setValue(100)
        self.info.setText("モデルの準備が完了しました。")
        self.btn_dl.hide()
        self.btn_skip.setText("閉じる")
        self.btn_skip.setEnabled(True)

    def _fail(self, msg: str) -> None:
        self.info.setText(f"ダウンロードに失敗しました: {msg}\n"
                          "(再実行で続きから再開できます)")
        self.btn_dl.setEnabled(True)
        self.btn_skip.setEnabled(True)


def ensure_models_gui(cfg: Config, parent=None) -> None:
    """Pop the download dialog if any model component is missing."""
    if dm.missing_models(cfg):
        ModelDownloadDialog(cfg, parent).exec_()
