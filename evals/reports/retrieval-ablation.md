# Retrieval ablation

Date 2026-10-28, git `38aceee`. 197 unique golden item names as queries,
top 5 chunks scored against each item's `gold_source_ids` (list entry + IRS sections).
Embeddings `BAAI/bge-small-en-v1.5`, reranker `BAAI/bge-reranker-base`, both local.

| Configuration | Recall@5 | Hit@5 | MRR | OTC rule found | OTC inversions | Median latency |
|---|---|---|---|---|---|---|
| BM25 only | 48.4% | 89.8% | 0.827 | 0.0% | 1 of 46 | 0 ms |
| Vectors only | 50.4% | 94.4% | 0.876 | 0.0% | 0 of 46 | 7 ms |
| Hybrid (RRF) | 52.8% | 94.9% | 0.881 | 0.0% | 1 of 46 | 7 ms |
| Hybrid + rerank | 49.2% | 92.4% | 0.819 | 2.2% | 0 of 46 | 1626 ms |
| Hybrid + rerank + exact match | 50.6% | 95.4% | 0.915 | 2.2% | 0 of 46 | 1738 ms |
| Hybrid + exact match + citation expansion | 93.8% | 95.9% | 0.895 | 97.8% | 0 of 46 | 11 ms |
| Hybrid + rerank + exact match + citation expansion | 95.7% | 97.5% | 0.919 | 95.7% | 0 of 46 | 1595 ms |

Recall@5: share of an item's gold sources found in the top 5. Hit@5: at least one found.
OTC rule found: for OTC items, `p969:distributions-from-an-fsa` is in the top 5. OTC inversion: the
deduction-only rule `p502:nonprescription-drugs-and-medicines` ranks above it (or appears without it), the trap
described in DECISIONS.md.

The full configuration meets the EVALS.md target of recall@5 ≥ 90%.
