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

from .config import Config, portable_root  # noqa: E402

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


def whisper_local_dir(model: str) -> Path | None:
    """Portable package: whisper models live in <exe>/models/whisper-<name>."""
    pr = portable_root()
    return (pr / "models" / f"whisper-{model}") if pr is not None else None


def download_whisper(model: str, progress=_progress) -> str:
    """Pre-fetch a faster-whisper model (handles alias->repo mapping)."""
    from faster_whisper.utils import download_model

    out = whisper_local_dir(model)
    kw = {"output_dir": str(out)} if out is not None else {}
    p = download_model(model, **kw)
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


# ---------------- presence checks / first-run download ----------------

ITEM_LABELS = {
    "nllb": "翻訳モデル (NLLB-200 int8, ~600MB)",
    "speaker": "話者埋め込みモデル (~38MB)",
    "segmentation": "セグメンテーション (~6MB)",
}


def nllb_present(cfg: Config) -> bool:
    return (Path(cfg.nllb_dir) / "model.bin").exists()


def speaker_present(cfg: Config) -> bool:
    return Path(cfg.speaker_model).exists()


def segmentation_present(cfg: Config) -> bool:
    return Path(cfg.segmentation_model).exists()


def whisper_present(cfg: Config, model: str) -> bool:
    resolved = cfg.resolve_whisper(model)
    p = Path(resolved)
    if p.is_dir():
        return (p / "model.bin").exists()
    try:
        from faster_whisper.utils import download_model
        download_model(resolved, local_files_only=True)
        return True
    except Exception:
        return False


def missing_models(cfg: Config) -> list[str]:
    """Component keys still needing download (whisper -> 'whisper:<name>')."""
    miss: list[str] = []
    if not nllb_present(cfg):
        miss.append("nllb")
    if not speaker_present(cfg):
        miss.append("speaker")
    if not segmentation_present(cfg):
        miss.append("segmentation")
    for m in _whisper_models(cfg):
        if not whisper_present(cfg, m):
            miss.append(f"whisper:{m}")
    return miss


def missing_labels(cfg: Config) -> list[str]:
    out = []
    for k in missing_models(cfg):
        if k.startswith("whisper:"):
            name = k.split(":", 1)[1]
            size = {"tiny": "~75MB", "base": "~150MB", "small": "~460MB",
                    "medium": "~1.5GB"}.get(name, "~1-2GB")
            out.append(f"Whisper {name} ({size})")
        else:
            out.append(ITEM_LABELS.get(k, k))
    return out


def _whisper_models(cfg: Config) -> list[str]:
    if cfg.whisper_model_path:
        return [cfg.whisper_model_path]
    return sorted({cfg.eco.whisper_model, cfg.power.whisper_model})


def ensure_models(cfg: Config, progress) -> None:
    """Download only missing components. progress(msg, frac 0..1)."""
    steps: list[tuple[str, object]] = []
    if not nllb_present(cfg):
        steps.append(("翻訳モデル", lambda p: download_nllb(cfg.nllb_dir, p)))
    if not speaker_present(cfg):
        steps.append(("話者モデル", lambda p: download_speaker_model(cfg.speaker_model, p)))
    if not segmentation_present(cfg):
        steps.append(("セグメンテーション", lambda p: download_segmentation(
            str(Path(cfg.segmentation_model).parent), p)))
    for m in _whisper_models(cfg):
        if not whisper_present(cfg, m):
            steps.append((f"Whisper {m}", lambda p, m=m: download_whisper(m, p)))

    n = len(steps)
    if n == 0:
        progress("models already present", 1.0)
        return
    for i, (label, fn) in enumerate(steps):
        progress(f"[{i + 1}/{n}] {label} ...", i / n)
        fn(lambda msg: progress(msg, i / n))
        progress(f"{label}: done", (i + 1) / n)
    progress("all models ready", 1.0)


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
