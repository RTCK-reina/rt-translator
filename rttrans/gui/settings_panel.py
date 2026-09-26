"""Settings panel: model paths/downloads, mode presets, capture, overlay."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QProgressBar, QPushButton,
                               QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from PySide6.QtCore import Qt, Signal
from ..config import Config
from ..pipeline import Pipeline
from .. import modeldl as dm
from .recordings_panel import run_bg


class SettingsPanel(QWidget):
    saved = Signal()  # emitted after settings are persisted

    def __init__(self, cfg: Config, pipeline: Pipeline):
        super().__init__()
        self.cfg = cfg
        self.pipeline = pipeline
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll, 1)
        body = QWidget()
        scroll.setWidget(body)
        root = QVBoxLayout(body)

        # ---------- model paths ----------
        g_model = QGroupBox("モデル")
        fm = QFormLayout(g_model)
        self.ed_model_dir = self._path_row(fm, "モデル保存先", self.cfg.model_dir, dir_pick=True)
        self.ed_nllb = self._path_row(fm, "翻訳モデル (NLLB CT2)", self.cfg.nllb_dir, dir_pick=True)
        self.ed_whisper = QLineEdit(self.cfg.whisper_model_path)
        self.ed_whisper.setPlaceholderText("空欄 = モード別プリセットを使用")
        fm.addRow("Whisperローカルパス(任意)", self.ed_whisper)
        self.ed_spk = self._path_row(fm, "話者埋め込み (onnx)", self.cfg.speaker_model)
        self.ed_seg = self._path_row(fm, "セグメンテーション (onnx)", self.cfg.segmentation_model)

        btn_all = QPushButton("不足モデルを一括DL")
        btn_all.setObjectName("primary")
        btn_all.clicked.connect(self._dl_all)
        fm.addRow(btn_all)
        dl = QHBoxLayout()
        for label, fn in [
            ("翻訳DL", self._dl_nllb),
            ("話者DL", self._dl_speaker),
            ("セグDL", self._dl_seg),
            ("Whisper DL", self._dl_whisper),
        ]:
            b = QPushButton(label)
            b.clicked.connect(fn)
            dl.addWidget(b)
        dl.addStretch(1)
        fm.addRow("個別:", dl)
        self.btn_unload = QPushButton("モデル解放 (VRAM/メモリを空ける)")
        self.btn_unload.clicked.connect(self._unload_models)
        unl = QHBoxLayout()
        unl.addWidget(self.btn_unload)
        unl.addStretch(1)
        fm.addRow(unl)
        root.addWidget(g_model)

        # ---------- mode presets ----------
        g_modes = QGroupBox("モードプリセット")
        hm = QHBoxLayout(g_modes)
        self.eco_form = _PresetForm("エコ (低負荷)", self.cfg.eco)
        self.power_form = _PresetForm("フルパワー", self.cfg.power)
        hm.addWidget(self.eco_form)
        hm.addWidget(self.power_form)
        root.addWidget(g_modes)

        # ---------- capture ----------
        g_cap = QGroupBox("キャプチャ / 推論")
        fc = QFormLayout(g_cap)
        self.rate_combo = QComboBox()
        self.rate_combo.addItems(["48000", "44100", "16000"])
        self.rate_combo.setCurrentText(str(self.cfg.capture_rate))
        fc.addRow("キャプチャレート", self.rate_combo)
        self.sp_block = QSpinBox()
        self.sp_block.setRange(30, 500)
        self.sp_block.setSuffix(" ms")
        self.sp_block.setValue(self.cfg.capture_block_ms)
        fc.addRow("ブロック長", self.sp_block)
        self.sp_interim = QDoubleSpinBox()
        self.sp_interim.setRange(0.5, 5.0)
        self.sp_interim.setSingleStep(0.5)
        self.sp_interim.setSuffix(" s")
        self.sp_interim.setValue(self.cfg.interim_interval_s)
        fc.addRow("中間結果間隔", self.sp_interim)
        self.sp_spkth = QDoubleSpinBox()
        self.sp_spkth.setRange(0.3, 0.95)
        self.sp_spkth.setSingleStep(0.05)
        self.sp_spkth.setValue(self.cfg.speaker_threshold)
        fc.addRow("話者一致しきい値", self.sp_spkth)
        root.addWidget(g_cap)

        # ---------- overlay ----------
        g_ov = QGroupBox("字幕オーバーレイ")
        fo = QFormLayout(g_ov)
        self.sp_font = QSpinBox()
        self.sp_font.setRange(10, 72)
        self.sp_font.setValue(self.cfg.overlay.font_size)
        fo.addRow("フォントサイズ", self.sp_font)
        self.sp_lines = QSpinBox()
        self.sp_lines.setRange(1, 10)
        self.sp_lines.setValue(self.cfg.overlay.max_lines)
        fo.addRow("最大行数", self.sp_lines)
        self.sp_opacity = QSpinBox()
        self.sp_opacity.setRange(20, 255)
        self.sp_opacity.setValue(self.cfg.overlay.bg_opacity)
        fo.addRow("背景の濃さ", self.sp_opacity)
        self.chk_through = QCheckBox("クリックスルー (ゲーム操作を妨げない)")
        self.chk_through.setChecked(self.cfg.overlay.click_through)
        fo.addRow(self.chk_through)
        self.chk_orig = QCheckBox("原文も表示する")
        self.chk_orig.setChecked(self.cfg.overlay.show_original)
        fo.addRow(self.chk_orig)
        root.addWidget(g_ov)

        # ---------- storage / llm ----------
        g_st = QGroupBox("保存 / 要約")
        fs = QFormLayout(g_st)
        self.ed_record_dir = self._path_row(fs, "録音保存先", self.cfg.record_dir, dir_pick=True)
        self.ed_llm = self._path_row(fs, "LLM(GGUF, 任意)", self.cfg.llm_gguf_path)
        root.addWidget(g_st)

        # ---------- save ----------
        row = QHBoxLayout()
        btn_save = QPushButton("設定を保存")
        btn_save.clicked.connect(self._save)
        row.addWidget(btn_save)
        row.addStretch(1)
        root.addLayout(row)

        self.dl_progress = QProgressBar()
        self.dl_progress.hide()
        root.addWidget(self.dl_progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(110)
        root.addWidget(self.log)
        root.addStretch(1)

    # ---------------- helpers ----------------

    def _path_row(self, form: QFormLayout, label: str, value: str,
                  dir_pick: bool = False) -> QLineEdit:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        ed = QLineEdit(value)
        b = QPushButton("…")
        b.setFixedWidth(30)

        def pick():
            if dir_pick:
                p = QFileDialog.getExistingDirectory(self, label, ed.text())
            else:
                p, _ = QFileDialog.getOpenFileName(self, label, ed.text())
            if p:
                ed.setText(p)
        b.clicked.connect(pick)
        h.addWidget(ed, 1)
        h.addWidget(b)
        form.addRow(label, w)
        return ed

    def _log(self, msg: str) -> None:
        self.log.appendPlainText(str(msg))

    def _dl(self, fn, label: str) -> None:
        self.dl_progress.show()
        self.dl_progress.setRange(0, 0)
        self.dl_progress.setFormat(label)
        self._task = run_bg(self, lambda prog: fn(lambda m: prog(m, 0)),
                            on_done=lambda r: (self.dl_progress.hide(),
                                               self._log(f"{label}: 完了")),
                            on_fail=lambda e: (self.dl_progress.hide(),
                                               self._log(f"{label}: 失敗 {e}")))
        self._task.progress.connect(lambda m, f: self._log(m))

    # ---------------- actions ----------------

    def _dl_all(self) -> None:
        self._save()
        from .model_dialog import ensure_models_gui
        ensure_models_gui(self.cfg, self)

    def _dl_nllb(self) -> None:
        self._save()
        self._dl(lambda prog: dm.download_nllb(self.cfg.nllb_dir, prog), "翻訳モデル")

    def _dl_speaker(self) -> None:
        self._save()
        self._dl(lambda prog: dm.download_speaker_model(self.cfg.speaker_model, prog),
                 "話者モデル")

    def _dl_seg(self) -> None:
        self._save()
        self._dl(lambda prog: dm.download_segmentation(
            str(Path(self.cfg.segmentation_model).parent), prog), "セグメンテーション")

    def _dl_whisper(self) -> None:
        self._save()
        model = self.cfg.preset().whisper_model
        self._dl(lambda prog: dm.download_whisper(model, prog), f"Whisper {model}")

    def _unload_models(self) -> None:
        if self.pipeline.running:
            QMessageBox.information(self, "実行中", "停止してから解放してください")
            return
        for eng in self.pipeline.engines.stt_engines.values():
            eng.unload()
        if self.pipeline.engines.translator:
            self.pipeline.engines.translator.unload()
        if self.pipeline.engines.embedder:
            self.pipeline.engines.embedder._ext = None
        self._log("モデルを解放しました")

    def _save(self) -> None:
        c = self.cfg
        c.model_dir = self.ed_model_dir.text().strip() or c.model_dir
        c.nllb_dir = self.ed_nllb.text().strip()
        c.whisper_model_path = self.ed_whisper.text().strip()
        c.speaker_model = self.ed_spk.text().strip()
        c.segmentation_model = self.ed_seg.text().strip()
        c.record_dir = self.ed_record_dir.text().strip() or c.record_dir
        c.llm_gguf_path = self.ed_llm.text().strip()
        c.capture_rate = int(self.rate_combo.currentText())
        c.capture_block_ms = self.sp_block.value()
        c.interim_interval_s = self.sp_interim.value()
        c.speaker_threshold = self.sp_spkth.value()
        c.overlay.font_size = self.sp_font.value()
        c.overlay.max_lines = self.sp_lines.value()
        c.overlay.bg_opacity = self.sp_opacity.value()
        c.overlay.click_through = self.chk_through.isChecked()
        c.overlay.show_original = self.chk_orig.isChecked()
        self.eco_form.apply(c.eco)
        self.power_form.apply(c.power)
        c.save()
        self.saved.emit()
        self._log("設定を保存しました")


class _PresetForm(QGroupBox):
    def __init__(self, title: str, preset):
        super().__init__(title)
        f = QFormLayout(self)
        self.ed_model = QLineEdit(preset.whisper_model)
        self.ed_model.setPlaceholderText("例: base / small / large-v3-turbo / distil-large-v3")
        f.addRow("Whisperモデル", self.ed_model)
        self.combo_ct = QComboBox()
        self.combo_ct.addItems(["int8", "int8_float16", "float16", "float32"])
        self.combo_ct.setCurrentText(preset.compute_type)
        f.addRow("量子化", self.combo_ct)
        self.sp_beam = QSpinBox()
        self.sp_beam.setRange(1, 10)
        self.sp_beam.setValue(preset.beam_size)
        f.addRow("ビームサイズ", self.sp_beam)
        self.chk_spk = QCheckBox("話者分離を有効化")
        self.chk_spk.setChecked(preset.enable_speakers)
        f.addRow(self.chk_spk)
        self.chk_interim = QCheckBox("中間結果を表示")
        self.chk_interim.setChecked(preset.interim_results)
        f.addRow(self.chk_interim)
        self.sp_sil = QSpinBox()
        self.sp_sil.setRange(200, 2000)
        self.sp_sil.setSuffix(" ms")
        self.sp_sil.setValue(preset.vad_silence_ms)
        f.addRow("無音で区切る長さ", self.sp_sil)
        self.sp_maxseg = QDoubleSpinBox()
        self.sp_maxseg.setRange(2.0, 30.0)
        self.sp_maxseg.setSuffix(" s")
        self.sp_maxseg.setValue(preset.max_segment_s)
        f.addRow("最大セグメント長", self.sp_maxseg)

    def apply(self, preset) -> None:
        preset.whisper_model = self.ed_model.text().strip() or preset.whisper_model
        preset.compute_type = self.combo_ct.currentText()
        preset.beam_size = self.sp_beam.value()
        preset.enable_speakers = self.chk_spk.isChecked()
        preset.interim_results = self.chk_interim.isChecked()
        preset.vad_silence_ms = self.sp_sil.value()
        preset.max_segment_s = self.sp_maxseg.value()
