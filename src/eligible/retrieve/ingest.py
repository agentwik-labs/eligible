"""Build the knowledge index: `uv run python -m eligible.retrieve.ingest`."""

from __future__ import annotations

import time

from eligible.knowledge.eligibility import load_list
from eligible.knowledge.sources import load_sections
from eligible.retrieve.chunk import Chunk, chunk_entry, chunk_section
from eligible.retrieve.embed import BGEEmbedder
from eligible.retrieve.index import INDEX_PATH, build


def all_chunks() -> list[Chunk]:
    chunks = [c for s in load_sections().values() for c in chunk_section(s)]
    return chunks + [chunk_entry(e) for e in load_list()]


def main() -> None:
    started = time.perf_counter()
    chunks = all_chunks()
    build(chunks, BGEEmbedder(), INDEX_PATH)
    print(f"{len(chunks)} chunks -> {INDEX_PATH} in {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    main()
