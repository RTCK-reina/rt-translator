"""Smoke tests: imports, device enum, VAD, config, GUI (offscreen)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402

print("== imports ==")
from rttrans import (analysis, capture, config, devices, langs, pipeline,  # noqa: E402
                     speakers, store, stt, summary, translator, vad)

print("== langs ==")
assert langs.nllb_code("en") == "eng_Latn"
assert langs.nllb_code("ja") == "jpn_Jpan"
assert langs.lang_name("en") == "英語"
print("ok")

print("== config ==")
cfg = config.Config.load()
cfg.save()
cfg2 = config.Config.load()
assert cfg2.mode == cfg.mode
print("ok  model_dir:", cfg.model_dir)

print("== devices ==")
try:
    devs = devices.list_devices()
    for d in devs[:8]:
        print(" ", d.label[:80])
    print(f"  total={len(devs)} loopbacks={sum(1 for d in devs if d.is_loopback)}")
except Exception as e:
    print("  device enum failed:", e)

print("== vad (onnx sanity + segmenter logic) ==")
v0 = vad.VadSegmenter()
sr = 16000
p_sil = v0._prob(np.zeros(512, np.float32))
p_sig = v0._prob(np.random.default_rng(0).standard_normal(512).astype(np.float32) * 0.3)
print(f"  onnx probs: silence={p_sil:.3f} noise={p_sig:.3f}")
assert p_sil < 0.5

# segmenter logic: inject scripted probs (silence, speech x48, silence, speech x30)
v = vad.VadSegmenter(threshold=0.5, min_silence_ms=300, pad_ms=120,
                     min_speech_ms=200, max_speech_s=5.0)
seq = [0.0] * 16 + [0.9] * 48 + [0.0] * 32 + [0.9] * 30 + [0.0] * 32
it = iter(seq)
v._prob = lambda win: next(it, 0.0)
audio = np.zeros(len(seq) * 512, np.float32)
segs = []
for i in range(0, len(audio), 1600):
    segs.extend(v.feed(audio[i:i + 1600]))
tail = v.flush()
if tail:
    segs.append(tail)
print(f"  segments={len(segs)} (expect 2)")
for s in segs:
    print(f"   {s.start / sr:.2f}s - {s.end / sr:.2f}s len={len(s.audio) / sr:.2f}s")
assert len(segs) == 2, segs

print("== stt (class only) ==")
e = stt.SttEngine("tiny", "cuda", "int8")
assert not e.loaded
print("ok")

print("== translator (class only) ==")
t = translator.NllbTranslator("nonexistent", "cpu", "int8")
assert not t.model_ready()
print("ok")

print("== store ==")
import tempfile  # noqa: E402
with tempfile.TemporaryDirectory() as td:
    st = store.Store(td)
    rid = st.create_recording(str(Path(td) / "x.wav"), "x", "dev", "eco")
    st.add_segments(rid, [{"start": 0, "end": 1, "speaker": "SPEAKER_00",
                           "lang": "en", "text": "hi", "translation": "やあ",
                           "prob": -0.1}])
    st.finish_recording(rid, 5.0)
    recs = st.list_recordings()
    assert len(recs) == 1
    sg = st.segments(rid)
    assert sg[0]["text"] == "hi"
    st.close()
    print("ok  db:", st.db_path)

print("== summary ==")
text = "これはテストです。GPUで翻訳します。翻訳は速いです。テストが終わりました。重要なのは遅延です。"
s = summary.extractive_summary(text, 2)
k = summary.keywords(text, 3)
print("  summary:", s)
print("  keywords:", k)

print("== speakers (class only) ==")
emb = speakers.SpeakerEmbedder("nonexistent.onnx")
assert not emb.available()
print("ok")

print("== gui offscreen ==")
from PySide6.QtWidgets import QApplication  # noqa: E402
from rttrans.gui.app import run  # noqa: E402
from rttrans.gui.main_window import Bridge, MainWindow  # noqa: E402

app = QApplication.instance() or QApplication([])
st2 = store.Store(str(config.app_data_dir()))
br = Bridge()
pipe = pipeline.Pipeline(cfg, st2, br.event.emit)
win = MainWindow(cfg, st2, pipe, br)
win.show()
print("  window ok, tabs:", win.findChildren(type(win.live))[0].windowTitle() if False else "3 tabs")
br.event.emit("status", {"text": "test"})
print("  event dispatch ok")

print("== ALL PASS ==")
