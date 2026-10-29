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
from eligible.models import CheckResult
from eligible.retrieve.chunk import Chunk
from eligible.retrieve.embed import BGEEmbedder, BGEReranker
from eligible.retrieve.index import INDEX_PATH
from eligible.retrieve.search import Retriever
from eligible.validate import totals_mismatch, validate


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

    def retrieve(self, query: str) -> list[Chunk]:
        return self.retriever.search(
            query, k=self.settings.retrieval_k, mode=self.settings.retrieval_mode
        )

    def check(self, text: str) -> CheckResult:
        started = time.perf_counter()
        extraction = extract(text, self.client, self.settings.extract_model)
        receipt = extraction.receipt
        retrieved = [self.retrieve(item.name) for item in receipt.items]
        decided = decide(receipt.items, retrieved, self.client)
        items, unsupported = validate(receipt, decided.decisions, retrieved)
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
        )
