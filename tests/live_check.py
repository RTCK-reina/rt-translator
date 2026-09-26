"""Live check: translate whatever is currently playing on this PC.

1) Probe all loopback devices briefly, pick the one with real signal.
2) Run the full pipeline on it for N seconds and print results.
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import queue  # noqa: E402

from rttrans.capture import CaptureThread  # noqa: E402
from rttrans.config import Config  # noqa: E402
from rttrans.devices import list_devices  # noqa: E402
from rttrans.pipeline import Pipeline  # noqa: E402
from rttrans.stt import SttEngine  # noqa: E402
from rttrans.store import Store  # noqa: E402
from rttrans.translator import NllbTranslator  # noqa: E402

PROBE_S = 2.0
RUN_S = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0

cfg = Config.load()
cfg.mode = "eco"
cfg.eco.whisper_model = "base"
cfg.translation_enabled = True
cfg.lang_actions = {"en": "translate", "ja": "show"}
cfg.eco.interim_results = False

devs = list_devices()
lbs = [d for d in devs if d.is_loopback]
print(f"{len(lbs)} loopback devices, probing {PROBE_S:.0f}s each (parallel)...")


def probe(d):
    q: queue.Queue = queue.Queue()
    cap = CaptureThread(d.id, q)
    cap.start()
    time.sleep(PROBE_S)
    cap.stop()
    cap.join(3)
    n = 0.0
    cnt = 0
    while not q.empty():
        c = q.get()
        n += float(np.sqrt(np.mean(c ** 2)))
        cnt += 1
    return n / max(cnt, 1)


results = {}
threads = [threading.Thread(target=lambda d=d: results.__setitem__(d.id, probe(d)), daemon=True)
           for d in lbs]
for t in threads:
    t.start()
for t in threads:
    t.join(PROBE_S + 5)

for d in lbs:
    rms = results.get(d.id, 0.0)
    print(f"  {'>>> ' if rms == max(results.values()) and rms > 0.001 else '    '}"
          f"rms={rms:.5f}  {d.name[:70]}")

best_id = max(results, key=results.get) if results else None
best_rms = results.get(best_id, 0.0) if best_id else 0.0
if not best_id or best_rms < 0.001:
    print("\nどの出力デバイスも無音でした。動画が再生中か、別デバイス出力か確認してください。")
    sys.exit(2)

dev = next(d for d in lbs if d.id == best_id)
print(f"\n使用デバイス: {dev.name}  ({RUN_S:.0f}s 取得/翻訳中...)\n")

events = []
store = Store(str(Path("tests/tmp_db_live")))
pipe = Pipeline(cfg, store, lambda k, p: events.append((k, p)))

eng = SttEngine("base", "cuda", "int8")
eng.load()
tr = NllbTranslator(cfg.nllb_dir, "cpu", "int8")
tr.load()
pipe.engines.stt_engines[("base", "int8")] = eng
pipe.engines.translator = tr
pipe._stt = eng
pipe._tracker = None

q = pipe._q
stop = pipe._stop
preset = cfg.preset()
cap = CaptureThread(dev.id, q, capture_rate=48000, block_ms=100)
worker = threading.Thread(target=pipe._run, args=(preset,), daemon=True)
cap.start()
worker.start()

t_end = time.time() + RUN_S
out_lines: list[str] = []
while time.time() < t_end:
    time.sleep(0.5)
    for k, p in events[len(out_lines):]:
        pass  # processed below after join

stop.set()
worker.join(timeout=15)
cap.stop()
cap.join(timeout=5)

for k, p in events:
    if k == "segment":
        sp = f"[{p['speaker']}]" if p.get("speaker") else ""
        out_lines.append(f"[{p['start']:6.1f}] ({p['lang']}){sp} {p['text']}")
        if p.get("translation"):
            out_lines.append(f"          -> {p['translation']}")
    elif k == "error":
        out_lines.append(f"ERR: {p['text']}")

segs = [p for k, p in events if k == "segment"]
out_lines.append(f"\n== {len(segs)} segments in {RUN_S:.0f}s ==")
Path("tests/live_out.txt").write_text("\n".join(out_lines), encoding="utf-8")
print(f"segments={len(segs)} -> tests/live_out.txt")
