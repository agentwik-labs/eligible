"""receipt -> redact -> extract -> retrieve -> decide -> validate -> CheckResult (SPEC §2)."""

from __future__ import annotations

import time
import uuid
from decimal import Decimal
from functools import cached_property

from eligible.config import Settings, get_settings
from eligible.decide import decide
from eligible.extract import extract
from eligible.knowledge.eligibility import load_list
from eligible.llm.client import LLMClient
from eligible.llm.factory import build_client
from eligible.llm.types import LLMResponse
from eligible.models import CheckResult, Citation, FieldConfidence, ItemResult, LineItem, Stage
from eligible.redact import redact
from eligible.retrieve.chunk import Chunk, chunk_entry
from eligible.retrieve.embed import BGEEmbedder, BGEReranker
from eligible.retrieve.index import INDEX_PATH
from eligible.retrieve.search import Retriever
from eligible.tracing import Tracer
from eligible.validate import quote, totals_mismatch, validate, validate_items


class Checker:
    def __init__(
        self,
        settings: Settings | None = None,
        client: LLMClient | None = None,
        retriever: Retriever | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client
        self._retriever = retriever
        self.tracer = tracer

    @cached_property
    def client(self) -> LLMClient:
        return self._client or build_client(self.settings)

    @cached_property
    def retriever(self) -> Retriever:
        reranker = BGEReranker() if self.settings.retrieval_mode == "rerank" else None
        return self._retriever or Retriever(INDEX_PATH, BGEEmbedder(), reranker, load_list())

    @cached_property
    def list_chunks(self) -> list[Chunk]:
        return [chunk_entry(e) for e in load_list()]

    def attach_rule_sources(self, result: ItemResult) -> ItemResult:
        """Cite the IRS sections behind each cited list entry, looked up in the index."""
        rules = {e.source_id: e for e in load_list()}
        have = {c.source_id for c in result.citations}
        extra = []
        for citation in result.citations:
            entry = rules.get(citation.source_id)
            for source in entry.sources if entry else []:
                chunk = self.retriever.best_chunk_of(source, entry.rule) if entry else None
                if chunk is not None and chunk.source_id not in have:
                    have.add(chunk.source_id)
                    extra.append(
                        Citation(
                            chunk_id=chunk.id,
                            source_id=chunk.source_id,
                            title=" > ".join(chunk.heading_path),
                            quote=quote(chunk),
                        )
                    )
        return (
            result.model_copy(update={"citations": result.citations + extra}) if extra else result
        )

    def retrieve(self, query: str) -> list[Chunk]:
        return self.retriever.search(
            query, k=self.settings.retrieval_k, mode=self.settings.retrieval_mode
        )

    def check_item(self, name: str) -> tuple[ItemResult, LLMResponse]:
        """One item by name, no receipt: retrieve, decide, validate (for the MCP tool)."""
        sure = FieldConfidence(name=1.0, quantity=1.0, unit_price=1.0, amount=1.0)
        item = LineItem(
            raw_text=name,
            name=name,
            quantity=1,
            unit_price=None,
            amount=Decimal(0),
            confidence=sure,
        )
        retrieved = [self.retrieve(name)]
        decided = decide([item], retrieved, self.client)
        items, _ = validate_items([item], decided.decisions, [retrieved[0] + self.list_chunks])
        return self.attach_rule_sources(items[0]), decided.response

    def check(self, text: str) -> CheckResult:
        started = time.perf_counter()

        def now() -> float:
            return (time.perf_counter() - started) * 1000

        spans: list[Stage] = []
        t0 = now()
        redaction = redact(text)
        masked = sum(redaction.counts.values())
        spans.append(
            Stage(
                name="redact",
                start_ms=t0,
                ms=now() - t0,
                detail=f"{masked} personal-data values masked",
            )
        )

        t0 = now()
        extraction = extract(text, self.client, self.settings.extract_model, redaction)
        receipt = extraction.receipt
        spans.append(
            _llm_stage(
                "extract", t0, now() - t0, extraction.response, f"{len(receipt.items)} items"
            )
        )

        t0 = now()
        retrieved: list[list[Chunk]] = []
        per_item: list[Stage] = []
        for item in receipt.items:
            s0 = now()
            retrieved.append(self.retrieve(item.name))
            per_item.append(
                Stage(
                    name=f"retrieve: {item.name[:40]}",
                    parent="retrieve",
                    start_ms=s0,
                    ms=now() - s0,
                    detail=f"{len(retrieved[-1])} chunks",
                )
            )
        unique_chunks = len({c.id for chunks in retrieved for c in chunks})
        spans.append(
            Stage(
                name="retrieve",
                start_ms=t0,
                ms=now() - t0,
                detail=f"{unique_chunks} unique chunks for {len(receipt.items)} items",
            )
        )
        spans += per_item

        t0 = now()
        decided = decide(receipt.items, retrieved, self.client)
        spans.append(
            _llm_stage("decide", t0, now() - t0, decided.response, "one call for the whole receipt")
        )

        t0 = now()
        # The whole eligibility list is in the decide prompt, so any entry is a provided source.
        available = [chunks + self.list_chunks for chunks in retrieved]
        items, unsupported = validate(receipt, decided.decisions, available)
        items = [self.attach_rule_sources(r) for r in items]
        spans.append(
            Stage(
                name="validate",
                start_ms=t0,
                ms=now() - t0,
                detail=f"{unsupported} unsupported citations removed",
            )
        )

        result = CheckResult(
            receipt=receipt,
            items=items,
            eligible_subtotal=sum(
                (r.item.amount for r in items if r.verdict == "eligible"), Decimal(0)
            ),
            totals_mismatch=totals_mismatch(receipt),
            needs_review_count=sum(r.verdict == "needs_review" for r in items),
            trace_id=uuid.uuid4().hex,
            cost_usd=extraction.response.cost_usd + decided.response.cost_usd,
            latency_ms=now(),
            prompt_versions={
                "extract": extraction.request.prompt_version,
                "decide": decided.request.prompt_version,
            },
            unsupported_citations_before_validation=unsupported,
            stages=spans,
        )
        if self.tracer is not None:
            self.tracer.record(result)
        return result


def _llm_stage(name: str, start: float, ms: float, response: LLMResponse, detail: str) -> Stage:
    replayed = response.source == "cache"
    return Stage(
        name=name,
        start_ms=start,
        ms=ms,
        model=response.model,
        cost_usd=response.cost_usd if not replayed else response.avoided_cost_usd,
        prompt_tokens=response.usage.prompt_tokens,
        output_tokens=response.usage.output_tokens,
        cache_read_tokens=response.usage.cache_read_tokens,
        replayed=replayed,
        detail=detail,
    )
