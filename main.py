"""Entry point for RT Translator."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        from rttrans.selftest import run_selftest
        sys.exit(run_selftest())

    from rttrans.gui.app import run
    sys.exit(run())
