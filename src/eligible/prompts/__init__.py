"""Versioned prompts. Each file starts with a front-matter block naming its version."""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

from pydantic import BaseModel

PROMPTS_DIR = Path(__file__).parent
FRONT_MATTER = re.compile(r"\A---\nname: (?P<name>\S+)\nversion: (?P<version>\S+)\n---\n")


class Prompt(BaseModel):
    name: str
    version: str
    text: str


@cache
def load_prompt(name: str) -> Prompt:
    raw = (PROMPTS_DIR / f"{name}.md").read_text()
    match = FRONT_MATTER.match(raw)
    if match is None or match["name"] != name:
        raise ValueError(f"prompts/{name}.md needs a front-matter block with name and version")
    return Prompt(name=name, version=match["version"], text=raw[match.end() :].strip())
