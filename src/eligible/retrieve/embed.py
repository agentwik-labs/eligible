"""Embedding and reranking models, behind small protocols so tests can run without them."""

from __future__ import annotations

import hashlib
import math
from functools import cached_property
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder, SentenceTransformer

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
RERANK_MODEL = "BAAI/bge-reranker-base"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "  # bge convention
DIM = 384


class Embedder(Protocol):
    dim: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class Reranker(Protocol):
    def scores(self, query: str, texts: list[str]) -> list[float]: ...


class BGEEmbedder:
    dim = DIM

    @cached_property
    def _model(self) -> SentenceTransformer:
        from sentence_transformers import SentenceTransformer

        try:  # use the downloaded copy without asking the Hub; download only the first time
            return SentenceTransformer(EMBED_MODEL, device="cpu", local_files_only=True)
        except OSError:
            return SentenceTransformer(EMBED_MODEL, device="cpu")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, normalize_embeddings=True, batch_size=32)
        return [list(map(float, v)) for v in vectors]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([QUERY_PREFIX + text])[0]


class BGEReranker:
    @cached_property
    def _model(self) -> CrossEncoder:
        from sentence_transformers import CrossEncoder

        try:
            model: CrossEncoder = CrossEncoder(RERANK_MODEL, device="cpu", local_files_only=True)
        except OSError:
            model = CrossEncoder(RERANK_MODEL, device="cpu")
        return model

    def scores(self, query: str, texts: list[str]) -> list[float]:
        return [float(s) for s in self._model.predict([(query, t) for t in texts])]


class HashEmbedder:
    """Deterministic bag-of-words vectors for unit tests: no model download, no network."""

    dim = 64

    def _vector(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for word in text.lower().split():
            v[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dim] += 1.0  # noqa: S324
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class OverlapReranker:
    """Word-overlap scores for unit tests."""

    def scores(self, query: str, texts: list[str]) -> list[float]:
        q = set(query.lower().split())
        return [len(q & set(t.lower().split())) / (len(q) or 1) for t in texts]
