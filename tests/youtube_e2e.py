"""YouTube-equivalent E2E: play speech to the default speaker, capture the
matching loopback device, and run the REAL pipeline (capture->VAD->STT->NLLB).

This is exactly what happens when Chrome plays a YouTube video: audio goes
through the WASAPI render path and comes back via the loopback device.
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import soundcard as sc  # noqa: E402
import soxr  # noqa: E402

from rttrans.analysis import load_audio_16k  # noqa: E402
from rttrans.capture import CaptureThread  # noqa: E402
from rttrans.config import Config  # noqa: E402
from rttrans.devices import default_loopback  # noqa: E402
from rttrans.pipeline import Pipeline  # noqa: E402
from rttrans.store import Store  # noqa: E402

cfg = Config.load()
cfg.mode = "eco"
cfg.eco.whisper_model = "tiny"       # fast for the test; real use: base
cfg.translation_enabled = True
cfg.lang_actions = {"en": "translate", "ja": "show"}
cfg.eco.interim_results = True

speaker = sc.default_speaker()
lb = default_loopback()
print("speaker :", speaker.name)
print("loopback:", lb.name if lb else None)
assert lb is not None, "no loopback device found"

events: list[tuple[str, dict]] = []
store = Store(str(Path("tests/tmp_db_yt")))
pipe = Pipeline(cfg, store, lambda k, p: events.append((k, p)))

# Preload engines so _prepare_models is cheap and reuses them.
from rttrans.stt import SttEngine  # noqa: E402
from rttrans.translator import NllbTranslator  # noqa: E402

eng = SttEngine("tiny", "cuda", "int8")
eng.load()
tr = NllbTranslator(cfg.nllb_dir, "cpu", "int8")
tr.load()
pipe.engines.stt_engines[("tiny", "int8")] = eng
pipe.engines.translator = tr
pipe._stt = eng
pipe._tracker = None

q = pipe._q
stop = pipe._stop
preset = cfg.preset()

cap = CaptureThread(lb.id, q, capture_rate=48000, block_ms=100)
worker = threading.Thread(target=pipe._run, args=(preset,), daemon=True)
cap.start()
worker.start()
time.sleep(0.5)  # let capture settle

# Play the 2-speaker English test wav through the speaker like a video.
audio16 = load_audio_16k("tests/data/1-two-speakers-en.wav")
RATE = 48000
pcm = soxr.resample(audio16, 16000, RATE)
pcm = np.clip(pcm * 0.9, -1, 1).astype(np.float32)
stereo = np.stack([pcm, pcm], axis=1)

print(f"playing {len(pcm) / RATE:.1f}s of speech to '{speaker.name}' ...")
with speaker.player(samplerate=RATE, channels=2) as player:
    for i in range(0, len(stereo), 4800):
        player.play(stereo[i:i + 4800])

time.sleep(1.5)  # drain VAD tail
stop.set()
worker.join(timeout=15)
cap.stop()
cap.join(timeout=5)

segs = [p for k, p in events if k == "segment"]
kinds = {}
for k, _ in events:
    kinds[k] = kinds.get(k, 0) + 1
print("event counts:", kinds)
print(f"{len(segs)} segments:")
for s in segs:
    print(f"  [{s['start']:5.1f}] ({s['lang']}) {s['text']}")
    if s.get("translation"):
        print(f"          -> {s['translation']}")

if cap.error:
    print("capture error:", cap.error)
assert segs, "no speech segments captured through loopback!"
assert any(s.get("translation") for s in segs), "no translations produced"
print("== YOUTUBE-PATH E2E PASS ==")
