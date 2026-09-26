"""Live translation control panel."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGroupBox, QHBoxLayout,
                               QLabel, QProgressBar, QPushButton,
                               QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from .. import devices
from ..config import Config
from ..langs import (ACTION_LABELS, ACTIONS, LANGS, all_known_codes,
                     lang_name)
from ..pipeline import Pipeline
from .overlay import OverlayWindow
from .transcript import TranscriptView
from .waveform import WaveformWidget


def fmt_time(t: float) -> str:
    m, s = divmod(int(t), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


class LivePanel(QWidget):
    def __init__(self, cfg: Config, pipeline: Pipeline):
        super().__init__()
        self.cfg = cfg
        self.pipeline = pipeline
        self.overlay: OverlayWindow | None = None
        self._session_lines: list[str] = []
        self._dev_list: list[devices.AudioDevice] = []
        self._build()
        self.refresh_devices()

    # ---------------- UI ----------------

    def _build(self) -> None:
        root = QVBoxLayout(self)

        # --- input row ---
        top = QHBoxLayout()
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(360)
        self.device_combo.currentIndexChanged.connect(self._device_changed)
        btn_ref = QPushButton("再取得")
        btn_ref.clicked.connect(self.refresh_devices)
        top.addWidget(QLabel("入力デバイス:"))
        top.addWidget(self.device_combo, 1)
        top.addWidget(btn_ref)
        root.addLayout(top)

        # --- mode row ---
        mode_row = QHBoxLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("エコ (低負荷・ゲーム併用)", "eco")
        self.mode_combo.addItem("フルパワー (高精度)", "power")
        self.mode_combo.setCurrentIndex(0 if self.cfg.mode == "eco" else 1)
        self.mode_combo.currentIndexChanged.connect(self._mode_changed)
        mode_row.addWidget(QLabel("モード:"))
        mode_row.addWidget(self.mode_combo)

        self.tgt_combo = QComboBox()
        for code in ["ja", "en", "zh", "ko", "de", "fr", "es", "pt", "ru"]:
            self.tgt_combo.addItem(f"{lang_name(code)} ({code})", code)
        self.tgt_combo.setCurrentIndex(
            max(0, self.tgt_combo.findData(self.cfg.target_lang)))
        self.tgt_combo.currentIndexChanged.connect(self._target_changed)
        mode_row.addWidget(QLabel("翻訳先:"))
        mode_row.addWidget(self.tgt_combo)

        self.chk_translate = QCheckBox("翻訳有効")
        self.chk_translate.setChecked(self.cfg.translation_enabled)
        self.chk_translate.toggled.connect(
            lambda v: setattr(self.cfg, "translation_enabled", v))
        mode_row.addWidget(self.chk_translate)

        self.chk_record = QCheckBox("録音する")
        self.chk_record.setChecked(True)
        mode_row.addWidget(self.chk_record)
        mode_row.addStretch(1)
        root.addLayout(mode_row)

        # --- language filter table ---
        lang_box = QGroupBox("言語フィルタ (検出言語ごとの動作)")
        lv = QVBoxLayout(lang_box)
        self.lang_table = QTableWidget(0, 2)
        self.lang_table.setHorizontalHeaderLabels(["言語", "動作"])
        self.lang_table.horizontalHeader().setStretchLastSection(True)
        self.lang_table.setMaximumHeight(140)
        lv.addWidget(self.lang_table)
        add_row = QHBoxLayout()
        self.add_lang_combo = QComboBox()
        for c in all_known_codes():
            self.add_lang_combo.addItem(f"{lang_name(c)} ({c})", c)
        btn_add_lang = QPushButton("言語を追加")
        btn_add_lang.clicked.connect(self._add_lang_row)
        self.default_action_combo = QComboBox()
        for a in ACTIONS:
            self.default_action_combo.addItem(ACTION_LABELS[a], a)
        self.default_action_combo.setCurrentIndex(
            ACTIONS.index(self.cfg.default_lang_action))
        self.default_action_combo.currentIndexChanged.connect(
            lambda _: setattr(self.cfg, "default_lang_action",
                              self.default_action_combo.currentData()))
        add_row.addWidget(self.add_lang_combo)
        add_row.addWidget(btn_add_lang)
        add_row.addStretch(1)
        add_row.addWidget(QLabel("その他の言語:"))
        add_row.addWidget(self.default_action_combo)
        lv.addLayout(add_row)
        root.addWidget(lang_box)
        self._load_lang_rows()

        # --- control row ---
        ctrl = QHBoxLayout()
        self.btn_start = QPushButton("開始")
        self.btn_start.setObjectName("primary")
        self.btn_start.setMinimumHeight(36)
        self.btn_start.clicked.connect(self._start)
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setObjectName("danger")
        self.btn_stop.setMinimumHeight(36)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_overlay = QPushButton("字幕オーバーレイ")
        self.btn_overlay.setCheckable(True)
        self.btn_overlay.clicked.connect(self._toggle_overlay)
        self.btn_export = QPushButton("セッション保存")
        self.btn_export.clicked.connect(self._export_session)
        ctrl.addWidget(self.btn_start)
        ctrl.addWidget(self.btn_stop)
        ctrl.addWidget(self.btn_overlay)
        ctrl.addWidget(self.btn_export)
        ctrl.addStretch(1)
        root.addLayout(ctrl)

        # --- status row ---
        stat = QHBoxLayout()
        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setTextVisible(False)
        self.level.setMaximumHeight(8)
        self.status = QLabel("待機中")
        self.speech = QLabel("")
        stat.addWidget(self.level, 1)
        stat.addWidget(self.speech)
        stat.addWidget(self.status, 2)
        root.addLayout(stat)

        # --- waveform ---
        self.waveform = WaveformWidget()
        root.addWidget(self.waveform)

        self.interim = QLabel("")
        self.interim.setStyleSheet("color: #7f9fff;")
        self.interim.setWordWrap(True)
        root.addWidget(self.interim)

        # --- transcript ---
        self.transcript = TranscriptView()
        root.addWidget(self.transcript, 1)

    # ---------------- device / mode ----------------

    def refresh_devices(self) -> None:
        prev = self.device_combo.currentData()
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        try:
            self._dev_list = devices.list_devices()
        except Exception as e:
            self.status.setText(f"デバイス取得失敗: {e}")
            self._dev_list = []
        sel = 0
        for i, d in enumerate(self._dev_list):
            self.device_combo.addItem(d.label, d.id)
            if d.id == prev or d.id == self.cfg.device_id:
                sel = i
        if self._dev_list:
            self.device_combo.setCurrentIndex(sel)
        self.device_combo.blockSignals(False)

    def _device_changed(self, idx: int) -> None:
        if 0 <= idx < len(self._dev_list):
            d = self._dev_list[idx]
            self.cfg.device_id = d.id
            self.cfg.device_name = d.name

    def _mode_changed(self, idx: int) -> None:
        self.cfg.mode = self.mode_combo.itemData(idx)

    def _target_changed(self, idx: int) -> None:
        self.cfg.target_lang = self.tgt_combo.itemData(idx)

    # ---------------- lang filter table ----------------

    def _load_lang_rows(self) -> None:
        for code in list(self.cfg.lang_actions.keys()):
            self._append_lang_row(code, self.cfg.lang_actions[code])

    def _append_lang_row(self, code: str, action: str) -> None:
        row = self.lang_table.rowCount()
        self.lang_table.insertRow(row)
        self.lang_table.setItem(row, 0, QTableWidgetItem(f"{lang_name(code)} ({code})"))
        self.lang_table.item(row, 0).setData(Qt.UserRole, code)
        combo = QComboBox()
        for a in ACTIONS:
            combo.addItem(ACTION_LABELS[a], a)
        combo.setCurrentIndex(ACTIONS.index(action) if action in ACTIONS else 1)
        combo.currentIndexChanged.connect(lambda _i, c=combo: self._lang_action_changed())
        self.lang_table.setCellWidget(row, 1, combo)

    def _add_lang_row(self) -> None:
        code = self.add_lang_combo.currentData()
        for r in range(self.lang_table.rowCount()):
            if self.lang_table.item(r, 0).data(Qt.UserRole) == code:
                return
        self._append_lang_row(code, self.cfg.default_lang_action)
        self._lang_action_changed()

    def _lang_action_changed(self) -> None:
        actions = {}
        for r in range(self.lang_table.rowCount()):
            code = self.lang_table.item(r, 0).data(Qt.UserRole)
            actions[code] = self.lang_table.cellWidget(r, 1).currentData()
        self.cfg.lang_actions = actions
        self.cfg.save()

    def ensure_lang_row(self, code: str) -> None:
        """Auto-add detected language to the table."""
        for r in range(self.lang_table.rowCount()):
            if self.lang_table.item(r, 0).data(Qt.UserRole) == code:
                return
        if code in LANGS:
            self._append_lang_row(code, self.cfg.action_for_lang(code))
            self._lang_action_changed()

    # ---------------- control ----------------

    def _start(self) -> None:
        if not self._dev_list:
            self.status.setText("入力デバイスがありません")
            return
        dev_id = self.device_combo.currentData()
        self._device_changed(self.device_combo.currentIndex())
        self.transcript.clear()
        self.waveform.clear()
        self._session_lines = []
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        # start() loads models (can take seconds) -> run off the UI thread
        from .recordings_panel import run_bg
        self._start_task = run_bg(
            self,
            lambda _prog: self.pipeline.start(
                dev_id, record=self.chk_record.isChecked()),
            on_done=lambda _r: None,
            on_fail=lambda e: self.status.setText(f"開始失敗: {e}"))

    def _stop(self) -> None:
        self.btn_stop.setEnabled(False)
        self.pipeline.stop()
        self.btn_start.setEnabled(True)
        self.interim.setText("")
        self.speech.setText("")
        self.waveform.set_active(False)

    def _toggle_overlay(self, checked: bool) -> None:
        if checked:
            if self.overlay is None:
                self.overlay = OverlayWindow(self.cfg.overlay)
            self.overlay.show()
        elif self.overlay is not None:
            self.overlay.hide()

    def refresh_overlay(self) -> None:
        """Push current overlay settings to a live overlay window."""
        if self.overlay is not None:
            self.overlay.update_config(self.cfg.overlay)

    def _export_session(self) -> None:
        if not self._session_lines:
            return
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "セッション保存",
            f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Text (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(self._session_lines))

    # ---------------- pipeline events ----------------

    def on_event(self, kind: str, p: dict) -> None:
        if kind == "status":
            self.status.setText(p["text"])
        elif kind == "error":
            self.status.setText(f"エラー: {p['text']}")
            if not self.pipeline.running:
                self.btn_start.setEnabled(True)
                self.btn_stop.setEnabled(False)
        elif kind == "level":
            self.level.setValue(int(p["rms"] * 100))
            self.waveform.push(p.get("wave") or [])
        elif kind == "speech":
            self.speech.setText("● 聞き取り中" if p["state"] == "start" else "")
            self.waveform.set_active(p["state"] == "start")
            if p["state"] == "end":
                self.interim.setText("")
                if self.overlay:
                    self.overlay.clear_interim()
        elif kind == "interim":
            self.interim.setText(f"… {p['text']}")
            if self.overlay:
                self.overlay.add_interim(p["text"])
        elif kind == "segment":
            self._add_segment(p)
        elif kind == "recording":
            if p["state"] == "started":
                self.status.setText(f"録音中: {p['path']}")
            else:
                self.status.setText(f"録音保存 ({p['duration']:.0f}s)")

    def _add_segment(self, s: dict) -> None:
        self.ensure_lang_row(s["lang"])
        self.interim.setText("")
        self.transcript.add_segment(s)
        ts = fmt_time(s["start"])
        sp = f"[{s['speaker']}]" if s.get("speaker") else ""
        header = f"[{ts}] [{s['lang_name']}]{sp}"
        self._session_lines.append(f"{header} {s['text']}")
        if s.get("translation"):
            self._session_lines.append(
                f"{' ' * len(header)}  → {s['translation']}")
        if self.overlay and self.btn_overlay.isChecked():
            self.overlay.clear_interim()
            self.overlay.add_line(s["lang"], s.get("speaker") or "",
                                  s["text"], s.get("translation"),
                                  s.get("action") or "show")
