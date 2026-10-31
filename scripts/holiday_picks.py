"""Picks-only price pass for the holiday deal pages (toolboxtop10-holiday-pages skill).

A holiday page shows every category's Best Overall and Best Budget. Re-reading all 1,800
listings each day isn't practical, so this re-reads just those award listings:

  python scripts/holiday_picks.py asins    # list the award ASINs the holiday pages show
  python scripts/holiday_picks.py scrape   # re-read them into scrape-results/<today>.json
                                           # (visible Chrome window; re-run until nothing is left)
  python scripts/holiday_picks.py apply    # write data/holiday-prices.json from today's capture

build.py overlays data/holiday-prices.json on the holiday pages only, each pick with its own
"regular price on <date>". Category pages keep their own numbers and capture date until their
next refresh. Entries that didn't capture keep their previous values and date.
"""
import asyncio
import datetime
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TODAY = datetime.date.today().isoformat()
CAPTURE = ROOT / "scrape-results" / f"{TODAY}.json"
OUT = ROOT / "data" / "holiday-prices.json"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import build  # noqa: E402  same ranking and badge logic the holiday pages use


def award_asins():
    site = build.load("site.json")
    out = []
    for c in site["categories"]:
        cat = build.load(f"{c['slug']}.json")
        _ranked, overall, budget, _premium = build.rank_products(cat)
        for p in (overall, budget):
            if p and p["asin"] not in out:
                out.append(p["asin"])
    return out


def scrape():
    import scrape_amazon  # noqa: E402  the site's Amazon reader (Playwright, visible Chrome)
    asins = award_asins()
    scrape_amazon.targets = lambda _slugs: asins  # same capture file and format as the price pass
    print(f"Re-reading {len(asins)} award listings into {CAPTURE.name} (at most {scrape_amazon.PER_RUN} per run)")
    asyncio.run(scrape_amazon.main(set()))


def apply():
    if not CAPTURE.exists():
        sys.exit("No capture for today. Run: python scripts/holiday_picks.py scrape")
    cap = json.loads(CAPTURE.read_text(encoding="utf-8"))
    prices = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    ok, failed = 0, []
    for asin in award_asins():
        r = cap.get(asin) or {}
        try:
            price = float(str(r.get("price")).replace("$", "").replace(",", "")) if r.get("price") else None
            rating = float(str(r.get("rating")).split()[0]) if r.get("rating") else None
            reviews = int(str(r.get("reviews")).replace(",", "").strip("() ").split()[0]) if r.get("reviews") else None
        except ValueError:
            price = rating = reviews = None
        if r.get("error") or not r.get("buybox") or None in (price, rating, reviews):
            failed.append(asin)
            continue
        prices[asin] = {"price": price, "rating": rating, "reviews_count": reviews, "checked": TODAY}
        ok += 1
    OUT.write_text(json.dumps(prices, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"holiday-prices: {ok} updated today, {len(failed)} not captured: {' '.join(failed)}")


if __name__ == "__main__":
    {"asins": lambda: print(len(award_asins()), *award_asins()), "scrape": scrape, "apply": apply}[sys.argv[1]]()
