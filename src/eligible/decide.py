"""One decision call per receipt, over each item's retrieved chunks (SPEC §2.5)."""

from __future__ import annotations

import json
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
    """Each chunk is printed once, however many items retrieved it (saves input tokens)."""
    sources: dict[str, Chunk] = {}
    lines = ["<receipt>"]
    for i, (item, chunks) in enumerate(zip(items, retrieved, strict=True)):
        for c in chunks:
            if c.doc != "elist":  # list entries are already in the system prompt
                sources.setdefault(c.id, c)
        lines.append(
            f'{i}. "{item.raw_text}" read as "{item.name}"; sources: '
            + ", ".join(c.id for c in chunks)
        )
    lines += ["</receipt>", "<sources>"]
    for c in sources.values():
        lines.append(f"[{c.id}] {' > '.join(c.heading_path)}\n{c.text}\n")
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
