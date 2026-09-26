"""NLLB-200 translation via CTranslate2 + SentencePiece."""
from __future__ import annotations

import threading
from pathlib import Path

from .langs import nllb_code

_SPECIAL = {"</s>", "<s>", "<pad>", "<unk>"}


class NllbTranslator:
    """Lazy CT2 translator. Source text is prefixed with its FLORES code."""

    def __init__(self, model_dir: str, device: str = "cuda",
                 compute_type: str = "int8_float16"):
        self.model_dir = model_dir
        self.device = device
        self.compute_type = compute_type
        self._tr = None
        self._sp = None
        self._lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self._tr is not None

    def model_ready(self) -> bool:
        d = Path(self.model_dir)
        return (d / "model.bin").exists() and (d / "sentencepiece.bpe.model").exists()

    def load(self) -> None:
        from .cudaenv import register_cuda_dlls
        register_cuda_dlls()
        import ctranslate2
        import sentencepiece as spm

        with self._lock:
            if self._tr is not None:
                return
            self._tr = ctranslate2.Translator(
                self.model_dir, device=self.device,
                compute_type=self.compute_type,
                inter_threads=1, intra_threads=2,
            )
            sp_path = Path(self.model_dir) / "sentencepiece.bpe.model"
            self._sp = spm.SentencePieceProcessor(model_file=str(sp_path))

    def unload(self) -> None:
        with self._lock:
            self._tr = None
            self._sp = None

    def translate(self, text: str, src_lang: str, tgt_lang: str,
                  beam_size: int = 2) -> str | None:
        """src_lang/tgt_lang are whisper codes; returns None if unsupported."""
        src = nllb_code(src_lang)
        tgt = nllb_code(tgt_lang)
        if src is None or tgt is None or not text.strip():
            return None
        if src == tgt:
            return text
        with self._lock:
            assert self._tr is not None and self._sp is not None
            pieces = self._sp.encode(text.strip(), out_type=str)
            tokens = [src] + pieces + ["</s>"]
            results = self._tr.translate_batch(
                [tokens],
                target_prefix=[[tgt]],
                beam_size=beam_size,
                max_decoding_length=256,
                repetition_penalty=1.1,
            )
            out_tokens = results[0].hypotheses[0]
            out_tokens = [t for t in out_tokens if t not in _SPECIAL and not _is_lang_token(t)]
            return self._sp.decode(out_tokens).strip()

    def translate_batch(self, texts: list[str], src_lang: str, tgt_lang: str,
                        beam_size: int = 2) -> list[str | None]:
        src = nllb_code(src_lang)
        tgt = nllb_code(tgt_lang)
        if src is None or tgt is None:
            return [None] * len(texts)
        if src == tgt:
            return list(texts)
        with self._lock:
            assert self._tr is not None and self._sp is not None
            batch = [[src] + self._sp.encode(t.strip(), out_type=str) + ["</s>"]
                     for t in texts]
            results = self._tr.translate_batch(
                batch, target_prefix=[[tgt]] * len(batch),
                beam_size=beam_size, max_decoding_length=256,
                repetition_penalty=1.1,
            )
            out = []
            for r in results:
                toks = [t for t in r.hypotheses[0]
                        if t not in _SPECIAL and not _is_lang_token(t)]
                out.append(self._sp.decode(toks).strip())
            return out


def _is_lang_token(tok: str) -> bool:
    # FLORES-200 codes look like "eng_Latn", "jpn_Jpan"
    return len(tok) == 8 and tok[3] == "_" and tok[:3].islower()
