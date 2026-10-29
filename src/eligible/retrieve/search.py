"""Hybrid retrieval: BM25 + vectors, reciprocal rank fusion, rerank, exact-match boost."""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import sqlite_vec

from eligible.knowledge.eligibility import Entry
from eligible.retrieve.chunk import Chunk
from eligible.retrieve.embed import Embedder, Reranker
from eligible.retrieve.index import connect

Mode = Literal["bm25", "vector", "hybrid", "rerank"]
CANDIDATES = 20  # per retriever (SPEC §2.4)
RRF_K = 60


def rrf(rankings: Sequence[Sequence[int]], k: int = RRF_K) -> list[int]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, rowid in enumerate(ranking, start=1):
            scores[rowid] = scores.get(rowid, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda r: (-scores[r], r))


def fts_query(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return " OR ".join(f'"{w}"' for w in words if len(w) > 1)


def exact_match(name: str, entries: list[Entry]) -> Entry | None:
    """A list entry whose name appears as whole words in the item name, longest name first."""
    lowered = f" {re.sub(r'[^a-z0-9]+', ' ', name.lower())} "
    best: tuple[int, Entry] | None = None
    for entry in entries:
        for alias in entry.names:
            key = f" {re.sub(r'[^a-z0-9]+', ' ', alias.lower()).strip()} "
            if key.strip() and key in lowered and (best is None or len(key) > best[0]):
                best = (len(key), entry)
    return best[1] if best else None


class Retriever:
    def __init__(
        self,
        path: Path,
        embedder: Embedder,
        reranker: Reranker | None = None,
        entries: list[Entry] | None = None,
    ) -> None:
        self._conn = connect(path)
        self._embedder = embedder
        self._reranker = reranker
        self._entries = entries or []
        self._lock = threading.RLock()

    def bm25(self, query: str, k: int = CANDIDATES) -> list[int]:
        q = fts_query(query)
        if not q:
            return []
        rows = self._conn.execute(
            "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? "
            "ORDER BY bm25(chunks_fts) LIMIT ?",
            (q, k),
        )
        return [r[0] for r in rows]

    def vector(self, query: str, k: int = CANDIDATES) -> list[int]:
        blob = sqlite_vec.serialize_float32(self._embedder.embed_query(query))
        rows = self._conn.execute(
            "SELECT rowid FROM chunks_vec WHERE embedding MATCH ? AND k = ? ORDER BY distance",
            (blob, k),
        )
        return [r[0] for r in rows]

    def chunks(self, rowids: Sequence[int]) -> list[Chunk]:
        if not rowids:
            return []
        marks = ",".join("?" * len(rowids))
        rows = self._conn.execute(
            "SELECT rowid, id, source_id, doc, heading_path, text FROM chunks "  # noqa: S608
            f"WHERE rowid IN ({marks})",
            list(rowids),
        ).fetchall()
        by_id = {
            r[0]: Chunk(id=r[1], source_id=r[2], doc=r[3], heading_path=json.loads(r[4]), text=r[5])
            for r in rows
        }
        return [by_id[r] for r in rowids if r in by_id]

    def chunk_by_id(self, chunk_id: str) -> Chunk | None:
        with self._lock:
            return self._chunk_by_id(chunk_id)

    def _chunk_by_id(self, chunk_id: str) -> Chunk | None:
        row = self._conn.execute("SELECT rowid FROM chunks WHERE id = ?", (chunk_id,)).fetchone()
        return self.chunks([row[0]])[0] if row else None

    def best_chunk_of(self, source_id: str, hint: str) -> Chunk | None:
        """The chunk of a section that best matches `hint` (BM25), else its first chunk."""
        with self._lock:
            return self._best_chunk_of(source_id, hint)

    def _best_chunk_of(self, source_id: str, hint: str) -> Chunk | None:
        rowids = [
            r[0]
            for r in self._conn.execute(
                "SELECT rowid FROM chunks WHERE source_id = ?", (source_id,)
            )
        ]
        if not rowids:
            return None
        q = fts_query(hint)
        if q and len(rowids) > 1:
            marks = ",".join("?" * len(rowids))
            ranked = self._conn.execute(
                "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? "  # noqa: S608
                f"AND rowid IN ({marks}) ORDER BY bm25(chunks_fts) LIMIT 1",
                [q, *rowids],
            ).fetchone()
            if ranked:
                return self.chunks([ranked[0]])[0]
        return self.chunks([rowids[0]])[0]

    def expand_citations(self, ranked: list[Chunk]) -> list[Chunk]:
        """After each list entry, insert the IRS sections it cites.

        Receipt words ("ibuprofen") never appear in IRS prose ("over-the-counter medicine"),
        so the list entry is the bridge from an item to the law that governs it.
        """
        entries = {e.source_id: e for e in self._entries}
        out: list[Chunk] = []
        for chunk in ranked:
            if chunk.id in {c.id for c in out}:
                continue
            out.append(chunk)
            entry = entries.get(chunk.source_id)
            if entry is None:
                continue
            for source in entry.sources:
                cited = self._best_chunk_of(source, entry.rule)
                if cited is not None and cited.source_id not in {c.source_id for c in out}:
                    out.append(cited)
        return out

    def search(
        self, query: str, k: int = 5, mode: Mode = "rerank", exact: bool = True, expand: bool = True
    ) -> list[Chunk]:
        with self._lock:
            return self._search(query, k, mode, exact, expand)

    def _search(
        self,
        query: str,
        k: int = 5,
        mode: Mode = "rerank",
        exact: bool = True,
        expand: bool = True,
    ) -> list[Chunk]:
        if mode == "bm25":
            ranked = self.bm25(query)
        elif mode == "vector":
            ranked = self.vector(query)
        else:
            ranked = rrf([self.bm25(query), self.vector(query)])
        candidates = self.chunks(ranked[:CANDIDATES])
        if mode == "rerank" and self._reranker is not None and candidates:
            scores = self._reranker.scores(query, [c.search_text for c in candidates])
            candidates = [
                c for _, c in sorted(zip(scores, candidates, strict=True), key=lambda p: -p[0])
            ]
        if exact and (entry := exact_match(query, self._entries)):
            pinned = self._chunk_by_id(f"{entry.source_id}#0")
            if pinned is not None:
                candidates = [pinned] + [c for c in candidates if c.id != pinned.id]
        if expand:
            candidates = self.expand_citations(candidates)
        return candidates[:k]
