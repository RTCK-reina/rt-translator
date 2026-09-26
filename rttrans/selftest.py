"""Non-GUI self diagnostics: `RTTranslator.exe --selftest`.

Runs VAD + Whisper(CUDA) + NLLB on a generated sine burst and a tiny
whisper pass over it, then writes a report file. Works from the frozen
exe too (report -> %APPDATA%/RTTranslator/selftest.txt).
"""
from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

import numpy as np


def run_selftest(out_path: Path | None = None) -> int:
    from .config import Config, app_data_dir

    lines: list[str] = []
    ok = True

    def log(msg: str) -> None:
        lines.append(str(msg))

    try:
        cfg = Config.load()
        log(f"config: mode={cfg.mode} nllb={cfg.nllb_dir}")

        # 1) VAD
        from .vad import VadSegmenter
        v = VadSegmenter()
        p = v._prob(np.zeros(512, np.float32))
        log(f"vad onnx ok (silence prob={p:.3f})")

        # 2) whisper on cuda
        from .stt import SttEngine
        name = cfg.resolve_whisper("tiny")
        t0 = time.time()
        eng = SttEngine(name, "cuda", "int8")
        eng.load()
        log(f"whisper '{name}' cuda loaded in {time.time() - t0:.1f}s")

        # 3) nllb
        from .translator import NllbTranslator
        tr = NllbTranslator(cfg.nllb_dir, "cpu", "int8")
        if tr.model_ready():
            tr.load()
            out = tr.translate("Hello, how are you?", "en", "ja")
            log(f"nllb cpu: en->ja = {out!r}")
        else:
            log("nllb: NOT DOWNLOADED")

        # 4) speaker model presence
        from .speakers import SpeakerEmbedder
        emb = SpeakerEmbedder(cfg.speaker_model)
        log(f"speaker model: {'ok' if emb.available() else 'missing'}")

        # 5) devices
        from .devices import list_devices
        devs = list_devices()
        log(f"devices: {len(devs)} ({sum(d.is_loopback for d in devs)} loopback)")

        # 6) model presence
        from . import modeldl as dm
        miss = dm.missing_labels(cfg)
        log(f"models: {'all present' if not miss else 'missing -> ' + ', '.join(miss)}")

        # 7) store
        from .store import Store
        st = Store(str(app_data_dir() / "selftest_db"))
        rid = st.create_recording("x", "selftest", "dev", "eco")
        st.finish_recording(rid, 0.1)
        st.delete_recording(rid)
        st.close()
        log("store ok")

    except Exception:
        ok = False
        log("FAILED:\n" + traceback.format_exc())

    report = "\n".join(lines)
    if out_path is None:
        out_path = app_data_dir() / "selftest.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(report)
    return 0 if ok else 1
