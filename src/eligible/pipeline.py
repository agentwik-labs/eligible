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
from eligible.models import CheckResult, Citation, ItemResult, Stage
from eligible.retrieve.chunk import Chunk, chunk_entry
from eligible.retrieve.embed import BGEEmbedder, BGEReranker
from eligible.retrieve.index import INDEX_PATH
from eligible.retrieve.search import Retriever
from eligible.validate import quote, totals_mismatch, validate


class Checker:
    def __init__(
        self,
        settings: Settings | None = None,
        client: LLMClient | None = None,
        retriever: Retriever | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client
        self._retriever = retriever

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

    def check(self, text: str) -> CheckResult:
        started = time.perf_counter()
        clock = started

        def lap() -> float:
            nonlocal clock
            now = time.perf_counter()
            elapsed, clock = (now - clock) * 1000, now
            return elapsed

        extraction = extract(text, self.client, self.settings.extract_model)
        extract_ms = lap()
        receipt = extraction.receipt
        retrieved = [self.retrieve(item.name) for item in receipt.items]
        retrieve_ms = lap()
        decided = decide(receipt.items, retrieved, self.client)
        decide_ms = lap()
        # The whole eligibility list is in the decide prompt, so any entry is a provided source.
        available = [chunks + self.list_chunks for chunks in retrieved]
        items, unsupported = validate(receipt, decided.decisions, available)
        items = [self.attach_rule_sources(r) for r in items]
        validate_ms = lap()
        masked = sum(extraction.redaction.counts.values())
        unique_chunks = len({c.id for chunks in retrieved for c in chunks})
        stages = [
            Stage(name="redact", ms=0.0, detail=f"{masked} personal-data values masked"),
            _llm_stage("extract", extract_ms, extraction.response, f"{len(receipt.items)} items"),
            Stage(
                name="retrieve",
                ms=retrieve_ms,
                detail=f"{unique_chunks} unique chunks for {len(receipt.items)} items",
            ),
            _llm_stage("decide", decide_ms, decided.response, "one call for the whole receipt"),
            Stage(
                name="validate",
                ms=validate_ms,
                detail=f"{unsupported} unsupported citations removed",
            ),
        ]
        return CheckResult(
            receipt=receipt,
            items=items,
            eligible_subtotal=sum(
                (r.item.amount for r in items if r.verdict == "eligible"), Decimal(0)
            ),
            totals_mismatch=totals_mismatch(receipt),
            needs_review_count=sum(r.verdict == "needs_review" for r in items),
            trace_id=uuid.uuid4().hex,
            cost_usd=extraction.response.cost_usd + decided.response.cost_usd,
            latency_ms=(time.perf_counter() - started) * 1000,
            prompt_versions={
                "extract": extraction.request.prompt_version,
                "decide": decided.request.prompt_version,
            },
            unsupported_citations_before_validation=unsupported,
            stages=stages,
        )


def _llm_stage(name: str, ms: float, response: LLMResponse, detail: str) -> Stage:
    replayed = response.source == "cache"
    return Stage(
        name=name,
        ms=ms,
        cost_usd=response.cost_usd if not replayed else response.avoided_cost_usd,
        prompt_tokens=response.usage.prompt_tokens,
        output_tokens=response.usage.output_tokens,
        cache_read_tokens=response.usage.cache_read_tokens,
        replayed=replayed,
        detail=detail,
    )
