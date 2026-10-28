"""Generate the synthetic receipts and their golden labels (DATA.md §1-2).

    uv run python -m data.generate            # 60 receipts, seed 20261028

Every item is drawn from eligibility_list.yaml, so each golden label inherits that entry's
verdict and sources. Nothing here is real: merchants, people and card numbers are fake.
"""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from eligible.knowledge.eligibility import Entry, Product, load_list
from eligible.models import PII, VERDICTS, GoldenItem, GoldenReceipt, MerchantType, Verdict

SEED = 20261028
N_RECEIPTS = 60
ROOT = Path(__file__).resolve().parent
FONT_PATH = ROOT / "fonts" / "DejaVuSansMono.ttf"
WIDTH = 40  # characters per printed line

# DATA.md §1 merchant mix, as exact counts for 60 receipts ("dental or medical" split evenly).
MERCHANT_COUNTS: dict[MerchantType, int] = {
    "pharmacy": 24,
    "big_box": 12,
    "grocery": 6,
    "optical": 6,
    "dental": 3,
    "medical_provider": 3,
    "other": 6,
}
# DATA.md §2 target verdict mix across all items.
VERDICT_WEIGHTS: dict[Verdict, float] = {
    "eligible": 0.45,
    "not_eligible": 0.30,
    "dual_purpose": 0.10,
    "needs_prescription": 0.10,
    "needs_review": 0.05,
}
MERCHANTS: dict[MerchantType, list[tuple[str, str]]] = {
    "pharmacy": [
        ("WELLSPRING PHARMACY #0412", "1200 EXAMPLE BLVD, SPRINGFIELD"),
        ("CORNER DRUG CO", "88 SAMPLE ST, RIVERTON"),
        ("BLUE HERON PHARMACY", "410 PLACEHOLDER AVE, LAKEVIEW"),
    ],
    "big_box": [
        ("MEGAMART SUPERCENTER #2210", "5000 COMMERCE PKWY, SPRINGFIELD"),
        ("BRIGHTWAY STORES #118", "77 TESTING RD, RIVERTON"),
    ],
    "grocery": [
        ("FRESHFIELD MARKET", "23 ORCHARD LN, LAKEVIEW"),
        ("GREEN BASKET GROCERS", "910 HARVEST WAY, SPRINGFIELD"),
    ],
    "optical": [
        ("CLEARVIEW OPTICAL", "301 LENS CT, RIVERTON"),
        ("BRIGHT EYES VISION CENTER", "64 FOCUS DR, LAKEVIEW"),
    ],
    "dental": [("LAKESIDE FAMILY DENTAL", "15 MOLAR WAY, LAKEVIEW")],
    "medical_provider": [("ORANGE GROVE MEDICAL GROUP", "2 CLINIC CIR, SPRINGFIELD")],
    "other": [
        ("NORTHSIDE WELLNESS CENTER", "400 CALM ST, RIVERTON"),
        ("PEAK FITNESS & SPA", "19 SUMMIT RD, SPRINGFIELD"),
        ("DIRECTCARE ONLINE STORE", "ORDER CONFIRMATION"),
    ],
}
TAX_RATE: dict[MerchantType, Decimal] = {
    "pharmacy": Decimal("0.07"),
    "big_box": Decimal("0.07"),
    "grocery": Decimal("0.07"),
    "optical": Decimal("0.07"),
    "dental": Decimal("0"),
    "medical_provider": Decimal("0"),
    "other": Decimal("0.07"),
}
# Medicine and medical devices are untaxed in many states; everything else is taxed.
UNTAXED: set[Verdict] = {"eligible", "needs_prescription"}

FAKE_NAMES = ["TESTY MCTESTFACE", "JANE Q SAMPLE", "JOHN EXAMPLE", "PAT PLACEHOLDER"]
TEST_CARDS = ["4111111111111111", "5555555555554444", "378282246310005", "6011111111111117"]
CENT = Decimal("0.01")


@dataclass
class Line:
    entry: Entry
    product: Product
    quantity: int

    @property
    def amount(self) -> Decimal:
        return (self.product.price * self.quantity).quantize(CENT)

    @property
    def taxed(self) -> bool:
        return self.entry.verdict not in UNTAXED


def money(value: Decimal) -> str:
    return f"{value.quantize(CENT):,.2f}"


