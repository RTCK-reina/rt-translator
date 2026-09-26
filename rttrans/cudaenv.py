"""Register NVIDIA pip-wheel DLL dirs (cublas/cudnn) for ctranslate2.

ctranslate2 loads cublas64_12.dll / cudnn64_*.dll from PATH or DLL
directories. The `nvidia-*-cu12` wheels drop them under
site-packages/nvidia/<lib>/bin — add those before importing ctranslate2.
"""
from __future__ import annotations

import os
import site
import sys
from pathlib import Path

_registered = False


def register_cuda_dlls() -> list[str]:
    global _registered
    added: list[str] = []
    if _registered or os.name != "nt":
        _registered = True
        return added
    _registered = True

    roots = []
    # PyInstaller frozen app: nvidia/<lib>/bin under _internal (_MEIPASS)
    mp = getattr(sys, "_MEIPASS", None)
    if mp:
        roots.append(str(mp))
    if getattr(sys, "frozen", False):
        roots.append(str(Path(sys.executable).parent / "_internal"))
    try:
        roots.extend(site.getsitepackages())
    except Exception:
        pass
    roots.append(str(Path(sys.prefix) / "Lib" / "site-packages"))

    for root in dict.fromkeys(roots):
        nv = Path(root) / "nvidia"
        if not nv.exists():
            continue
        for lib_dir in sorted(nv.iterdir()):
            bin_dir = lib_dir / "bin"
            if bin_dir.is_dir():
                try:
                    os.add_dll_directory(str(bin_dir))
                    added.append(str(bin_dir))
                except OSError:
                    pass
    # also prepend to PATH for any transitive loader paths
    if added:
        os.environ["PATH"] = ";".join(added) + ";" + os.environ.get("PATH", "")
    return added
