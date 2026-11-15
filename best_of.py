"""Best of 2026: every category's Best Overall, Best Budget and Money No Object in one table.

Until FREEZE_DATE the page shows the live awards. The first build on or after FREEZE_DATE
writes data/best-of-2026.json; from then on the picks, ratings and review counts come only
from that file and never change. Prices keep moving: scripts/holiday_picks.py re-reads the
frozen ASINs too, and with_prices() lays the newer prices over the frozen rows at build time.
The page is noindex and unlinked until REVEAL_DATE.
"""
import json
import re
from pathlib import Path

SLUG = "best-of-2026"
FREEZE_DATE = "2026-12-31"
REVEAL_DATE = "2027-01-01"
DATA = Path(__file__).resolve().parent / "data"
FROZEN = DATA / "best-of-2026.json"
_HP = DATA / "holiday-prices.json"
HOLIDAY_PRICES = json.loads(_HP.read_text(encoding="utf-8")) if _HP.exists() else {}
AWARDS = ("Best Overall", "Best Budget", "Money No Object")


def rank(cat):
    """(ranked, overall, budget, premium) from build.py's own ranking (tests swap this out)."""
    import build
    return build.rank_products(cat)


def _cat_name(cat):
    return re.sub(r"^The \d+ Best ", "", cat["title"])


def live_rows(site, cats):
    """One row per award per category, in site order, from today's awards. A pick whose
    holiday-prices.json check is newer than the category's capture takes those numbers."""
    rows = []
    for cat in cats:
        _ranked, overall, budget, premium = rank(cat)
        captured = cat.get("data_captured") or site["updated"]
        for award, p in zip(AWARDS, (overall, budget, premium)):
            if not p:
                continue
            nums, date = p, captured
            hp = HOLIDAY_PRICES.get(p["asin"])
            if hp and hp["checked"] > captured:
                nums, date = hp, hp["checked"]
            rows.append({"slug": cat["slug"], "category": _cat_name(cat), "award": award, "asin": p["asin"],
                         "title": f"{p['brand']} {p['model']}", "rating": nums["rating"],
                         "reviews_count": nums["reviews_count"], "price": nums["price"], "price_date": date})
    return rows


def load_frozen():
    return json.loads(FROZEN.read_text(encoding="utf-8")) if FROZEN.exists() else None


def ensure_frozen(site, cats, today):
    """Write the frozen file once, on the first call on or after FREEZE_DATE. True if written."""
    if today < FREEZE_DATE or FROZEN.exists():
        return False
    FROZEN.write_text(json.dumps(live_rows(site, cats), indent=1) + "\n", encoding="utf-8")
    return True


def with_prices(rows, holiday_prices):
    """Copies of rows with price and price_date from a newer holiday-prices check; nothing else changes."""
    out = []
    for r in rows:
        hp = holiday_prices.get(r["asin"])
        out.append({**r, "price": hp["price"], "price_date": hp["checked"]}
                   if hp and hp["checked"] > r["price_date"] else dict(r))
    return out


def rows_for_page(site, cats):
    frozen = load_frozen()
    return with_prices(frozen, HOLIDAY_PRICES) if frozen is not None else live_rows(site, cats)


def is_public(today):
    return today >= REVEAL_DATE


def frozen_asins():
    out = []
    for r in load_frozen() or []:
        if r["asin"] not in out:
            out.append(r["asin"])
    return out
