"""Speaker identification via sherpa-onnx embedding extractor.

Live mode: per-segment embedding + online cosine clustering.
Offline:   pyannote segmentation + embeddings + clustering (recordings).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

MIN_EMBED_S = 0.4  # too short to embed reliably -> inherit previous label


def _norm(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


class SpeakerEmbedder:
    """Lazy sherpa_onnx.SpeakerEmbeddingExtractor (CPU, ONNX)."""

    def __init__(self, model_path: str, num_threads: int = 1):
        self.model_path = model_path
        self.num_threads = num_threads
        self._ext = None
        self._lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self._ext is not None

    def available(self) -> bool:
        return Path(self.model_path).exists()

    def load(self) -> None:
        import sherpa_onnx

        with self._lock:
            if self._ext is not None:
                return
            cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                model=self.model_path,
                num_threads=self.num_threads,
                provider="cpu",
            )
            if not cfg.validate():
                raise RuntimeError(f"invalid speaker model config: {self.model_path}")
            self._ext = sherpa_onnx.SpeakerEmbeddingExtractor(cfg)

    def embed(self, audio16k: np.ndarray) -> np.ndarray:
        with self._lock:
            assert self._ext is not None
            stream = self._ext.create_stream()
            stream.accept_waveform(sample_rate=16000, waveform=audio16k)
            stream.input_finished()
            if not self._ext.is_ready(stream):
                return np.zeros(0, np.float32)
            return np.asarray(self._ext.compute(stream), dtype=np.float32)


@dataclass
class _Cluster:
    label: str
    centroid: np.ndarray
    count: int = 1


class OnlineSpeakerTracker:
    """Assign SPEAKER_XX labels to segments via incremental clustering."""

    def __init__(self, embedder: SpeakerEmbedder, threshold: float = 0.65,
                 max_speakers: int = 10):
        self.embedder = embedder
        self.threshold = threshold
        self.max_speakers = max_speakers
        self.clusters: list[_Cluster] = []
        self._last_label = "?"
        self._seg_idx = 0

    def reset(self) -> None:
        self.clusters.clear()
        self._last_label = "?"
        self._seg_idx = 0

    def identify(self, audio16k: np.ndarray) -> str:
        self._seg_idx += 1
        if len(audio16k) < int(16000 * MIN_EMBED_S):
            return self._last_label
        try:
            emb = _norm(self.embedder.embed(audio16k))
        except Exception:
            return self._last_label
        if emb.size == 0:
            return self._last_label

        best, best_sim = None, -1.0
        for c in self.clusters:
            sim = float(np.dot(emb, c.centroid))
            if sim > best_sim:
                best, best_sim = c, sim

        if best is not None and best_sim >= self.threshold:
            # running-average centroid update
            best.centroid = _norm(best.centroid * best.count + emb)
            best.count += 1
            self._last_label = best.label
            return best.label

        if len(self.clusters) < self.max_speakers:
            label = f"SPEAKER_{len(self.clusters):02d}"
            self.clusters.append(_Cluster(label, emb))
            self._last_label = label
            return label

        # cap reached -> nearest cluster even if below threshold
        if best is not None:
            self._last_label = best.label
            return best.label
        return self._last_label


def diarize_offline(audio16k: np.ndarray, segmentation_model: str,
                    embedding_model: str, num_speakers: int = -1,
                    cluster_threshold: float = 0.5,
                    num_threads: int = 4) -> list[tuple[float, float, int]]:
    """Offline diarization for recordings -> [(start_s, end_s, speaker_idx)]."""
    import sherpa_onnx

    cfg = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=segmentation_model),
            num_threads=num_threads,
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=embedding_model, num_threads=num_threads),
        clustering=sherpa_onnx.FastClusteringConfig(
            num_clusters=num_speakers, threshold=cluster_threshold),
        min_duration_on=0.3,
        min_duration_off=0.5,
    )
    if not cfg.validate():
        raise RuntimeError("invalid diarization config (check model paths)")
    sd = sherpa_onnx.OfflineSpeakerDiarization(cfg)
    result = sd.process(
        np.ascontiguousarray(audio16k, dtype=np.float32)).sort_by_start_time()
    return [(s.start, s.end, s.speaker) for s in result]
