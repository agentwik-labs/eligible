"""SQLite knowledge index: chunk table, FTS5 for BM25 and sqlite-vec for vectors."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import sqlite_vec

from eligible.retrieve.chunk import Chunk
from eligible.retrieve.embed import Embedder

INDEX_PATH = Path(__file__).resolve().parents[3] / "data" / "index" / "eligible.db"


def connect(path: Path) -> sqlite3.Connection:
    # Read-only after build; the API serves it from a thread pool, guarded by Retriever's lock.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def build(chunks: list[Chunk], embedder: Embedder, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    conn = connect(path)
    with conn:
        conn.execute(
            "CREATE TABLE chunks (rowid INTEGER PRIMARY KEY, id TEXT UNIQUE, source_id TEXT, "
            "doc TEXT, heading_path TEXT, text TEXT)"
        )
        conn.execute("CREATE VIRTUAL TABLE chunks_fts USING fts5(heading, body)")
        conn.execute(f"CREATE VIRTUAL TABLE chunks_vec USING vec0(embedding float[{embedder.dim}])")
        vectors = embedder.embed_documents([c.search_text for c in chunks])
        for rowid, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True), start=1):
            conn.execute(
                "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
                (
                    rowid,
                    chunk.id,
                    chunk.source_id,
                    chunk.doc,
                    json.dumps(chunk.heading_path),
                    chunk.text,
                ),
            )
            conn.execute(
                "INSERT INTO chunks_fts(rowid, heading, body) VALUES (?, ?, ?)",
                (rowid, " ".join(chunk.heading_path), chunk.text),
            )
            conn.execute(
                "INSERT INTO chunks_vec(rowid, embedding) VALUES (?, ?)",
                (rowid, sqlite_vec.serialize_float32(vector)),
            )
    conn.close()
