"""Rebuild dist/RTTranslator as a portable package + release zips.

PyInstaller's COLLECT wipes dist/RTTranslator, so portable.txt and
models/ must be (re)assembled after every build — this script does both.

usage:
  .venv\\Scripts\\python.exe tools\\build_package.py            # build + assemble
  .venv\\Scripts\\python.exe tools\\build_package.py --assemble  # assemble only
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DIST = ROOT / "dist" / "RTTranslator"
MODELS = DIST / "models"

WHISPER_MODELS = ["tiny", "base", "large-v3-turbo"]


def assemble() -> None:
    from rttrans.config import Config
    from rttrans import modeldl as dm

    (DIST / "portable.txt").write_text("portable\n", encoding="ascii")
    MODELS.mkdir(parents=True, exist_ok=True)

    cfg = Config.load()
    # ensure sources exist in %APPDATA% model dir / HF cache
    dm.download_nllb(cfg.nllb_dir)
    dm.download_speaker_model(cfg.speaker_model)
    dm.download_segmentation(str(Path(cfg.segmentation_model).parent))

    def put(src: Path, dst: Path) -> None:
        if dst.exists():
            print("exists:", dst.name)
            return
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        print("copied:", dst.name)

    put(Path(cfg.nllb_dir), MODELS / Path(cfg.nllb_dir).name)
    put(Path(cfg.speaker_model), MODELS / Path(cfg.speaker_model).name)
    put(Path(cfg.segmentation_model).parent,
        MODELS / Path(cfg.segmentation_model).parent.name)

    from faster_whisper.utils import download_model
    for name in WHISPER_MODELS:
        src = Path(download_model(name))
        put(src, MODELS / f"whisper-{name}")


def make_zips() -> None:
    out = ROOT / "dist"

    def zipdir(files: list[Path], dest: Path) -> None:
        dest.unlink(missing_ok=True)
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED,
                             compresslevel=6) as z:
            for f in files:
                for p in (f.rglob("*") if f.is_dir() else [f]):
                    if p.is_file():
                        z.write(p, p.relative_to(DIST.parent))
        print(f"{dest.name}: {dest.stat().st_size / 1e6:.0f} MB")

    zipdir([DIST / "RTTranslator.exe", DIST / "_internal",
            DIST / "portable.txt"], out / "RTTranslator-app.zip")
    zipdir([MODELS / f"whisper-{m}" for m in WHISPER_MODELS],
           out / "RTTranslator-models-1.zip")
    rest = [p for p in MODELS.iterdir() if p.name not in
            {f"whisper-{m}" for m in WHISPER_MODELS}]
    zipdir(rest, out / "RTTranslator-models-2.zip")


def preserve_data() -> Path | None:
    """Move dist data/ aside so COLLECT (or the build) can't delete it."""
    data = DIST / "data"
    if not data.exists():
        return None
    bak = ROOT / "dist" / "_data_backup"
    if bak.exists():
        shutil.rmtree(bak)
    shutil.move(str(data), str(bak))
    return bak


def restore_data(bak: Path | None) -> None:
    if bak is None or not bak.exists():
        return
    dst = DIST / "data"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.move(str(bak), str(dst))


if __name__ == "__main__":
    bak = None
    if "--assemble" not in sys.argv:
        bak = preserve_data()
        try:
            subprocess.check_call(
                [sys.executable, "-m", "PyInstaller", "rt-translator.spec",
                 "--clean", "--noconfirm"], cwd=ROOT)
        finally:
            restore_data(bak)
    assemble()
    make_zips()
    print("done")
