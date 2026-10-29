"""One decision call per receipt, over each item's retrieved chunks (SPEC §2.5)."""

from __future__ import annotations

import json
import re
from functools import cache
from typing import Any

from pydantic import BaseModel

from eligible.config import get_settings
from eligible.knowledge.eligibility import load_list
from eligible.llm.client import LLMClient
from eligible.llm.types import LLMRequest, LLMResponse, Message
from eligible.models import VERDICTS, LineItem, Verdict
from eligible.prompts import load_prompt
from eligible.retrieve.chunk import Chunk

DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "verdict": {"type": "string", "enum": list(VERDICTS)},
                    "reason": {"type": "string"},
                    "citation_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["index", "verdict", "reason", "citation_ids"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


class Decision(BaseModel):
    index: int
    verdict: Verdict
    reason: str
    citation_ids: list[str]


class DecideResult(BaseModel):
    decisions: list[Decision]
    request: LLMRequest
    response: LLMResponse


SENTENCES_PER_CHUNK = 3
WORDS_PER_CHUNK = 90
STOP = {"the", "and", "for", "you", "can", "your", "that", "this", "with", "are", "pay", "count"}


def trim(text: str, focus: set[str]) -> str:
    """The sentences of a chunk that share the most words with the items citing it.

    Rules live in the cached preamble; the IRS chunk only has to carry the governing
    sentence, so sending the whole ~225-word chunk is mostly uncached waste.
    """
    sentences = re.split(r"(?<=[.;:])\s+", text)
    scored = sorted(
        range(len(sentences)),
        key=lambda i: -len(focus & set(re.findall(r"[a-z]{3,}", sentences[i].lower()))),
    )
    keep = sorted(scored[:SENTENCES_PER_CHUNK])
    words = " ".join(sentences[i] for i in keep).split()
    return " ".join(words[:WORDS_PER_CHUNK]) + (" …" if len(words) > WORDS_PER_CHUNK else "")


@cache
def knowledge_preamble() -> str:
    """The eligibility list as static text: part of the cached system prompt (SPEC §2.5)."""
    lines = ["## Eligibility list", "", "id | items | verdict | rule | IRS sources"]
    for e in load_list():
        lines.append(
            f"elist:{e.id} | {', '.join(e.names)} | {e.verdict} | {e.rule} | {', '.join(e.sources)}"
        )
    return "\n".join(lines)


def render_input(items: list[LineItem], retrieved: list[list[Chunk]]) -> str:
    """Each chunk is printed once, trimmed to the sentences that matter for these items."""
    sources: dict[str, Chunk] = {}
    focus: dict[str, set[str]] = {}
    lines = ["<receipt>"]
    for i, (item, chunks) in enumerate(zip(items, retrieved, strict=True)):
        words = set(re.findall(r"[a-z]{3,}", f"{item.name} {item.raw_text}".lower())) - STOP
        for c in chunks:
            if c.doc != "elist":  # list entries are already in the system prompt
                sources.setdefault(c.id, c)
                focus.setdefault(c.id, set()).update(words)
        lines.append(
            f'{i}. "{item.raw_text}" read as "{item.name}"; sources: '
            + ", ".join(c.id for c in chunks)
        )
    lines += ["</receipt>", "<sources>"]
    for c in sources.values():
        lines.append(f"[{c.id}] {' > '.join(c.heading_path)}\n{trim(c.text, focus[c.id])}\n")
    lines.append("</sources>")
    return "\n".join(lines)


def build_request(items: list[LineItem], retrieved: list[list[Chunk]]) -> LLMRequest:
    prompt = load_prompt("decide")
    settings = get_settings()
    return LLMRequest(
        model=settings.decide_model,
        prompt_name=prompt.name,
        prompt_version=prompt.version,
        system=f"{prompt.text}\n\n{knowledge_preamble()}",
        messages=[Message(role="user", content=render_input(items, retrieved))],
        max_tokens=4096,
        effort=settings.effort,
        output_schema=DECISION_SCHEMA,
    )


def decide(items: list[LineItem], retrieved: list[list[Chunk]], client: LLMClient) -> DecideResult:
    request = build_request(items, retrieved)
    response = client.complete(request)
    raw = json.loads(response.text) if response.stop_reason == "end_turn" else {"items": []}
    decisions = [Decision.model_validate(d) for d in raw.get("items", [])]
    return DecideResult(decisions=decisions, request=request, response=response)
