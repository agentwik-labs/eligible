"""Registry of the public sources and their parsing into citable sections.

uv run python -m eligible.knowledge.sources   # writes sections.jsonl and SOURCES.md
"""

from __future__ import annotations

import hashlib
import html
import re
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel
from pypdf import PdfReader

from eligible.knowledge.html_sections import Section, parse_sections, slugify

KNOWLEDGE_DIR = Path(__file__).resolve().parents[3] / "data" / "knowledge"
RAW_DIR = KNOWLEDGE_DIR / "raw"
SECTIONS_PATH = KNOWLEDGE_DIR / "sections.jsonl"
RETRIEVED = "2026-10-28"


class Source(BaseModel):
    doc: str
    title: str
    url: str
    file: str
    note: str = ""


SOURCES = [
    Source(
        doc="p502",
        title="IRS Publication 502 (2025), Medical and Dental Expenses",
        url="https://www.irs.gov/publications/p502",
        file="p502.html",
        note="Written for the itemized deduction. Its rule that non-prescribed drugs aren't "
        "includible does not apply to HSA/FSA reimbursement after 2019 (see p969, cares).",
    ),
    Source(
        doc="p502pdf",
        title="IRS Publication 502 (2025), PDF edition",
        url="https://www.irs.gov/pub/irs-pdf/p502.pdf",
        file="p502.pdf",
        note="Same content as the HTML edition. Kept for reference, not indexed.",
    ),
    Source(
        doc="p969",
        title="IRS Publication 969 (2025), Health Savings Accounts and Other Tax-Favored "
        "Health Plans",
        url="https://www.irs.gov/publications/p969",
        file="p969.html",
    ),
    Source(
        doc="cares",
        title="CARES Act, Pub. L. 116-136, §3702 (enrolled text via govinfo.gov)",
        url="https://www.govinfo.gov/content/pkg/PLAW-116publ136/html/PLAW-116publ136.htm",
        file="cares-act-plaw-116-136.htm",
        note="congress.gov returned 403 to automated download; govinfo.gov serves the same "
        "official public law. §3702 makes OTC medicine eligible by *striking* the sentence "
        "that limited medicines to prescribed drugs and insulin; the only new text is about "
        "menstrual care products. Retrieval must pair it with p969 to explain OTC verdicts.",
    ),
    Source(
        doc="n2013-71",
        title="IRS Notice 2013-71, health FSA carryover",
        url="https://www.irs.gov/pub/irs-drop/n-13-71.pdf",
        file="n-13-71.pdf",
        note="Not needed for verdicts. Indexed on purpose as an off-topic distractor.",
    ),
]

P502_GROUPS = (
    "What Medical Expenses Are Includible",
    "What Expenses Aren",
    "How Do You Treat Reimbursements",
    "How Do You Figure",
)
P969_GROUPS = (
    "Health Savings Accounts (HSAs)",
    "Medical Savings Accounts (MSAs)",
    "Flexible Spending Arrangements (FSAs)",
    "Health Reimbursement Arrangements (HRAs)",
)


def _p502(raw: str) -> list[Section]:
    return parse_sections(raw, "p502", "Publication 502", "How To Get Tax Help", P502_GROUPS)


def _p969(raw: str) -> list[Section]:
    return parse_sections(raw, "p969", "Publication 969", "How To Get Tax Help", P969_GROUPS)


def _cares(raw: str) -> list[Section]:
    text = html.unescape(re.sub(r"<[^>]+>", "", raw))
    start = text.index("SEC. 3702.")
    body = text[start : text.index("SEC. 3703.", start)]
    body = re.sub(r"<<NOTE:[^>]*>>\s*", "", body)
    heading = " ".join(body.split("\n\n", 1)[0].split())
    return [
        Section(
            id="cares:sec-3702",
            doc="cares",
            level=1,
            heading_path=["CARES Act", heading],
            text="\n".join(" ".join(p.split()) for p in body.split("\n\n")[1:] if p.strip()),
        )
    ]


def _notice(path: Path) -> list[Section]:
    text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    parts = re.split(r"\n\s*([IVX]+)\.\s+([A-Z][A-Z ,\-\u2019'()]+?)\s*\n", text)
    sections = []
    for numeral, title, body in zip(parts[1::3], parts[2::3], parts[3::3], strict=True):
        name = f"{numeral}. {title.strip().title()}"
        sections.append(
            Section(
                id=f"n2013-71:{slugify(name)}",
                doc="n2013-71",
                level=1,
                heading_path=["Notice 2013-71", name],
                text=" ".join(body.split()),
            )
        )
    return sections


PARSERS: dict[str, Callable[[Path], list[Section]]] = {
    "p502": lambda p: _p502(p.read_text()),
    "p969": lambda p: _p969(p.read_text()),
    "cares": lambda p: _cares(p.read_text(errors="replace")),
    "n2013-71": _notice,
}


def build_sections() -> list[Section]:
    sections: list[Section] = []
    for source in SOURCES:
        parser = PARSERS.get(source.doc)
        if parser is not None:
            sections.extend(s for s in parser(RAW_DIR / source.file) if s.text)
    return sections


def load_sections() -> dict[str, Section]:
    lines = SECTIONS_PATH.read_text().splitlines()
    return {s.id: s for s in (Section.model_validate_json(line) for line in lines)}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render_sources_md(sections: list[Section]) -> str:
    counts: dict[str, int] = {}
    for s in sections:
        counts[s.doc] = counts.get(s.doc, 0) + 1
    lines = [
        "# SOURCES.md",
        "",
        "Public sources only. Generated by `uv run python -m eligible.knowledge.sources`.",
        f"All files retrieved {RETRIEVED}. The SHA-256 lets anyone check the copy in `raw/`.",
        "",
        "| Doc | Title | URL | File | SHA-256 | Sections |",
        "|---|---|---|---|---|---|",
    ]
    for src in SOURCES:
        digest = sha256(RAW_DIR / src.file)[:16]
        lines.append(
            f"| `{src.doc}` | {src.title} | {src.url} | `raw/{src.file}` | `{digest}…` | "
            f"{counts.get(src.doc, 0)} |"
        )
    lines += ["", "## Notes", ""]
    lines += [f"- **{s.doc}**: {s.note}" for s in SOURCES if s.note]
    return "\n".join(lines) + "\n"


def main() -> None:
    sections = build_sections()
    SECTIONS_PATH.write_text("".join(s.model_dump_json() + "\n" for s in sections))
    (KNOWLEDGE_DIR / "SOURCES.md").write_text(render_sources_md(sections))
    print(f"{len(sections)} sections -> {SECTIONS_PATH}")


if __name__ == "__main__":
    main()
