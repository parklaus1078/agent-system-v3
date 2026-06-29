from __future__ import annotations

import hashlib
import math
import os
import re

from langchain_core.embeddings import Embeddings


class DeterministicEmbeddings(Embeddings):
    """Offline, hash bag-of-words — for tests and a zero-dep default. Unit-normalized.
    Defaults to 384 dims to match sentence-transformers/all-MiniLM-L6-v2, so a PGVector
    collection has the same width whichever embedding mode is selected."""

    def __init__(self, dim: int = 384):
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        # \w (Unicode) so non-ASCII text (e.g. Korean decisions) yields real tokens — an
        # ASCII-only [a-z0-9]+ produced an all-zero vector for CJK text, which then made
        # cosine similarity NaN and 500'd /memory/search and RAG-using step execution.
        for tok in re.findall(r"\w+", (text or "").lower()):
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)  # noqa: S324 (non-crypto hash)
            v[h % self.dim] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


def make_embeddings() -> Embeddings:
    if os.getenv("ASV3_EMBEDDINGS") == "huggingface":
        from langchain_huggingface import HuggingFaceEmbeddings  # lazy: heavy dep

        return HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    return DeterministicEmbeddings()
