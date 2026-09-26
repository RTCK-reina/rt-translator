"""Recordings list + offline analysis panel."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel,
                               QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QSplitter, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from .. import analysis
from ..config import Config
from ..store import Recording, Store
from .live_panel import fmt_time


class BgTask(QObject):
    """Run a blocking function on a QThread with progress + result signals."""
    progress = Signal(str, float)
    done = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        try:
            res = self._fn(lambda m, f: self.progress.emit(m, f))
            self.done.emit(res)
        except Exception as e:
            self.failed.emit(str(e))
        finally:
            self.finished.emit()


def run_bg(parent: QWidget, fn, on_done=None, on_fail=None) -> BgTask:
    thread = QThread(parent)
    task = BgTask(fn)
    task.moveToThread(thread)
    thread.started.connect(task.run)
    task.finished.connect(thread.quit)
    task.finished.connect(task.deleteLater)
    thread.finished.connect(thread.deleteLater)
    if on_done:
        task.done.connect(on_done)
    task.failed.connect(on_fail or (lambda msg: QMessageBox.warning(parent, "エラー", msg)))
    thread.start()
    return task


class RecordingsPanel(QWidget):
    def __init__(self, cfg: Config, store: Store):
        super().__init__()
        self.cfg = cfg
        self.store = store
        self._recs: list[Recording] = []
        self._task: BgTask | None = None
        self._build()
        self.refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        split = QSplitter(Qt.Vertical)
        root.addWidget(split, 1)

        # --- top: recording table ---
        top = QWidget()
        tv = QVBoxLayout(top)
        tv.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["名前", "日時", "長さ", "モード", "分析済"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        tv.addWidget(self.table)

        btns = QHBoxLayout()
        for label, fn in [
            ("更新", self.refresh),
            ("開く", self._open_folder),
            ("削除", self._delete),
        ]:
            b = QPushButton(label)
            b.clicked.connect(fn)
            btns.addWidget(b)
        btns.addStretch(1)
        tv.addLayout(btns)
        split.addWidget(top)

        # --- bottom: analysis + transcript ---
        bottom = QWidget()
        bv = QVBoxLayout(bottom)
        bv.setContentsMargins(0, 0, 0, 0)

        ops = QHBoxLayout()
        self.model_combo = QComboBox()
        for m in ["large-v3-turbo", "large-v3", "distil-large-v3",
                  "small", "base", "tiny"]:
            self.model_combo.addItem(m)
        self.model_combo.setCurrentText(self.cfg.power.whisper_model)
        ops.addWidget(QLabel("文字起こしモデル:"))
        ops.addWidget(self.model_combo)
        self.btn_retrans = QPushButton("再文字起こし")
        self.btn_retrans.clicked.connect(self._retranscribe)
        ops.addWidget(self.btn_retrans)

        self.btn_diarize = QPushButton("話者分離")
        self.btn_diarize.clicked.connect(self._diarize)
        ops.addWidget(self.btn_diarize)

        self.spin_speakers = QComboBox()
        self.spin_speakers.addItem("話者数: 自動", -1)
        for n in range(1, 9):
            self.spin_speakers.addItem(str(n), n)
        ops.addWidget(self.spin_speakers)

        self.btn_summary = QPushButton("サマリー")
        self.btn_summary.clicked.connect(self._summarize)
        ops.addWidget(self.btn_summary)

        self.export_combo = QComboBox()
        self.export_combo.addItems(["txt", "srt", "json", "md"])
        ops.addWidget(self.export_combo)
        self.btn_export = QPushButton("エクスポート")
        self.btn_export.clicked.connect(self._export)
        ops.addWidget(self.btn_export)
        ops.addStretch(1)
        bv.addLayout(ops)

        self.progress = QProgressBar()
        self.progress.setMaximumHeight(8)
        self.progress.setTextVisible(True)
        self.progress.hide()
        bv.addWidget(self.progress)

        filt = QHBoxLayout()
        self.speaker_filter = QComboBox()
        self.speaker_filter.addItem("全話者", "")
        self.speaker_filter.currentIndexChanged.connect(self._fill_transcript)
        filt.addWidget(QLabel("話者フィルタ:"))
        filt.addWidget(self.speaker_filter)
        filt.addStretch(1)
        bv.addLayout(filt)

        self.transcript = QPlainTextEdit()
        self.transcript.setReadOnly(True)
        bv.addWidget(self.transcript, 1)

        self.summary_view = QPlainTextEdit()
        self.summary_view.setReadOnly(True)
        self.summary_view.setMaximumHeight(150)
        self.summary_view.setPlaceholderText("サマリー結果がここに表示されます")
        bv.addWidget(self.summary_view)
        split.addWidget(bottom)
        split.setSizes([250, 550])

    # ---------------- list ----------------

    def refresh(self) -> None:
        self._recs = self.store.list_recordings()
        self.table.setRowCount(0)
        for r in self._recs:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(r.name))
            self.table.setItem(row, 1, QTableWidgetItem(r.started_at))
            self.table.setItem(row, 2, QTableWidgetItem(f"{r.duration_s:.0f}s"))
            self.table.setItem(row, 3, QTableWidgetItem(r.mode or ""))
            self.table.setItem(row, 4, QTableWidgetItem("✓" if r.analyzed else ""))
        self.table.resizeColumnsToContents()

    def _selected(self) -> Recording | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        idx = rows[0].row()
        return self._recs[idx] if 0 <= idx < len(self._recs) else None

    def _selection_changed(self) -> None:
        self._fill_transcript()

    def _fill_transcript(self) -> None:
        rec = self._selected()
        self.transcript.clear()
        if rec is None:
            return
        segs = self.store.segments(rec.id)
        speakers = sorted({s.get("speaker") or "" for s in segs} - {""})
        cur = self.speaker_filter.currentData()
        self.speaker_filter.blockSignals(True)
        self.speaker_filter.clear()
        self.speaker_filter.addItem("全話者", "")
        for sp in speakers:
            self.speaker_filter.addItem(sp, sp)
        idx = self.speaker_filter.findData(cur)
        self.speaker_filter.setCurrentIndex(max(0, idx))
        self.speaker_filter.blockSignals(False)

        want = self.speaker_filter.currentData()
        lines = []
        for s in segs:
            if want and (s.get("speaker") or "") != want:
                continue
            sp = f"[{s['speaker']}]" if s.get("speaker") else ""
            line = f"[{fmt_time(s['start'])}] {sp}({s.get('lang','?')}) {s.get('text','')}"
            lines.append(line)
            if s.get("translation"):
                lines.append(f"    → {s['translation']}")
        self.transcript.setPlainText("\n".join(lines) or "(セグメントなし — 再文字起こしを実行)")

    # ---------------- ops ----------------

    def _busy(self, msg: str) -> None:
        self.progress.show()
        self.progress.setRange(0, 0)
        self.progress.setFormat(msg)

    def _idle(self) -> None:
        self.progress.hide()
        self.progress.setRange(0, 100)

    def _retranscribe(self) -> None:
        rec = self._selected()
        if rec is None:
            return
        model = self.model_combo.currentText()
        ct = "float16" if "large" in model or "turbo" in model else "int8"
        self._busy("再文字起こし中…")

        def work(prog):
            return analysis.retranscribe(rec, self.cfg, self.store,
                                         model, ct, progress=prog)

        def done(n):
            self._idle()
            self._fill_transcript()
            self.refresh()
            QMessageBox.information(self, "完了", f"{n} セグメントを生成しました")

        task = run_bg(self, work, done)
        task.progress.connect(
            lambda m, f: (self.progress.setRange(0, 100),
                          self.progress.setValue(int(f * 100)),
                          self.progress.setFormat(f"{m} %p%")))
        self._task = task

    def _diarize(self) -> None:
        rec = self._selected()
        if rec is None:
            return
        n = self.spin_speakers.currentData()
        self._busy("話者分離中…")

        def work(prog):
            return analysis.diarize(rec, self.cfg, self.store,
                                    num_speakers=n, progress=prog)

        def done(turns):
            self._idle()
            self._fill_transcript()
            QMessageBox.information(self, "完了", f"{turns} 発話ターンを検出しました")

        task = run_bg(self, work, done)
        task.progress.connect(
            lambda m, f: (self.progress.setRange(0, 100),
                          self.progress.setValue(int(f * 100)),
                          self.progress.setFormat(f"{m} %p%")))
        self._task = task

    def _summarize(self) -> None:
        rec = self._selected()
        if rec is None:
            return
        self._busy("分析中…")

        def work(prog):
            return analysis.analyze(rec, self.cfg, self.store)

        def done(res):
            self._idle()
            lines = [f"■ 概要 — {res['segment_count']}セグメント, "
                     f"{res['sentences']}文, 長さ {res['duration_s']:.0f}s", ""]
            if res.get("summary_llm"):
                lines += ["■ LLMサマリー", res["summary_llm"], ""]
            lines.append("■ 抽出サマリー")
            lines += [f"・{s}" for s in res["summary_extractive"]]
            lines += ["", "■ キーワード",
                      ", ".join(f"{w}({c})" for w, c in res["keywords"]), "",
                      "■ 話者統計"]
            for sp, d in res["speaker_stats"].items():
                langs = ", ".join(f"{k}:{v}" for k, v in d["langs"].items())
                lines.append(f"{sp}: {d['time']:.0f}s / {d['segments']}セグ / {langs}")
            lines += ["", "■ 言語分布",
                      ", ".join(f"{k}: {v:.0f}s" for k, v in res["lang_dist"].items())]
            self.summary_view.setPlainText("\n".join(lines))

        run_bg(self, work, done)

    def _export(self) -> None:
        rec = self._selected()
        if rec is None:
            return
        fmt = self.export_combo.currentText()
        path, _ = QFileDialog.getSaveFileName(
            self, "エクスポート", f"{rec.name}.{fmt}", f"*.{fmt}")
        if not path:
            return
        try:
            out = analysis.export_recording(rec, self.store, fmt, path)
            QMessageBox.information(self, "完了", f"保存しました:\n{out}")
        except Exception as e:
            QMessageBox.warning(self, "エラー", str(e))

    def _open_folder(self) -> None:
        rec = self._selected()
        path = Path(rec.path).parent if rec else Path(self.cfg.record_dir)
        if sys.platform == "win32":
            os.startfile(str(path))  # noqa: S606
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _delete(self) -> None:
        rec = self._selected()
        if rec is None:
            return
        r = QMessageBox.question(
            self, "削除", f"{rec.name} を削除しますか?\n(WAVファイルも削除されます)")
        if r == QMessageBox.Yes:
            self.store.delete_recording(rec.id)
            self.refresh()
            self.transcript.clear()
            self.summary_view.clear()
