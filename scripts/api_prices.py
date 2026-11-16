"""Daily price pass through the Amazon Creators API: every listing, price only.

    python scripts/api_prices.py              # every category
    python scripts/api_prices.py <slug> ...   # just these

The API has no star ratings or review counts, so this writes only `price` on each product and
avoid pick, stamps the page's `prices_checked` date, and leaves `data_captured` alone: that date
is the ratings capture and the scrape rotation key (marketing/gsc/refresh_queue.py). Ratings,
reviews and audits keep coming from scrape_amazon.py + apply_scrape.py on their usual timing.

A listing is left as it was and FLAGGED when the API doesn't return it, returns no price, has no
buy-box winner, or returns a title that shares under half its words with the product name. Flags
go to scrape-results/<today>-api-flags.txt; the routine adds those pages to audit-flags.txt.
A "What changed" note is added only when some price moved 8% or more.
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"
sys.path.insert(0, str(HERE))
from apply_scrape import money, spans, sub_field  # noqa: E402

BIG = 0.08


def words(s):
    return set(re.findall(r"[a-z0-9]+", (s or "").lower()))


def _price(s):
    try:
        return float(re.sub(r"[^\d.]", "", s)) if s else None
    except ValueError:
        return None


def why_not(p, r):
    """Reason this API record can't price the listing, or None if it can."""
    if not r or r.get("notfound"):
        return "not returned by the API"
    if _price(r.get("price")) is None:
        return f"no price ({r.get('avail')})"
    if not r.get("buybox"):
        return f"no buy-box winner ({r.get('avail')})"
    a_w, o_w = words(r.get("title")), words(p.get("name"))
    if a_w and o_w and len(a_w & o_w) < 0.5 * min(len(a_w), len(o_w)):
        return f"title changed: {(r.get('title') or '')[:70]!r}"
    return None


def apply_prices(slug, recs, today, dry=False):
    """Write API prices into data/<slug>.json. Returns {"priced", "total", "moves", "flags", "issues"}."""
    path = DATA / f"{slug}.json"
    text = path.read_text(encoding="utf-8")
    cat = json.loads(text)
    by_asin = {p["asin"]: p for p in cat["products"] + cat.get("avoid", [])}
    flags, issues, moves, priced = [], [], [], 0
    pieces, last = [], 0
    for asin, a, b in spans(text):
        p = by_asin.get(asin)
        if not p:
            continue
        block = text[a:b]
        label = f"{p['brand']} {p['model']}"
        reason = why_not(p, recs.get(asin))
        if reason:
            flags.append(f"{slug} {asin} {label}: {reason}")
        else:
            price = _price(recs[asin]["price"])
            old = p["price"]
            block = sub_field(block, "price", f"{price:.2f}")
            if isinstance(old, (int, float)) and old and old != price:
                moves.append((abs(price - old) / old, label, old, price))
                for q in {money(old), f"${old:.2f}"}:
                    if q in block:
                        issues.append(f"{label}: copy quotes old price {q} (now {money(price)}), review the text")
            priced += 1
        pieces.append(text[last:a] + block)
        last = b
    text = "".join(pieces) + text[last:]
    if priced:
        if '"prices_checked"' in text:
            text = re.sub(r'("prices_checked":\s*)"[^"]*"', rf'\1"{today}"', text, count=1)
        else:
            text = re.sub(r'(\n([ \t]*)"data_captured":[^\n]*\n)',
                          lambda m: f'{m.group(1)}{m.group(2)}"prices_checked": "{today}",\n', text, count=1)
        big = sorted([m for m in moves if m[0] >= BIG], reverse=True)[:3]
        if big:
            parts = [f"the {lbl} {'dropped' if new < old else 'rose'} from {money(old)} to {money(new)}"
                     for _, lbl, old, new in big]
            note = (f"Prices re-checked on {priced} of {len(by_asin)} listings. "
                    f"Biggest price moves: {'; '.join(parts)}.")
            entry = json.dumps({"date": today, "note": note}, ensure_ascii=False)
            text = re.sub(r'("changelog":\s*\[\n)([ \t]*)',
                          lambda m: f"{m.group(1)}{m.group(2)}{entry},\n{m.group(2)}", text, count=1)
    json.loads(text)  # still valid JSON
    if not dry and priced:
        path.write_text(text, encoding="utf-8")
    return {"priced": priced, "total": len(by_asin), "moves": moves, "flags": flags, "issues": issues}


def main(slugs):
    import creators_api
    site = json.loads((DATA / "site.json").read_text(encoding="utf-8"))
    slugs = slugs or [c["slug"] for c in site["categories"]]
    pages = {s: json.loads((DATA / f"{s}.json").read_text(encoding="utf-8")) for s in slugs}
    asins = list(dict.fromkeys(p["asin"] for c in pages.values() for p in c["products"] + c.get("avoid", [])))
    items, errs = creators_api.get_items(asins)
    hard = [e for e in errs if "http" in str(e).lower()]
    if hard:
        print("API errors:", json.dumps(hard)[:800])
    if not items:
        raise SystemExit("API returned nothing: fall back to the scrape price pass today")
    recs = {a: creators_api.record(a, items.get(a)) for a in asins}
    today = dt.date.today().isoformat()
    all_flags, all_issues, n_priced, n_total, n_moved = [], [], 0, 0, 0
    for s in slugs:
        out = apply_prices(s, recs, today)
        n_priced += out["priced"]
        n_total += out["total"]
        n_moved += len(out["moves"])
        all_flags += out["flags"]
        all_issues += out["issues"]
    flag_file = ROOT / "scrape-results" / f"{today}-api-flags.txt"
    flag_file.parent.mkdir(exist_ok=True)
    flag_file.write_text("\n".join(all_flags) + ("\n" if all_flags else ""), encoding="utf-8")
    print(f"API price pass {today}: {n_priced} of {n_total} listings priced on {len(slugs)} pages, "
          f"{n_moved} price changes, {len(all_flags)} flagged -> {flag_file.name}")
    for x in all_issues:
        print("  CHECK", x)
    flagged_pages = sorted({f.split()[0] for f in all_flags})
    if flagged_pages:
        print("Pages with flagged listings:", " ".join(flagged_pages))


if __name__ == "__main__":
    main(sys.argv[1:])