def plan_verdicts(
    rng: random.Random, slots: list[MerchantType], entries: list[Entry]
) -> list[Verdict]:
    """Assign a verdict to every item slot so the overall mix matches DATA.md §2.

    Each slot draws among the verdicts its merchant actually sells, weighted by how many
    items of each verdict are still needed. Sampling verdicts per receipt instead skews the
    mix toward whatever pharmacies carry most.
    """
    sells = {m: {e.verdict for e in entries if e.sold_at(m)} for m in set(slots)}
    remaining = {v: w * len(slots) for v, w in VERDICT_WEIGHTS.items()}
    order = list(range(len(slots)))
    rng.shuffle(order)
    plan: list[Verdict] = ["eligible"] * len(slots)
    for i in order:
        feasible = [v for v in VERDICTS if v in sells[slots[i]]]
        weights = [max(remaining[v], 0.0) for v in feasible]
        if not any(weights):
            weights = [VERDICT_WEIGHTS[v] for v in feasible]
        verdict = rng.choices(feasible, weights=weights)[0]
        remaining[verdict] -= 1
        plan[i] = verdict
    return plan


def pick_lines(
    rng: random.Random, merchant: MerchantType, verdicts: list[Verdict], entries: list[Entry]
) -> list[Line]:
    lines: list[Line] = []
    used: set[str] = set()
    for verdict in verdicts:
        pool = [
            (e, p)
            for e in entries
            if e.verdict == verdict
            for p in e.sold_at(merchant)
            if p.receipt_text not in used
        ]
        if not pool:
            continue
        entry, product = rng.choice(pool)
        used.add(product.receipt_text)
        quantity = 2 if product.price < 20 and rng.random() < 0.15 else 1
        lines.append(Line(entry, product, quantity))
    return lines


def render_text(
    merchant: str,
    address: str,
    merchant_type: MerchantType,
    day: date,
    lines: list[Line],
    subtotal_printed: Decimal,
    tax: Decimal,
    total: Decimal,
    rng: random.Random,
    pii: list[PII],
) -> str:
    out = [merchant.center(WIDTH), address.center(WIDTH)]
    out.append(f"TEL 407-555-01{rng.randint(10, 99)}".center(WIDTH))
    out.append(f"{day:%m/%d/%Y}  {rng.randint(8, 20):02d}:{rng.randint(0, 59):02d}".center(WIDTH))
    out.append("-" * WIDTH)
    for name in (p.value for p in pii if p.kind == "patient_name"):
        out.append(f"PATIENT: {name}")
    for line in lines:
        flag = " T" if line.taxed and TAX_RATE[merchant_type] else "  "
        desc = line.product.receipt_text[: WIDTH - 12]
        out.append(f"{desc:<{WIDTH - 11}}{money(line.amount):>9}{flag}")
        if line.quantity > 1:
            out.append(f"  {line.quantity} @ {money(line.product.price)}")
    out.append("-" * WIDTH)
    out.append(f"{'SUBTOTAL':<{WIDTH - 11}}{money(subtotal_printed):>9}")
    out.append(f"{'TAX':<{WIDTH - 11}}{money(tax):>9}")
    out.append(f"{'TOTAL':<{WIDTH - 11}}{money(total):>9}")
    card = next((p.value for p in pii if p.kind == "card_number"), None)
    out.append(f"CARD {card}" if card else f"VISA ************{rng.randint(1000, 9999)}")
    for p in pii:
        if p.kind == "phone":
            out.append(f"RX PICKUP PH: {p.value}")
        if p.kind == "email":
            out.append(f"E-RECEIPT SENT TO {p.value}")
    out += ["", f"ITEMS {sum(line.quantity for line in lines)}".center(WIDTH)]
    out.append("THANK YOU FOR SHOPPING".center(WIDTH))
    return "\n".join(out) + "\n"


def make_pii(rng: random.Random, merchant_type: MerchantType) -> list[PII]:
    pii: list[PII] = []
    if merchant_type in ("pharmacy", "medical_provider", "dental") and rng.random() < 0.4:
        pii.append(PII(kind="patient_name", value=rng.choice(FAKE_NAMES)))
        pii.append(PII(kind="phone", value=f"(321) 555-01{rng.randint(10, 99)}"))
    if rng.random() < 0.15:
        pii.append(PII(kind="card_number", value=rng.choice(TEST_CARDS)))
    if rng.random() < 0.15:
        pii.append(PII(kind="email", value=f"shopper{rng.randint(10, 99)}@example.com"))
    return pii


