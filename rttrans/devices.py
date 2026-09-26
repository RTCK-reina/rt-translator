"""Audio input device enumeration (microphones + WASAPI loopback outputs)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AudioDevice:
    id: str
    name: str
    is_loopback: bool

    @property
    def label(self) -> str:
        tag = "[出力]" if self.is_loopback else "[マイク]"
        return f"{tag} {self.name}"


def list_devices() -> list[AudioDevice]:
    """Return all capture devices; loopback devices capture speaker output."""
    import soundcard as sc  # lazy: imports WASAPI COM

    out: list[AudioDevice] = []
    try:
        mics = sc.all_microphones(include_loopback=True)
    except Exception:
        mics = sc.all_microphones()
    for m in mics:
        is_lb = bool(getattr(m, "isloopback", False))
        out.append(AudioDevice(id=m.id, name=m.name, is_loopback=is_lb))
    return out


def default_loopback() -> AudioDevice | None:
    """Loopback device for the default speaker, if any."""
    import soundcard as sc

    try:
        spk = sc.default_speaker()
        mic = sc.get_microphone(spk.id, include_loopback=True)
        return AudioDevice(id=mic.id, name=mic.name, is_loopback=True)
    except Exception:
        for d in list_devices():
            if d.is_loopback:
                return d
    return None
