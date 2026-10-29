from pathlib import Path

import pytest

from eligible.knowledge.eligibility import load_list
from eligible.knowledge.html_sections import Section
from eligible.retrieve.chunk import CHUNK_WORDS, OVERLAP_WORDS, chunk_entry, chunk_section
from eligible.retrieve.embed import HashEmbedder, OverlapReranker
from eligible.retrieve.index import build
from eligible.retrieve.ingest import all_chunks
from eligible.retrieve.search import Retriever, exact_match, fts_query, rrf


def section(text: str, sid: str = "p502:medicines") -> Section:
    return Section(id=sid, doc="p502", level=4, heading_path=["Pub 502", "Medicines"], text=text)


def test_chunks_overlap_and_keep_heading_path() -> None:
    words = [f"w{i}" for i in range(500)]
    chunks = chunk_section(section(" ".join(words)))
    assert len(chunks) == 3
    first, second = chunks[0].text.split(), chunks[1].text.split()
    assert len(first) == CHUNK_WORDS
    assert first[-OVERLAP_WORDS:] == second[:OVERLAP_WORDS]
    assert chunks[1].id == "p502:medicines#1"
    assert chunks[0].search_text.startswith("Pub 502 > Medicines\n")


def test_short_section_is_one_chunk() -> None:
    assert len(chunk_section(section("You can include insulin."))) == 1


def test_rrf_rewards_agreement_between_retrievers() -> None:
    assert rrf([[1, 2, 3], [3, 1, 4]])[:2] == [1, 3]


def test_fts_query_is_safe_for_receipt_text() -> None:
    assert fts_query('IBUPRF "200MG" (50CT) OR -x') == '"ibuprf" OR "200mg" OR "50ct" OR "or"'


def test_exact_match_prefers_the_longest_alias() -> None:
    entries = load_list()
    assert exact_match("children's fever reducer 4 oz", entries).id == "otc-children-medicine"
    assert exact_match("ibuprofen 200 mg, 50 count", entries).id == "otc-pain-reliever"
    assert exact_match("unicorn polish", entries) is None


@pytest.fixture(scope="module")
def retriever(tmp_path_factory: pytest.TempPathFactory) -> Retriever:
    path: Path = tmp_path_factory.mktemp("idx") / "test.db"
    build(all_chunks(), HashEmbedder(), path)
    return Retriever(path, HashEmbedder(), OverlapReranker(), load_list())


def test_citation_expansion_brings_the_law_behind_a_list_entry(retriever: Retriever) -> None:
    without = [
        c.source_id for c in retriever.search("ibuprofen 200 mg", mode="hybrid", expand=False)
    ]
    with_expansion = [c.source_id for c in retriever.search("ibuprofen 200 mg", mode="hybrid")]
    assert with_expansion[0] == "elist:otc-pain-reliever"
    assert "p969:distributions-from-an-fsa" in with_expansion[:3]
    assert "cares:sec-3702" in with_expansion[:3]
    assert "p969:distributions-from-an-fsa" not in without


def test_every_mode_returns_k_distinct_chunks(retriever: Retriever) -> None:
    for mode in ("bm25", "vector", "hybrid", "rerank"):
        results = retriever.search("contact lens solution", k=5, mode=mode)
        assert len(results) == 5
        assert len({c.id for c in results}) == 5


def test_entry_chunk_states_verdict_and_sources() -> None:
    chunk = chunk_entry(next(e for e in load_list() if e.id == "sunscreen"))
    assert "Verdict: dual_purpose" in chunk.text
    assert chunk.source_id == "elist:sunscreen"
