"""One trace per request (SPEC §5): JSON lines always, Langfuse when it's configured.

Each trace holds the pipeline's spans (redact, extract, retrieve per item, decide, validate)
with start offsets, latency, model, tokens and cost. The JSONL file is what the /traces page
reads. Langfuse is optional: set LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY and LANGFUSE_HOST
and install the `langfuse` package, and traces are sent there as well. A tracing failure
never fails a check.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from eligible.models import CheckResult, Stage

log = logging.getLogger(__name__)


class Trace(BaseModel):
    trace_id: str
    time: str
    merchant: str | None
    items: int
    needs_review: int
    total_ms: float
    cost_usd: Decimal
    prompt_versions: dict[str, str]
    spans: list[Stage]


class Tracer:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._langfuse = _langfuse_client()

    def record(self, result: CheckResult) -> Trace:
        trace = Trace(
            trace_id=result.trace_id,
            time=datetime.now(UTC).isoformat(timespec="seconds"),
            merchant=result.receipt.merchant,
            items=len(result.items),
            needs_review=result.needs_review_count,
            total_ms=result.latency_ms,
            cost_usd=result.cost_usd,
            prompt_versions=result.prompt_versions,
            spans=result.stages,
        )
        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a") as f:
                    f.write(trace.model_dump_json() + "\n")
            if self._langfuse is not None:
                _send_langfuse(self._langfuse, trace)
        except Exception:  # tracing must never break a check
            log.exception("could not record trace %s", trace.trace_id)
        return trace

    def recent(self, limit: int = 50) -> list[Trace]:
        if not self.path.exists():
            return []
        lines = self.path.read_text().splitlines()[-limit:]
        return [Trace.model_validate_json(line) for line in reversed(lines) if line.strip()]


def _langfuse_client() -> Any:
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        return None
    try:
        from langfuse import Langfuse  # type: ignore[import-not-found]
    except ImportError:
        log.warning("LANGFUSE_* is set but the langfuse package isn't installed; JSONL only")
        return None
    return Langfuse()


def _send_langfuse(client: Any, trace: Trace) -> None:
    """Langfuse 5.x: a root span per request, a child per pipeline span (LLM calls as
    generations with model, token usage and cost)."""
    root = client.start_observation(
        name="check",
        as_type="span",
        metadata={"trace_id": trace.trace_id, "items": trace.items, "merchant": trace.merchant},
    )
    for span in trace.spans:
        llm = bool(span.model)
        child = root.start_observation(
            name=span.name,
            as_type="generation" if llm else "span",
            model=span.model or None,
            usage_details={"input": span.prompt_tokens, "output": span.output_tokens}
            if llm
            else None,
            cost_details={"total": float(span.cost_usd)} if llm else None,
            metadata={
                "ms": span.ms,
                "start_ms": span.start_ms,
                "detail": span.detail,
                "replayed": span.replayed,
            },
        )
        child.end()
    root.end()
    client.flush()
