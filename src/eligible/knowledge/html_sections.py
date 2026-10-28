"""Split an IRS publication page into sections keyed by their heading path."""

from __future__ import annotations

import re
from html.parser import HTMLParser

from pydantic import BaseModel

HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
SKIP_TAGS = {"script", "style", "nav", "noscript", "svg", "button", "form"}
BLOCK_TAGS = {"p", "li", "div", "tr", "td", "th", "dd", "dt", "br", "table", "section"}


class Section(BaseModel):
    id: str
    doc: str
    level: int
    heading_path: list[str]
    text: str


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


class _Collector(HTMLParser):
    def __init__(self, start_heading: str) -> None:
        super().__init__(convert_charrefs=True)
        self._start = start_heading
        self.started = False
        self._skip_depth = 0
        self._heading: tuple[int, list[str]] | None = None
        self.blocks: list[tuple[int, str] | str] = []  # (level, heading) or body text
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIP_TAGS:
            self._skip_depth += 1
        elif tag in HEADING_TAGS:
            self._flush()
            self._heading = (int(tag[1]), [])
        elif tag in BLOCK_TAGS:
            self._buf.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in HEADING_TAGS and self._heading is not None:
            level, parts = self._heading
            title = " ".join("".join(parts).split())
            self._heading = None
            if not self.started and title.startswith(self._start):
                self.started = True
            if self.started and title:
                self.blocks.append((level, title))
        elif tag in BLOCK_TAGS:
            self._buf.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._heading is not None:
            self._heading[1].append(data)
        elif self.started:
            self._buf.append(data)

    def _flush(self) -> None:
        if self._buf:
            self.blocks.append("".join(self._buf))
            self._buf = []

    def close(self) -> None:
        super().close()
        self._flush()


def _clean(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


CALLOUTS = {"Tip", "Caution", "Example", "Note", "Exception", "Recordkeeping"}
LEAF_PREFIXES = ("Worksheet",)


def parse_sections(
    html: str,
    doc: str,
    start_heading: str,
    stop_heading: str,
    group_headings: tuple[str, ...] = (),
) -> list[Section]:
    """Sections from the first heading starting with `start_heading` up to `stop_heading`.

    IRS pages put a list's title and its entries at the same heading level; titles in
    `group_headings` are promoted half a level so entries nest under them. Callout boxes
    ("Caution", "Tip") stay inside the section they interrupt.
    """
    collector = _Collector(start_heading)
    collector.feed(html)
    collector.close()

    sections: list[Section] = []
    path: list[tuple[float, str]] = []
    seen: set[str] = set()
    current: Section | None = None
    for block in collector.blocks:
        if isinstance(block, str):
            if current is not None:
                current.text += block
            continue
        raw_level, title = block
        if title.startswith(stop_heading):
            break
        if title.rstrip(":") in CALLOUTS:
            if current is not None:
                current.text += f"\n{title.rstrip(':')}: "
            continue
        level = raw_level - 0.5 if title.startswith(group_headings) else float(raw_level)
        leaf = title.startswith(LEAF_PREFIXES)  # a boxed worksheet never parents what follows
        if leaf:
            heading_path = [t for _, t in path] + [title]
        else:
            while path and path[-1][0] >= level:
                path.pop()
            path.append((level, title))
            heading_path = [t for _, t in path]
        section_id = f"{doc}:{slugify(title)}"
        if section_id in seen:  # repeated heading (e.g. "Example"): qualify with its parent
            parent = heading_path[-2] if len(heading_path) > 1 else "x"
            section_id = f"{doc}:{slugify(parent)}--{slugify(title)}"
        n = 2
        base = section_id
        while section_id in seen:
            section_id, n = f"{base}-{n}", n + 1
        seen.add(section_id)
        current = Section(
            id=section_id, doc=doc, level=raw_level, heading_path=heading_path, text=""
        )
        sections.append(current)
    for s in sections:
        s.text = _clean(s.text)
    return sections
