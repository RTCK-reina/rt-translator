"""Model download helpers.

Used by the GUI (settings tab) and runnable standalone:
    python tools/download_models.py all
    python tools/download_models.py nllb|speaker|segmentation|whisper [model]
"""
from __future__ import annotations

import sys
import tarfile
import urllib.request
from pathlib import Path

from .config import Config  # noqa: E402

NLLB_REPO = "mijuanlo/nllb-200-distilled-600M-ct2-int8"
NLLB_FILES = ["model.bin", "config.json", "sentencepiece.bpe.model",
              "shared_vocabulary.json", "shared_vocabulary.txt"]

GH = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
SPEAKER_MODEL_URL = (
    f"{GH}/speaker-recongition-models/"
    "3dspeaker_speech_eres2net_base_200k_sv_zh-cn_16k-common.onnx")
SEGMENTATION_URL = (
    f"{GH}/speaker-segmentation-models/"
    "sherpa-onnx-pyannote-segmentation-3-0.tar.bz2")


def _progress(msg: str):
    print(msg, flush=True)


def download_nllb(dest: str, progress=_progress) -> str:
    from huggingface_hub import hf_hub_download

    d = Path(dest)
    d.mkdir(parents=True, exist_ok=True)
    for f in NLLB_FILES:
        try:
            p = hf_hub_download(NLLB_REPO, f, local_dir=str(d))
            progress(f"nllb: {f} -> {p}")
        except Exception as e:
            if f in ("model.bin", "sentencepiece.bpe.model"):
                raise
            progress(f"nllb: {f} skipped ({e})")
    return str(d)


def download_whisper(model: str, progress=_progress) -> str:
    """Pre-fetch a faster-whisper model (handles alias->repo mapping)."""
    from faster_whisper.utils import download_model

    p = download_model(model)
    progress(f"whisper: {model} -> {p}")
    return p


def _fetch(url: str, dest: Path, progress=_progress) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        progress(f"exists: {dest}")
        return dest
    tmp = dest.with_suffix(dest.suffix + ".part")
    progress(f"downloading {url}")
    with urllib.request.urlopen(url) as r, open(tmp, "wb") as w:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            buf = r.read(1 << 20)
            if not buf:
                break
            w.write(buf)
            done += len(buf)
            if total:
                progress(f"  {dest.name}: {done * 100 // total}%")
    tmp.replace(dest)
    return dest


def download_speaker_model(dest: str, progress=_progress) -> str:
    _fetch(SPEAKER_MODEL_URL, Path(dest), progress)
    return dest


def download_segmentation(dest_dir: str, progress=_progress) -> str:
    d = Path(dest_dir)
    d.mkdir(parents=True, exist_ok=True)
    archive = d / "seg.tar.bz2"
    _fetch(SEGMENTATION_URL, archive, progress)
    if not (d / "model.onnx").exists():
        progress("extracting...")
        with tarfile.open(archive) as t:
            t.extractall(d, filter="data")
        # archive contains sherpa-onnx-pyannote-segmentation-3-0/model.onnx
        for onnx in sorted(d.rglob("*.onnx")):
            if onnx.parent != d:
                onnx.replace(d / "model.onnx")
    archive.unlink(missing_ok=True)
    return str(d / "model.onnx")


def download_all(cfg: Config | None = None, progress=_progress) -> None:
    cfg = cfg or Config.load()
    download_nllb(cfg.nllb_dir, progress)
    download_speaker_model(cfg.speaker_model, progress)
    download_segmentation(str(Path(cfg.segmentation_model).parent), progress)
    download_whisper(cfg.eco.whisper_model, progress)
    download_whisper(cfg.power.whisper_model, progress)
    progress("done")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    cfg = Config.load()
    if what == "nllb":
        download_nllb(cfg.nllb_dir)
    elif what == "speaker":
        download_speaker_model(cfg.speaker_model)
    elif what == "segmentation":
        download_segmentation(str(Path(cfg.segmentation_model).parent))
    elif what == "whisper":
        download_whisper(sys.argv[2] if len(sys.argv) > 2 else cfg.eco.whisper_model)
    else:
        download_all(cfg)