def render_png(text: str, path: Path, degrade: random.Random | None = None) -> None:
    """Monospace receipt image. `degrade` adds noise, rotation and blur (adversarial set, M5)."""
    font = ImageFont.truetype(str(FONT_PATH), 18)
    rows = text.splitlines()
    line_h, char_w, pad = 24, 11, 24
    image = Image.new("L", (WIDTH * char_w + 2 * pad, len(rows) * line_h + 2 * pad), 255)
    draw = ImageDraw.Draw(image)
    for i, row in enumerate(rows):
        draw.text((pad, pad + i * line_h), row, font=font, fill=20)
    if degrade is not None:
        for _ in range(image.width * image.height // 150):
            xy = (degrade.randrange(image.width), degrade.randrange(image.height))
            image.putpixel(xy, degrade.randint(90, 200))
        image = image.rotate(degrade.uniform(-3, 3), expand=True, fillcolor=255)
        image = image.filter(ImageFilter.GaussianBlur(degrade.uniform(0.6, 1.2)))
    image.save(path, optimize=True)


def generate(
    seed: int = SEED, n: int = N_RECEIPTS, out: Path = ROOT, images: bool = True
) -> list[GoldenReceipt]:
    rng = random.Random(seed)
    entries = load_list()
    merchant_types = [m for m, count in MERCHANT_COUNTS.items() for _ in range(count)]
    merchant_types = (merchant_types * (n // len(merchant_types) + 1))[:n]
    rng.shuffle(merchant_types)
    mismatched = set(rng.sample(range(n), k=round(n * 0.10)))
    sizes = [rng.randint(3, 12) for _ in range(n)]
    slots = [m for m, size in zip(merchant_types, sizes, strict=True) for _ in range(size)]
    plan = plan_verdicts(rng, slots, entries)
    starts = [sum(sizes[:i]) for i in range(n)]

    receipts_dir, golden_dir = out / "receipts", out / "golden"
    receipts_dir.mkdir(parents=True, exist_ok=True)
    golden_dir.mkdir(parents=True, exist_ok=True)
    receipts = []
    for i, merchant_type in enumerate(merchant_types):
        receipt_id = f"r{i + 1:04d}"
        merchant, address = rng.choice(MERCHANTS[merchant_type])
        day = date(2026, 1, 1) + timedelta(days=rng.randint(0, 270))
        verdicts = plan[starts[i] : starts[i] + sizes[i]]
        lines = pick_lines(rng, merchant_type, verdicts, entries)
        subtotal = sum((line.amount for line in lines), Decimal(0))
        taxable = sum((line.amount for line in lines if line.taxed), Decimal(0))
        tax = (taxable * TAX_RATE[merchant_type]).quantize(CENT, rounding=ROUND_HALF_UP)
        subtotal_printed = subtotal
        if i in mismatched:  # a printed subtotal that doesn't match the lines (DATA.md §1)
            subtotal_printed = subtotal - lines[rng.randrange(len(lines))].amount
            if subtotal_printed == subtotal:
                subtotal_printed += Decimal("10.00")
        total = subtotal_printed + tax
        pii = make_pii(rng, merchant_type)
        text = render_text(
            merchant, address, merchant_type, day, lines, subtotal_printed, tax, total, rng, pii
        )
        golden = GoldenReceipt(
            receipt_id=receipt_id,
            merchant=merchant,
            merchant_type=merchant_type,
            date=day,
            items=[
                GoldenItem(
                    raw_text=line.product.receipt_text,
                    name=line.product.name,
                    quantity=line.quantity,
                    unit_price=line.product.price,
                    amount=line.amount,
                    verdict=line.entry.verdict,
                    gold_source_ids=[line.entry.source_id, *line.entry.sources],
                    note=line.entry.rule,
                )
                for line in lines
            ],
            subtotal_printed=subtotal_printed,
            tax=tax,
            total=total,
            totals_mismatch=subtotal_printed != subtotal,
            pii=pii,
            seed=seed,
        )
        (receipts_dir / f"{receipt_id}.txt").write_text(text)
        if images:
            render_png(text, receipts_dir / f"{receipt_id}.png")
        (golden_dir / f"{receipt_id}.json").write_text(golden.model_dump_json(indent=2) + "\n")
        receipts.append(golden)
    return receipts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("-n", type=int, default=N_RECEIPTS)
    args = parser.parse_args()
    receipts = generate(args.seed, args.n)
    items = [item for r in receipts for item in r.items]
    print(f"{len(receipts)} receipts, {len(items)} items, seed {args.seed}")
    for verdict in VERDICTS:
        share = sum(item.verdict == verdict for item in items) / len(items)
        print(f"  {verdict:<20}{share:6.1%}  (target {VERDICT_WEIGHTS[verdict]:.0%})")


if __name__ == "__main__":
    main()
