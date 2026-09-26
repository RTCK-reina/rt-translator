"""CLI wrapper around rttrans.modeldl (usable standalone).

    python tools/download_models.py all
    python tools/download_models.py nllb|speaker|segmentation|whisper [model]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rttrans import modeldl  # noqa: E402
from rttrans.config import Config  # noqa: E402

if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    cfg = Config.load()
    if what == "nllb":
        modeldl.download_nllb(cfg.nllb_dir)
    elif what == "speaker":
        modeldl.download_speaker_model(cfg.speaker_model)
    elif what == "segmentation":
        modeldl.download_segmentation(str(Path(cfg.segmentation_model).parent))
    elif what == "whisper":
        modeldl.download_whisper(sys.argv[2] if len(sys.argv) > 2
                                 else cfg.eco.whisper_model)
    else:
        modeldl.download_all(cfg)
