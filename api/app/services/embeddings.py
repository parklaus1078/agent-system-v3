from __future__ import annotations

import hashlib
import math
import os
import re

from langchain_core.embeddings import Embeddings


class DeterministicEmbeddings(Embeddings):
    """Offline, hash bag-of-words — for tests and a zero-dep default. Unit-normalized."""

    def __init__(self, dim: int = 256):
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for tok in re.findall(r"[a-z0-9]+", (text or "").lower()):
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
