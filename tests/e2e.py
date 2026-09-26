"""End-to-end test with real models: whisper(CUDA) -> NLLB -> speakers."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

from rttrans.config import Config  # noqa: E402
from rttrans.analysis import load_audio_16k  # noqa: E402
from rttrans.speakers import (OnlineSpeakerTracker, SpeakerEmbedder,  # noqa: E402
                              diarize_offline)
from rttrans.stt import SttEngine  # noqa: E402
from rttrans.translator import NllbTranslator  # noqa: E402
from rttrans.vad import VadSegmenter  # noqa: E402

cfg = Config.load()
WAV = "tests/data/1-two-speakers-en.wav"
WAV_ZH = "tests/data/0-four-speakers-zh.wav"

print("== whisper tiny on cuda ==")
t0 = time.time()
eng = SttEngine("tiny", "cuda", "int8")
eng.load()
print(f"  load: {time.time() - t0:.1f}s")

audio = load_audio_16k(WAV)
t0 = time.time()
res = eng.transcribe(audio, beam_size=1)
print(f"  {len(audio) / 16000:.1f}s audio -> {len(res)} segments "
      f"in {time.time() - t0:.2f}s, lang={res[0].lang if res else '?'}")
for r in res[:6]:
    print(f"   [{r.start:.1f}-{r.end:.1f}] ({r.lang}) {r.text}")

print("== nllb en->ja (cpu) ==")
tr = NllbTranslator(cfg.nllb_dir, "cpu", "int8")
assert tr.model_ready(), "nllb not downloaded"
t0 = time.time()
tr.load()
print(f"  load: {time.time() - t0:.1f}s")
t0 = time.time()
outs = tr.translate_batch([r.text for r in res[:4]], "en", "ja")
print(f"  {len(outs)} texts in {time.time() - t0:.2f}s")
for r, t in zip(res[:4], outs):
    print(f"   {r.text}  ->  {t}")

print("== speaker embedding + online clustering ==")
emb = SpeakerEmbedder(cfg.speaker_model)
assert emb.available()
emb.load()
tracker = OnlineSpeakerTracker(emb, threshold=0.6)
# feed two slices of the wav (different speakers hopefully)
labels = []
for a, b in [(0, 2), (4, 6), (8, 10), (0, 2)]:
    seg = audio[a * 16000:b * 16000]
    labels.append(tracker.identify(seg))
print("  labels:", labels, " clusters:", [c.label for c in tracker.clusters])

print("== offline diarization (2-speaker en wav) ==")
t0 = time.time()
turns = diarize_offline(audio, cfg.segmentation_model, cfg.speaker_model,
                        num_speakers=-1)
print(f"  {len(turns)} turns in {time.time() - t0:.1f}s")
for a, b, sp in turns[:10]:
    print(f"   {a:5.1f}-{b:5.1f} SPEAKER_{sp}")

print("== vad on real wav ==")
v = VadSegmenter(min_silence_ms=400, pad_ms=150)
segs = []
for i in range(0, len(audio), 1600):
    segs.extend(v.feed(audio[i:i + 1600]))
if v.flush():
    segs.append(v.flush())
print(f"  {len(segs)} speech segments")
for s in segs[:6]:
    print(f"   {s.start / 16000:.1f}s - {s.end / 16000:.1f}s")

print("== pipeline simulation (queue injection) ==")
import queue  # noqa: E402
import threading  # noqa: E402
from rttrans.pipeline import Pipeline  # noqa: E402
from rttrans.store import Store  # noqa: E402

events = []
store = Store(str(Path("tests/tmp_db")))
pipe = Pipeline(cfg, store, lambda k, p: events.append((k, p)))
# bypass _prepare_models: inject preloaded engines
pipe.engines.stt_engines[("tiny", "int8")] = eng
pipe._stt = eng
pipe.engines.translator = tr
pipe._tracker = None
cfg.translation_enabled = True
cfg.lang_actions = {"en": "translate"}
cfg.mode = "eco"
cfg.eco.whisper_model = "tiny"
# monkeypatch prepare to reuse loaded engines
pipe._prepare_models = lambda: None

stop = threading.Event()
pipe._stop = stop
preset = cfg.preset()

q: queue.Queue = queue.Queue()
pipe._q = q
w = threading.Thread(target=pipe._run, args=(preset,), daemon=True)
w.start()
for i in range(0, min(len(audio), 16000 * 15), 1600):
    q.put(audio[i:i + 1600])
time.sleep(0.5)
stop.set()
w.join(timeout=15)
seg_events = [p for k, p in events if k == "segment"]
print(f"  events: {[k for k, _ in events][:20]}")
print(f"  {len(seg_events)} translated segments")
for s in seg_events[:5]:
    print(f"   [{s['start']:.1f}] ({s['lang']}) {s['text']} -> {s['translation']}")
assert seg_events, "no segments produced"
print("== E2E PASS ==")
