# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: onedir windowed build of RT Translator.

Build:  .venv\Scripts\pyinstaller.exe rt-translator.spec --clean --noconfirm
"""
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve()
SP = ROOT / ".venv" / "Lib" / "site-packages"

datas = [(str(ROOT / "rttrans" / "assets" / "silero_vad.onnx"), "rttrans/assets")]
binaries = []
hidden = ["sherpa_onnx", "av"]

# --- CUDA runtime DLLs (cublas only; CT2 links cuDNN statically) ---
nv_root = SP / "nvidia"
if nv_root.exists():
    for libdir in sorted(nv_root.iterdir()):
        if libdir.name in ("cudnn", "cudnn.off"):
            continue  # ctranslate2 ships its own cudnn64_9.dll
        bindir = libdir / "bin"
        if bindir.is_dir():
            for dll in bindir.glob("*.dll"):
                binaries.append((str(dll), f"nvidia/{libdir.name}/bin"))

# --- packages carrying native libs / data ---
for pkg in ["sherpa_onnx", "onnxruntime", "ctranslate2", "av",
            "soundcard", "soundfile", "soxr", "huggingface_hub"]:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hidden += h
    except Exception as e:
        print(f"collect_all({pkg}) skipped: {e}")

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "torch", "torchaudio", "torchcodec", "silero_vad",
        "sympy", "networkx", "matplotlib", "pandas", "scipy",
        "IPython", "jupyter", "notebook", "tkinter", "llama_cpp",
        "PyQt5", "PyQt6", "PySide2",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RTTranslator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="RTTranslator",
)
