"""Retrieval ablation (PLAN M3, EVALS.md §2.2): `uv run python -m evals.retrieval`.

Queries are the golden items' normalized names, so retrieval is measured on its own,
independent of extraction errors. Writes evals/reports/retrieval-ablation.md.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from eligible.knowledge.eligibility import load_list
from eligible.models import GoldenReceipt
from eligible.retrieve.embed import BGEEmbedder, BGEReranker
from eligible.retrieve.index import INDEX_PATH
from eligible.retrieve.search import Mode, Retriever
from evals.run import git_sha

ROOT = Path(__file__).resolve().parents[1]
K = 5
TRAP_RULE = "p969:distributions-from-an-fsa"
TRAP_DEDUCTION = "p502:nonprescription-drugs-and-medicines"
CONFIGS: list[tuple[str, Mode, bool, bool]] = [
    ("BM25 only", "bm25", False, False),
    ("Vectors only", "vector", False, False),
    ("Hybrid (RRF)", "hybrid", False, False),
    ("Hybrid + rerank", "rerank", False, False),
    ("Hybrid + rerank + exact match", "rerank", True, False),
    ("Hybrid + exact match + citation expansion", "hybrid", True, True),
    ("Hybrid + rerank + exact match + citation expansion", "rerank", True, True),
]


@dataclass
class Query:
    text: str
    gold: list[str]


@dataclass
class Result:
    name: str
    recall: float
    hit: float
    mrr: float
    trap_recall: float
    trap_inversions: int
    trap_n: int
    ms: float


def load_queries() -> list[Query]:
    seen: dict[str, Query] = {}
    for path in sorted((ROOT / "data" / "golden").glob("r*.json")):
        for item in GoldenReceipt.model_validate_json(path.read_text()).items:
            seen.setdefault(item.name, Query(item.name, item.gold_source_ids))
    return list(seen.values())


def evaluate(
    retriever: Retriever, queries: list[Query], name: str, mode: Mode, exact: bool, expand: bool
) -> Result:
    recalls, hits, rr, latencies = [], [], [], []
    trap_recall, inversions, trap_n = [], 0, 0
    for q in queries:
        started = time.perf_counter()
        sources = [
            c.source_id
            for c in retriever.search(q.text, k=K, mode=mode, exact=exact, expand=expand)
        ]
        latencies.append((time.perf_counter() - started) * 1000)
        found = [g for g in q.gold if g in sources]
        recalls.append(len(found) / len(q.gold))
        hits.append(1.0 if found else 0.0)
        first = next((i for i, s in enumerate(sources) if s in q.gold), None)
        rr.append(0.0 if first is None else 1.0 / (first + 1))
        if TRAP_RULE in q.gold:  # OTC items: the HSA/FSA rule must beat the deduction rule
            trap_n += 1
            trap_recall.append(1.0 if TRAP_RULE in sources else 0.0)
            if TRAP_DEDUCTION in sources and (
                TRAP_RULE not in sources or sources.index(TRAP_DEDUCTION) < sources.index(TRAP_RULE)
            ):
                inversions += 1
    return Result(
        name,
        statistics.mean(recalls),
        statistics.mean(hits),
        statistics.mean(rr),
        statistics.mean(trap_recall) if trap_recall else 0.0,
        inversions,
        trap_n,
        statistics.median(latencies),
    )


def render(results: list[Result], n: int) -> str:
    best = results[-1]
    lines = [
        "# Retrieval ablation",
        "",
        f"Date {date.today().isoformat()}, git `{git_sha()}`. {n} unique golden item names as queries,",
        f"top {K} chunks scored against each item's `gold_source_ids` (list entry + IRS sections).",
        "Embeddings `BAAI/bge-small-en-v1.5`, reranker `BAAI/bge-reranker-base`, both local.",
        "",
        f"| Configuration | Recall@{K} | Hit@{K} | MRR | OTC rule found | OTC inversions | Median latency |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.name} | {r.recall:.1%} | {r.hit:.1%} | {r.mrr:.3f} | {r.trap_recall:.1%} | "
            f"{r.trap_inversions} of {r.trap_n} | {r.ms:.0f} ms |"
        )
    target = 0.90
    verdict = "meets" if best.recall >= target else "**misses**"
    lines += [
        "",
        f"Recall@{K}: share of an item's gold sources found in the top {K}. Hit@{K}: at least one found.",
        f"OTC rule found: for OTC items, `{TRAP_RULE}` is in the top {K}. OTC inversion: the",
        f"deduction-only rule `{TRAP_DEDUCTION}` ranks above it (or appears without it), the trap",
        "described in DECISIONS.md.",
        "",
        f"The full configuration {verdict} the EVALS.md target of recall@{K} ≥ {target:.0%}.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    queries = load_queries()
    retriever = Retriever(INDEX_PATH, BGEEmbedder(), BGEReranker(), load_list())
    results = [evaluate(retriever, queries, *config) for config in CONFIGS]
    report = render(results, len(queries))
    out = ROOT / "evals" / "reports" / "retrieval-ablation.md"
    out.write_text(report)
    print(report)


if __name__ == "__main__":
    main()
