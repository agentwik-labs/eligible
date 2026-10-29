"""Split sections and list entries into retrievable chunks that keep their heading path."""

from __future__ import annotations

from pydantic import BaseModel

from eligible.knowledge.eligibility import Entry
from eligible.knowledge.html_sections import Section

# SPEC §2.4: ~300 tokens with 50 overlap. Words are ~0.75 tokens in this English prose.
CHUNK_WORDS = 225
OVERLAP_WORDS = 38


class Chunk(BaseModel):
    id: str  # "<section id>#<n>"
    source_id: str  # the section or list entry it came from; what gold_source_ids name
    doc: str
    heading_path: list[str]
    text: str

    @property
    def search_text(self) -> str:
        return " > ".join(self.heading_path) + "\n" + self.text


def chunk_section(section: Section) -> list[Chunk]:
    words = section.text.split()
    step = CHUNK_WORDS - OVERLAP_WORDS
    starts = range(0, max(len(words) - OVERLAP_WORDS, 1), step)
    return [
        Chunk(
            id=f"{section.id}#{n}",
            source_id=section.id,
            doc=section.doc,
            heading_path=section.heading_path,
            text=" ".join(words[start : start + CHUNK_WORDS]),
        )
        for n, start in enumerate(starts)
    ]


def chunk_entry(entry: Entry) -> Chunk:
    """One chunk per list entry: names, verdict and rule, citing its IRS sources."""
    text = (
        f"Items: {', '.join(entry.names)}. Verdict: {entry.verdict}. {entry.rule} "
        f"Sources: {', '.join(entry.sources)}."
    )
    return Chunk(
        id=f"{entry.source_id}#0",
        source_id=entry.source_id,
        doc="elist",
        heading_path=["Eligibility list", entry.names[0]],
        text=text,
    )
