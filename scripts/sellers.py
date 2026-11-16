"""Who wins the Amazon buy box on each pick, from the Creators API (written by the daily price pass).

data/sellers.json holds {asin: [[date, seller, condition], ...]}, the last KEEP checks per listing.

A pick is "trusted" when Amazon.com or the brand's own store sells it new. It FLIPPED when the
check before the last RUNS was trusted and the last RUNS checks were all not: a reseller, Amazon
Resale or used stock took over. That usually means a price jump and copy ("Sold by Amazon",
"budget") that the price pass can't fix, so the page goes to a full audit. A buy box that bounces
from day to day never flags, and a flip is reported once, on the check that confirms it.
"""
import json
import re
from pathlib import Path

RUNS, KEEP = 2, 30


def _letters(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def trusted(seller, condition, brand):
    if not seller or condition != "New":
        return False
    b = _letters(brand).replace("and", "")
    return seller == "Amazon.com" or bool(b) and b in _letters(seller).replace("and", "")


def load(path):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def update(path, seen, today):
    """Record today's {asin: (seller, condition)}; listings with no seller are skipped. A second
    run on the same day replaces that day's entry."""
    path = Path(path)
    hist = load(path)
    for asin, (seller, condition) in seen.items():
        if not seller:
            continue
        rows = [r for r in hist.get(asin, []) if r[0] != today] + [[today, seller, condition]]
        hist[asin] = sorted(rows)[-KEEP:]
    lines = [f"  {json.dumps(a)}: {json.dumps(v, ensure_ascii=False)}" for a, v in sorted(hist.items())]
    path.write_text("{\n" + ",\n".join(lines) + "\n}\n", encoding="utf-8")
    return hist


def _who(row):
    return row[1] if row[2] == "New" else f"{row[1]} ({row[2]})"


def flipped(hist, asin, brand):
    """(old seller, new seller) on the check that confirms a flip away from a trusted seller, else None."""
    rows = hist.get(asin) or []
    if len(rows) < RUNS + 1:
        return None
    before, last = rows[-RUNS - 1], rows[-RUNS:]
    if trusted(before[1], before[2], brand) and not any(trusted(r[1], r[2], brand) for r in last):
        return _who(before), _who(last[-1])
    return None
