# SPEC.md: Eligible

## 1. What it does
Input: a receipt image (JPG/PNG/PDF) or receipt text.
Output, for every line item:
- the item as read (name, quantity, amount), with a confidence score for each field;
- a verdict: `eligible`, `not_eligible`, `needs_prescription` (only with a prescription or letter of medical necessity), `dual_purpose` (eligible only with a medical reason) or `needs_review`;
- a one- or two-sentence reason in plain English;
- citations: chunk IDs, source titles and quoted spans from the knowledge base.

It also returns receipt-level totals: the eligible subtotal, a flag for whether the receipt's own total matches the sum of its lines, and trace ID, cost and latency.

## 2. Pipeline
```
receipt ─► redact ─► extract ─► normalize ─► retrieve ─► decide ─► validate ─► response
             │          │                       │           │          │
          personal   LLM (vision,           hybrid +     LLM with   citation
          data scrub structured output)     rerank       retrieved  and math
                                                         chunks     checks
```

### 2.1 Redact (`src/eligible/redact.py`)
Before any LLM call, mask card numbers (Luhn-valid 13–19 digit runs), phone numbers, emails and anything that looks like a patient name next to "Patient:" or "Name:". Image input: run the redaction on the extracted text, and never send the image to logs or traces. Unit test every pattern.

### 2.2 Extract (`src/eligible/extract/`)
One LLM call with structured output:
```python
class LineItem(BaseModel):
    raw_text: str
    name: str
    quantity: int | None
    unit_price: Decimal | None
    amount: Decimal
    confidence: dict[str, float]  # per field, 0–1


class Receipt(BaseModel):
    merchant: str | None
    merchant_type: Literal[
        "pharmacy", "grocery", "medical_provider", "optical", "dental", "big_box", "other"
    ]
    date: date | None
    items: list[LineItem]
    subtotal: Decimal | None
    tax: Decimal | None
    total: Decimal | None
    read_quality: Literal["good", "partial", "poor"]
```
Any field below 0.6 confidence is flagged and passed through. Never guess silently.

### 2.3 Normalize (`src/eligible/normalize.py`)
Expand receipt abbreviations (e.g. "IBUPRF 200MG 50CT" → "ibuprofen 200 mg, 50 count") with a small deterministic dictionary first, then fall back to the LLM. Store both forms.

### 2.4 Retrieve (`src/eligible/retrieve/`)
- Knowledge base: IRS Publication 502, IRS Publication 969, IRS Notice 2013-71 / CARES Act OTC changes, and a hand-built `eligibility_list.yaml` (~150 common items, each with a verdict and a source reference). Sources are in DATA.md §3.
- Chunking: about 300 tokens with 50 overlap, but respect section headings, and keep the heading path in metadata (e.g. `Pub 502 > What Medical Expenses Are Includible > Medicines`).
- Hybrid: BM25 (FTS5) top 20 plus vector (sqlite-vec) top 20, merged with reciprocal rank fusion (k=60), then reranked to the top 5 with `BAAI/bge-reranker-base`, run locally.
- Exact match first: if the normalized name hits `eligibility_list.yaml`, put that entry at rank 1.

### 2.5 Decide (`src/eligible/decide.py`)
One LLM call per receipt, not per line. It receives the normalized items, each item's top-5 chunks with IDs, and the system prompt from `prompts/decide.md`. It must return, for every item, `verdict`, `reason` and `citation_ids` (a subset of that item's retrieved IDs). Use prompt caching on the static system prompt and knowledge preamble.

### 2.6 Validate (`src/eligible/validate.py`)
Deterministic, with no LLM:
- every `citation_id` was actually retrieved for that item. Otherwise set the verdict to `needs_review` and the reason to "no supporting source";
- the line amounts add up to the subtotal within $0.02. Otherwise set `totals_mismatch: true`;
- any item with field confidence below 0.6 and a verdict other than `not_eligible` becomes `needs_review`.

## 3. API (`src/eligible/api.py`)
- `POST /v1/check`: multipart `file` or JSON `{ "text": "..." }`. Returns `CheckResult`.
- `GET /v1/sources/{chunk_id}`: returns the chunk text and source.
- `GET /healthz`
- `GET /`: the demo page. It shows upload → a table of items and verdicts with color badges, and clicking a citation shows the quoted source text. It also shows cost and latency.

`CheckResult` = `{ receipt: Receipt, items: [ItemResult], eligible_subtotal, totals_mismatch, needs_review_count, trace_id, cost_usd, latency_ms, prompt_versions }`.

## 4. MCP server (`src/eligible/mcp_server.py`)
Tools:
- `check_receipt(text: str) -> CheckResult`
- `check_item(name: str, merchant_type?: str) -> ItemResult` (single-item lookup)
- `search_rules(query: str, k: int = 5) -> list[Chunk]`

The README includes a config snippet for adding the server to Claude Desktop or Claude Code, plus a recorded transcript in `docs/mcp-demo.md` where an agent uses the tools to answer "Can I use my FSA for sunscreen and a massage?".

## 5. Observability
- Every request gets one trace. Spans: redact, extract, normalize, retrieve (per item), decide, validate.
- Record input/output tokens, cost (from a price table in `llm/pricing.py`), latency and model per LLM span.
- When Langfuse is off, write the same span data as JSON lines to `logs/traces.jsonl`.

## 6. Non-goals
User accounts, persistence of receipts, real plan-specific rules, mobile app, fine-tuning.

## 7. Repo layout
```
src/eligible/{api.py, redact.py, normalize.py, decide.py, validate.py, mcp_server.py,
              extract/, retrieve/, llm/{client.py,pricing.py}, prompts/, models.py}
data/{generate.py, receipts/, golden/, knowledge/}
evals/{run.py, metrics.py, judge.py, suites/, reports/}
tests/  web/  docs/  .github/workflows/{ci.yml, evals.yml}
docker-compose.yml  Dockerfile  pyproject.toml  .env.example  DECISIONS.md
```
