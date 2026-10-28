# DATA.md

All data is either **synthetic** or **public**. No real receipts, people or employer data, ever.

## 1. Synthetic receipts (`data/generate.py`)
- Seeded (record the seed). Produces `data/receipts/<id>.txt`, `data/receipts/<id>.png` (rendered with Pillow in a monospace receipt layout, with optional noise, rotation and blur for the adversarial set) and `data/golden/<id>.json`.
- Merchant types: pharmacy (40%), big box (20%), grocery (10%), optical (10%), dental or medical provider (10%), other (10%).
- 3–12 items per receipt, using realistic abbreviations ("CVS HLTH IBUPRF 200MG", "BAND AID FLX 30CT"). Includes tax, subtotal and total. 10% of receipts get a deliberate totals mismatch.
- Fake personal data for redaction tests: Luhn-valid test card numbers, 555-01xx phone numbers, `example.com` emails and obviously fake names.

## 2. Golden labels (`data/golden/<id>.json`)
```json
{ "receipt_id": "r0001",
  "merchant": "...", "merchant_type": "pharmacy", "date": "2026-03-14", "total": "23.47",
  "items": [
    { "name": "ibuprofen 200 mg, 50 count", "amount": "8.99",
      "verdict": "eligible",
      "gold_source_ids": ["elist:otc-pain-reliever", "p502:medicines"],
      "note": "OTC medicine eligible without prescription since 2020 (CARES Act)" } ],
  "totals_mismatch": false }
```
Target verdict mix across all items: eligible ~45%, not_eligible ~30%, dual_purpose ~10%, needs_prescription ~10%, needs_review ~5%.

Label every item from `eligibility_list.yaml`, which itself cites the IRS sources. Labels are generated alongside the receipts, since the generator chooses items from the list, and then **20 receipts are spot-checked by hand**. Record the check in `data/golden/AUDIT.md`.

## 3. Knowledge sources (public, `data/knowledge/raw/`)
Download them, and record the URL and retrieval date in `data/knowledge/SOURCES.md`:
- IRS Publication 502, *Medical and Dental Expenses*: https://www.irs.gov/publications/p502 (and PDF https://www.irs.gov/pub/irs-pdf/p502.pdf)
- IRS Publication 969, *HSAs and Other Tax-Favored Health Plans*: https://www.irs.gov/publications/p969
- CARES Act §3702 (OTC medicines and menstrual products without a prescription): cite the statute text from congress.gov.
- IRS Notice 2013-71 (FSA carryover). Not needed for verdicts, but include it so retrieval has to cope with irrelevant documents.

Do not scrape commercial FSA store eligibility lists. Write `eligibility_list.yaml` yourself from the IRS sources.

## 4. `eligibility_list.yaml` format
The entries below show **format only**. Do not copy their rules. Check every `rule` against the text of its cited source, and if the source doesn't settle it, use `needs_review` or `dual_purpose` and say why in `rule`.
```yaml
- id: otc-pain-reliever
  names: [ibuprofen, acetaminophen, naproxen, aspirin]
  verdict: eligible
  rule: "OTC medicines are qualified medical expenses without a prescription after 2019."
  sources: ["CARES Act §3702", "p502:medicines"]
- id: sunscreen
  names: [sunscreen, "spf 30+", "spf 50"]
  verdict: dual_purpose
  rule: "Eligible only when it is SPF 15+ and broad spectrum; treat as dual-purpose and explain the condition."
  sources: ["p502:general-health"]
```
About 150 entries covering the common pharmacy, optical, dental, first-aid, cosmetic (not eligible), vitamin (dual purpose) and grocery (not eligible) items.
