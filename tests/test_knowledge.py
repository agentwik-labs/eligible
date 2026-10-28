from collections import Counter

from eligible.knowledge.eligibility import load_list
from eligible.knowledge.html_sections import parse_sections
from eligible.knowledge.sources import build_sections, load_sections
from eligible.models import VERDICTS

HTML = """
<h1>Publication 1 - Main</h1>
<h4>What Is Covered?</h4><p>Intro.</p>
<h4>Bandages</h4><p>You can include bandages.</p>
<h3>Caution:</h3><p>Read this.</p>
<h3>Worksheet A. Something</h3><p>Lines.</p>
<h4>Crutches</h4><p>You can include crutches.</p>
<h4>What Is Not Covered?</h4>
<h4>Example</h4><p>One.</p>
<h4>Toothpaste</h4><p>Personal.</p>
<h4>Example</h4><p>Two.</p>
<h2>How To Get Help</h2><p>Ignored.</p>
"""


def parsed() -> dict[str, list[str]]:
    sections = parse_sections(
        HTML, "pub", "Publication 1", "How To Get", ("What Is Covered", "What Is Not")
    )
    return {s.id: s.heading_path for s in sections}


def test_list_entries_nest_under_their_group_heading() -> None:
    paths = parsed()
    assert paths["pub:crutches"][-2:] == ["What Is Covered?", "Crutches"]
    assert paths["pub:toothpaste"][-2:] == ["What Is Not Covered?", "Toothpaste"]


def test_worksheet_box_belongs_to_the_entry_before_it_but_parents_nothing() -> None:
    paths = parsed()
    assert paths["pub:worksheet-a-something"][-2] == "Bandages"
    assert "Worksheet A. Something" not in paths["pub:crutches"]


def test_callouts_stay_inside_their_section_and_stop_heading_ends_parsing() -> None:
    sections = parse_sections(HTML, "pub", "Publication 1", "How To Get", ("What Is",))
    bandages = next(s for s in sections if s.id == "pub:bandages")
    assert "Caution:\nRead this." in bandages.text
    assert not any("Ignored" in s.text for s in sections)


def test_committed_sections_match_the_raw_sources() -> None:
    """sections.jsonl must be regenerated whenever the parser or raw files change."""
    built = {s.id: s for s in build_sections()}
    assert built == load_sections()


def test_key_rules_survive_parsing() -> None:
    s = load_sections()
    assert (
        "over-the-counter medicine (whether or not prescribed)"
        in s["p969:distributions-from-an-fsa"].text
    )
    assert "menstrual care product" in s["cares:sec-3702"].text
    assert s["p502:medicines"].heading_path[-2] == "What Medical Expenses Are Includible?"


def test_every_list_entry_cites_sections_that_exist() -> None:
    sections = load_sections()
    for entry in load_list():
        missing = [src for src in entry.sources if src not in sections]
        assert not missing, f"{entry.id} cites missing {missing}"


def test_list_size_ids_and_coverage() -> None:
    entries = load_list()
    assert 140 <= len(entries) <= 170
    assert len({e.id for e in entries}) == len(entries)
    texts = Counter(p.receipt_text for e in entries for p in e.products)
    assert [t for t, n in texts.items() if n > 1] == []
    assert {e.verdict for e in entries} == set(VERDICTS)
    assert all(
        e.sold_at(m)
        for e in entries
        for m in e.merchants
        if not any(p.merchants for p in e.products)
    )
