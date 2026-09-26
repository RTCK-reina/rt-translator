"""Application configuration persisted as JSON under %APPDATA%/RTTranslator."""
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_NAME = "RTTranslator"


def portable_root() -> Path | None:
    """Frozen exe with a `portable.txt` marker next to it -> fully portable."""
    import sys
    if getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent
        if (root / "portable.txt").exists():
            return root
    return None


def app_data_dir() -> Path:
    pr = portable_root()
    if pr is not None:
        d = pr / "data"
    else:
        base = os.environ.get("APPDATA") or str(Path.home() / ".config")
        d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def default_model_dir() -> Path:
    pr = portable_root()
    d = (pr / "models") if pr is not None else (app_data_dir() / "models")
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class ModePreset:
    """Per-mode inference parameters.

    whisper_model: faster-whisper model name or local path.
    compute_type:  ctranslate2 compute type (int8 / int8_float16 / float16).
    beam_size:     decoding beam size.
    enable_speakers: run online speaker-id embedding on each segment.
    interim_results: emit provisional transcription while speech continues.
    vad_silence_ms:  silence needed to close a segment.
    max_segment_s:   hard cap for one segment.
    """
    whisper_model: str = "base"
    compute_type: str = "int8"
    beam_size: int = 1
    enable_speakers: bool = False
    interim_results: bool = True
    vad_silence_ms: int = 400
    max_segment_s: float = 8.0


@dataclass
class OverlayConfig:
    font_size: int = 22
    max_lines: int = 4
    bg_opacity: int = 160        # 0-255
    click_through: bool = True
    show_original: bool = True
    always_on_top: bool = True


@dataclass
class Config:
    device_id: str | None = None
    mode: str = "eco"                     # "eco" | "power"
    target_lang: str = "ja"               # whisper code for translation target
    # whisper lang code -> action ("ignore" | "show" | "translate")
    lang_actions: dict = field(default_factory=lambda: {"en": "translate", "ja": "show"})
    default_lang_action: str = "translate"
    translation_enabled: bool = True

    eco: ModePreset = field(default_factory=ModePreset)
    power: ModePreset = field(default_factory=lambda: ModePreset(
        whisper_model="large-v3-turbo", compute_type="float16", beam_size=5,
        enable_speakers=True, interim_results=True, vad_silence_ms=600,
        max_segment_s=12.0))

    # model paths (empty = auto/default)
    model_dir: str = ""                   # base dir for downloads
    whisper_model_path: str = ""          # override local whisper dir (both modes if set)
    nllb_dir: str = ""                    # ct2 nllb model dir
    speaker_model: str = ""               # sherpa onnx embedding model path
    segmentation_model: str = ""          # pyannote segmentation onnx path

    speaker_threshold: float = 0.65       # cosine sim for same-speaker
    capture_rate: int = 48000
    capture_block_ms: int = 100
    interim_interval_s: float = 1.5
    device_name: str = ""                 # remembered label for the combo box

    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    record_dir: str = ""                  # default: app_data/recordings

    llm_gguf_path: str = ""               # optional llama.cpp model for abstractive summary

    # ---------- persistence ----------
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    @staticmethod
    def path() -> Path:
        return app_data_dir() / "config.json"

    @classmethod
    def load(cls) -> "Config":
        p = cls.path()
        cfg = cls()
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                cfg._apply(data)
            except Exception:
                pass  # corrupt config -> defaults
        cfg._fill_defaults()
        return cfg

    def _apply(self, data: dict) -> None:
        for k, v in data.items():
            if k == "eco" and isinstance(v, dict):
                self.eco = _preset_from(v, self.eco)
            elif k == "power" and isinstance(v, dict):
                self.power = _preset_from(v, self.power)
            elif k == "overlay" and isinstance(v, dict):
                self.overlay = _overlay_from(v)
            elif hasattr(self, k):
                setattr(self, k, v)

    def _fill_defaults(self) -> None:
        if not self.model_dir:
            self.model_dir = str(default_model_dir())
        if not self.record_dir:
            self.record_dir = str(app_data_dir() / "recordings")
        if not self.nllb_dir:
            self.nllb_dir = str(Path(self.model_dir) / "nllb-200-distilled-600M-ct2-int8")
        if not self.speaker_model:
            self.speaker_model = str(
                Path(self.model_dir) / "3dspeaker_speech_eres2net_base_200k_sv_zh-cn_16k-common.onnx")
        if not self.segmentation_model:
            self.segmentation_model = str(
                Path(self.model_dir) / "sherpa-onnx-pyannote-segmentation-3-0" / "model.onnx")

    def save(self) -> None:
        with self._lock:
            data = {f.name: getattr(self, f.name)
                    for f in self.__dataclass_fields__.values()
                    if not f.name.startswith("_")}
            data["eco"] = asdict(self.eco)
            data["power"] = asdict(self.power)
            data["overlay"] = asdict(self.overlay)
            tmp = self.path().with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path())

    def preset(self, mode: str | None = None) -> ModePreset:
        m = mode or self.mode
        return self.power if m == "power" else self.eco

    def action_for_lang(self, lang: str) -> str:
        return self.lang_actions.get(lang, self.default_lang_action)

    def resolve_whisper(self, name: str) -> str:
        """Model name -> local dir in portable package, else HF name/path."""
        p = Path(name)
        if p.is_absolute() or p.is_dir():
            return name
        pr = portable_root()
        if pr is not None:
            for cand in (pr / "models" / f"whisper-{name}",
                         pr / "models" / name):
                if cand.is_dir():
                    return str(cand)
        return name


def _preset_from(d: dict, base: ModePreset) -> ModePreset:
    kw = {f.name: d.get(f.name, getattr(base, f.name)) for f in ModePreset.__dataclass_fields__.values()}
    return ModePreset(**kw)


def _overlay_from(d: dict) -> OverlayConfig:
    kw = {f.name: d.get(f.name, getattr(OverlayConfig(), f.name))
          for f in OverlayConfig.__dataclass_fields__.values()}
    return OverlayConfig(**kw)
