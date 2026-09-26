"""Recording storage: WAV files + SQLite segment index."""
from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf

SCHEMA = """
CREATE TABLE IF NOT EXISTS recordings(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  path TEXT NOT NULL,
  name TEXT,
  started_at TEXT,
  duration_s REAL DEFAULT 0,
  device TEXT,
  mode TEXT,
  sample_rate INTEGER DEFAULT 16000,
  analyzed INTEGER DEFAULT 0,
  note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS segments(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  recording_id INTEGER NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  start_s REAL, end_s REAL,
  speaker TEXT, lang TEXT,
  text TEXT, translation TEXT,
  prob REAL
);
CREATE INDEX IF NOT EXISTS idx_segments_rec ON segments(recording_id, start_s);
"""


@dataclass
class Recording:
    id: int
    path: str
    name: str
    started_at: str
    duration_s: float
    device: str
    mode: str
    analyzed: bool
    note: str


class Store:
    def __init__(self, base_dir: str):
        self.dir = Path(base_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.dir / "recordings.db"
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------- recordings -------------

    def create_recording(self, path: str, name: str, device: str, mode: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO recordings(path,name,started_at,device,mode) VALUES(?,?,?,?,?)",
                (path, name, datetime.now().isoformat(timespec="seconds"), device, mode))
            self._conn.commit()
            return int(cur.lastrowid)

    def finish_recording(self, rec_id: int, duration_s: float) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE recordings SET duration_s=? WHERE id=?", (duration_s, rec_id))
            self._conn.commit()

    def list_recordings(self) -> list[Recording]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id,path,name,started_at,duration_s,device,mode,analyzed,note "
                "FROM recordings ORDER BY id DESC").fetchall()
        return [Recording(*r) for r in rows]

    def get_recording(self, rec_id: int) -> Recording | None:
        with self._lock:
            r = self._conn.execute(
                "SELECT id,path,name,started_at,duration_s,device,mode,analyzed,note "
                "FROM recordings WHERE id=?", (rec_id,)).fetchone()
        return Recording(*r) if r else None

    def delete_recording(self, rec_id: int, delete_file: bool = True) -> None:
        rec = self.get_recording(rec_id)
        with self._lock:
            self._conn.execute("DELETE FROM segments WHERE recording_id=?", (rec_id,))
            self._conn.execute("DELETE FROM recordings WHERE id=?", (rec_id,))
            self._conn.commit()
        if delete_file and rec:
            try:
                Path(rec.path).unlink(missing_ok=True)
            except Exception:
                pass

    def set_note(self, rec_id: int, note: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE recordings SET note=? WHERE id=?", (note, rec_id))
            self._conn.commit()

    def set_analyzed(self, rec_id: int, val: bool = True) -> None:
        with self._lock:
            self._conn.execute("UPDATE recordings SET analyzed=? WHERE id=?",
                               (int(val), rec_id))
            self._conn.commit()

    # ------------- segments -------------

    def add_segments(self, rec_id: int, segments: list[dict]) -> None:
        rows = [(rec_id, s.get("start"), s.get("end"), s.get("speaker"),
                 s.get("lang"), s.get("text"), s.get("translation"),
                 s.get("prob")) for s in segments]
        with self._lock:
            self._conn.executemany(
                "INSERT INTO segments(recording_id,start_s,end_s,speaker,lang,text,translation,prob)"
                " VALUES(?,?,?,?,?,?,?,?)", rows)
            self._conn.commit()

    def clear_segments(self, rec_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM segments WHERE recording_id=?", (rec_id,))
            self._conn.commit()

    def segments(self, rec_id: int) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id,start_s,end_s,speaker,lang,text,translation,prob "
                "FROM segments WHERE recording_id=? ORDER BY start_s", (rec_id,)).fetchall()
        return [dict(id=r[0], start=r[1], end=r[2], speaker=r[3], lang=r[4],
                     text=r[5], translation=r[6], prob=r[7]) for r in rows]

    def update_segment_speakers(self, updates: list[tuple[int, str]]) -> None:
        """updates: [(segment_id, speaker_label)]"""
        with self._lock:
            self._conn.executemany(
                "UPDATE segments SET speaker=? WHERE id=?",
                [(sp, sid) for sid, sp in updates])
            self._conn.commit()


class WavWriter:
    """Append-only 16 kHz mono PCM16 WAV writer (thread-safe)."""

    def __init__(self, path: str):
        self.path = path
        self._sf = sf.SoundFile(path, mode="w", samplerate=16000,
                                channels=1, subtype="PCM_16")
        self._lock = threading.Lock()
        self.written = 0

    def write(self, chunk: np.ndarray) -> None:
        with self._lock:
            self._sf.write(chunk)
            self.written += len(chunk)

    def close(self) -> float:
        with self._lock:
            self._sf.close()
        return self.written / 16000.0


def new_recording_path(record_dir: str) -> tuple[str, str]:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"rec_{ts}"
    return str(Path(record_dir) / f"{name}.wav"), name
