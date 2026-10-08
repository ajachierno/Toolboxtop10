"""Apply a scrape-results/<date>.json capture to the category files.

For every product and avoid pick with a clean capture (live listing, featured offer,
price shown) it updates price, rating, reviews_count and bought in place, fixes the
old review count / star rating where the copy quotes them, stamps data_captured, and
adds a "What changed" entry. Files are edited as text so their hand formatting
survives. Anything it can't apply cleanly (unavailable, no featured offer, no price,
copy that quotes an old price) is listed in the report for a human to handle.

    python scripts/apply_scrape.py 2026-10-06 [--dry-run] [slug ...]
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def num(s):
    return float(s.replace("$", "").replace(",", "")) if s else None


def parse(r):
    price = num(re.sub(r"[^\d.,$]", "", r["price"])) if r.get("price") else None
    m = re.match(r"([\d.]+) out of 5", r.get("rating") or "")
    rating = float(m.group(1)) if m else None
    m = re.search(r"[\d,]+", r.get("reviews") or "")
    reviews = int(m.group(0).replace(",", "")) if m else None
    m = re.match(r"([\d.]+K?\+) bought in past month", r.get("bought") or "")
    bought = f"{m.group(1)}/mo" if m else None
    return price, rating, reviews, bought


def money(v):
    return f"${v:,.2f}".replace(".00", "")


def spans(text):
    """(asin, start, end) for each product/avoid object, by '"asin":' anchors."""
    starts = [(m.start(), m.group(1)) for m in re.finditer(r'"asin":\s*"([A-Z0-9]{10})"', text)]
    out = []
    for i, (pos, asin) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
        out.append((asin, pos, end))
    return out


def sub_field(block, key, value):
    pat = re.compile(rf'("{key}":\s*)("[^"]*"|-?[\d.]+|null)')
    if not pat.search(block):
        return block
    return pat.sub(lambda m: m.group(1) + value, block, count=1)


def apply(slug, scrape, today, dry):
    path = DATA / f"{slug}.json"
    text = path.read_text(encoding="utf-8")
    cat = json.loads(text)
    by_asin = {p["asin"]: p for p in cat["products"] + cat.get("avoid", [])}
    issues, moves, updated = [], [], 0
    pieces, last = [], 0
    for asin, a, b in spans(text):
        block = text[a:b]
        p, r = by_asin.get(asin), scrape.get(asin)
        if not p or not r:
            issues.append(f"{asin}: not captured")
            continue
        label = f"{p['brand']} {p['model']}"
        if r.get("error") or r.get("notfound"):
            issues.append(f"{label} ({asin}): {'listing gone (404)' if r.get('notfound') else r.get('error')}")
            continue
        price, rating, reviews, bought = parse(r)
        if not r.get("buybox"):
            offers = r.get("other_offers") or []
            why = (r.get("avail") or "").split(".")[0].strip() or "no featured offer"
            issues.append(f"{label} ({asin}): {why}; other sellers: {offers or 'none'}")
            continue
        if price is None:
            issues.append(f"{label} ({asin}): buy box but no price shown")
            continue
        old_price, old_rating, old_reviews = p["price"], p["rating"], p["reviews_count"]
        block = sub_field(block, "price", f"{price:.2f}")
        if rating is not None:
            block = sub_field(block, "rating", f"{rating}")
        if reviews is not None:
            block = sub_field(block, "reviews_count", str(reviews))
        if bought:
            block = sub_field(block, "bought", json.dumps(bought))
        # Copy that quotes the old review count or star rating.
        if reviews is not None and old_reviews != reviews:
            # Whole numbers only, and only in copy: a plain replace of "9" once turned $49.99 into $411.1111.
            count = re.compile(rf'(?<![\d,.]){re.escape(f"{old_reviews:,}")}(?![\d,.]|\d)')
            block = re.sub(r'("(?:verdict|pros|cons|reasons)":\s*)(\[[^\]]*\]|"(?:[^"\\]|\\.)*")',
                           lambda m: m.group(1) + count.sub(f"{reviews:,}", m.group(2)), block)
        if rating is not None and old_rating != rating:
            block = re.sub(rf"\b{re.escape(str(old_rating))}( stars| out of 5| average)", rf"{rating}\1", block)
        if old_price != price:
            for q in {money(old_price), f"${old_price:.2f}"}:
                if q in block:
                    issues.append(f"{label}: copy quotes old price {q} (now {money(price)}), review the text")
            moves.append((abs(price - old_price) / old_price, label, old_price, price))
        pieces.append(text[last:a] + block)
        last = b
        updated += 1
    text = "".join(pieces) + text[last:]
    old_date = cat.get("data_captured")
    note = changelog_note(updated, len(by_asin), moves)
    text = re.sub(r'("data_captured":\s*)"[^"]*"', rf'\1"{today}"', text, count=1)
    if '"audited"' not in text:  # keep the last full audit date for the refresh rotation
        text = re.sub(r'(\n([ \t]*)"data_captured":[^\n]*\n)',
                      lambda m: f'{m.group(1)}{m.group(2)}"audited": "{old_date}",\n', text, count=1)
    entry = json.dumps({"date": today, "note": note}, ensure_ascii=False)
    text = re.sub(r'("changelog":\s*\[\n)([ \t]*)', lambda m: f"{m.group(1)}{m.group(2)}{entry},\n{m.group(2)}",
                  text, count=1)
    json.loads(text)  # still valid JSON
    if not dry:
        path.write_text(text, encoding="utf-8")
    return updated, issues, note


def changelog_note(updated, total, moves):
    note = f"Prices, ratings and review counts re-checked on {updated} of {total} listings."
    if updated == total:
        note = "Prices, ratings and review counts re-checked on every listing."
    big = sorted([m for m in moves if m[0] >= 0.08], reverse=True)[:3]
    if big:
        parts = [f"the {lbl} {'dropped' if new < old else 'rose'} from {money(old)} to {money(new)}"
                 for _, lbl, old, new in big]
        note += " Biggest price moves: " + "; ".join(parts) + "."
    elif moves:
        note += " Price changes were all under 8%."
    else:
        note += " No price changes."
    return note


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    today, slugs = args[0], set(args[1:])
    scrape = json.loads((ROOT / "scrape-results" / f"{today}.json").read_text(encoding="utf-8"))
    site = json.loads((DATA / "site.json").read_text(encoding="utf-8"))
    for c in site["categories"]:
        if slugs and c["slug"] not in slugs:
            continue
        updated, issues, note = apply(c["slug"], scrape, today, dry)
        print(f"== {c['slug']}: {updated} updated")
        print(f"   note: {note}")
        for i in issues:
            print(f"   ! {i}")


if __name__ == "__main__":
    main()
