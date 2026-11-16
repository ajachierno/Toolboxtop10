"""Plain-assert tests for the daily API price pass. Run: python tests/test_api_prices.py"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import api_prices  # noqa: E402

TODAY = "2026-11-20"


def setup(tmp):
    """A copy of cordless-drills.json in a temp data dir; returns (path, original dict)."""
    d = Path(tmp)
    shutil.copy(ROOT / "data" / "cordless-drills.json", d / "cordless-drills.json")
    api_prices.DATA = d
    return d / "cordless-drills.json", json.loads((d / "cordless-drills.json").read_text(encoding="utf-8"))


def rec(p, price, buybox=True, notfound=False, title=None):
    return {"title": title if title is not None else p["name"], "price": f"${price:,.2f}", "buybox": buybox,
            "notfound": notfound, "avail": "In Stock"}


def test_price_only_small_moves():
    with tempfile.TemporaryDirectory() as tmp:
        path, before = setup(tmp)
        recs = {p["asin"]: rec(p, round(p["price"] * 1.02, 2)) for p in before["products"] + before.get("avoid", [])}
        out = api_prices.apply_prices("cordless-drills", recs, TODAY)
        after = json.loads(path.read_text(encoding="utf-8"))
        assert out["priced"] == len(recs) and out["flags"] == []
        for b, a in zip(before["products"], after["products"]):
            assert a["price"] == round(b["price"] * 1.02, 2)
            assert (a["rating"], a["reviews_count"]) == (b["rating"], b["reviews_count"])
        assert after["data_captured"] == before["data_captured"]
        assert after.get("audited") == before.get("audited")
        assert "prices_checked" not in after, "freshness is per listing, never page-wide"
        assert all(a["price_checked"] == TODAY for a in after["products"] + after.get("avoid", []))
        assert after["changelog"] == before["changelog"], "no note for moves under 8%"


def test_big_move_adds_note():
    with tempfile.TemporaryDirectory() as tmp:
        path, before = setup(tmp)
        p0 = before["products"][0]
        recs = {p0["asin"]: rec(p0, round(p0["price"] * 0.8, 2))}
        api_prices.apply_prices("cordless-drills", recs, TODAY)
        after = json.loads(path.read_text(encoding="utf-8"))
        top = after["changelog"][0]
        assert top["date"] == TODAY and top["note"].startswith("Prices re-checked on 1 of ")
        assert "dropped" in top["note"] and "ratings" not in top["note"]


def test_flags_leave_listing_alone():
    with tempfile.TemporaryDirectory() as tmp:
        path, before = setup(tmp)
        ps = before["products"]
        recs = {ps[0]["asin"]: rec(ps[0], 1.0, buybox=False),
                ps[1]["asin"]: rec(ps[1], 1.0, notfound=True),
                ps[2]["asin"]: rec(ps[2], 1.0, title="Completely unrelated garden hose reel 100 ft"),
                ps[3]["asin"]: {**rec(ps[3], 1.0), "price": None}}
        out = api_prices.apply_prices("cordless-drills", recs, TODAY)
        after = json.loads(path.read_text(encoding="utf-8"))
        assert [a["price"] for a in after["products"][:4]] == [p["price"] for p in ps[:4]]
        assert len(out["flags"]) == len(before["products"]) + len(before.get("avoid", []))  # unlisted ones are "not returned"
        assert out["priced"] == 0
        assert not any("price_checked" in a for a in after["products"] + after.get("avoid", [])),             "a flagged listing keeps its old price and its old date"
        assert after["changelog"] == before["changelog"]


def test_price_date_and_overlays():
    import build
    site = {"updated": "2026-11-01"}
    fresh, stale = {"asin": "A", "price": 50, "price_checked": "2026-11-15"}, {"asin": "B", "price": 9}
    cat = {"data_captured": "2026-11-10", "products": [fresh, stale]}
    assert build.price_date(cat, site, fresh) == "2026-11-15"
    assert build.price_date(cat, site, stale) == "2026-11-10"
    assert build.price_date(cat, site) == "2026-11-10", "page date is the OLDEST listing check"
    assert build.price_date({**cat, "products": [fresh]}, site) == "2026-11-15"
    assert build.price_date({"data_captured": "2026-11-16", "products": [fresh]}, site, fresh) == "2026-11-16"
    real = build.HOLIDAY_PRICES
    build.HOLIDAY_PRICES = {"A": {"checked": "2026-11-12", "price": 1, "rating": 1, "reviews_count": 1},
                            "B": {"checked": "2026-11-12", "price": 2, "rating": 1, "reviews_count": 1}}
    try:
        p, d = build.holiday_price(fresh, cat, site)
        assert (p["price"], d) == (50, "2026-11-15"), "an older holiday check must not beat the API price"
        p, d = build.holiday_price(stale, cat, site)
        assert (p["price"], d) == (2, "2026-11-12"), "a stale listing still takes the newer holiday check"
    finally:
        build.HOLIDAY_PRICES = real


def test_history_logs_each_listing_under_its_own_date():
    import build
    with tempfile.TemporaryDirectory() as tmp:
        real_data, real_load = build.DATA, build.load
        cat = {"slug": "x", "data_captured": "2026-11-10",
               "products": [{"asin": "A", "price": 50.0, "price_checked": "2026-11-15"}, {"asin": "B", "price": 9.0}]}
        build.DATA = Path(tmp)
        build.load = lambda name: cat
        try:
            build.record_prices({"updated": "2026-11-01", "categories": [{"slug": "x"}]})
            hist = json.loads((Path(tmp) / "price-history.json").read_text(encoding="utf-8"))
        finally:
            build.DATA, build.load = real_data, real_load
        assert hist == {"A": [["2026-11-15", 50.0]], "B": [["2026-11-10", 9.0]]}, hist


def test_older_scrape_does_not_overwrite_newer_api_price():
    import apply_scrape
    with tempfile.TemporaryDirectory() as tmp:
        path, before = setup(tmp)
        apply_scrape.DATA = api_prices.DATA
        p0 = before["products"][0]
        api_prices.apply_prices("cordless-drills", {p0["asin"]: rec(p0, 77.77)}, "2026-11-15")
        scrape = {p0["asin"]: {"price": "$99.99", "rating": "4.1 out of 5 stars", "reviews": "(1,234)", "buybox": True}}
        apply_scrape.apply("cordless-drills", scrape, "2026-11-14", False)
        a0 = json.loads(path.read_text(encoding="utf-8"))["products"][0]
        assert a0["price"] == 77.77, "the 11-14 scrape is older than the 11-15 API price"
        assert (a0["rating"], a0["reviews_count"]) == (4.1, 1234), "ratings still come from the scrape"
        apply_scrape.apply("cordless-drills", scrape, "2026-11-16", False)
        a0 = json.loads(path.read_text(encoding="utf-8"))["products"][0]
        assert a0["price"] == 99.99, "a newer scrape wins"


def test_price_parsing():
    assert api_prices._price("$1,299.99") == 1299.99
    assert api_prices._price("$12.99 with 5 percent savings") == 12.99
    assert api_prices._price("From $5.00") is None, "a variation minimum is not this listing's price"
    assert api_prices._price(None) is None


def test_best_of_uses_price_date():
    import best_of
    real_rank, real_hp = best_of.rank, best_of.HOLIDAY_PRICES
    p = {"asin": "A", "brand": "B", "model": "M", "price": 10, "rating": 4.5, "reviews_count": 9,
         "price_checked": "2026-11-15"}
    best_of.rank = lambda cat: ([p], p, None, None)
    best_of.HOLIDAY_PRICES = {}
    try:
        r = best_of.live_rows({"updated": "2026-11-01"}, [{"slug": "s", "title": "The 10 Best S",
                                                           "data_captured": "2026-11-10",
                                                           "products": [p]}])[0]
        assert r["price_date"] == "2026-11-15"
    finally:
        best_of.rank, best_of.HOLIDAY_PRICES = real_rank, real_hp


def test_holiday_api_keeps_newest_ratings():
    import holiday_picks
    with tempfile.TemporaryDirectory() as tmp:
        holiday_picks.OUT = Path(tmp) / "holiday-prices.json"
        holiday_picks.OUT.write_text(json.dumps({
            "A": {"price": 5, "rating": 4.4, "reviews_count": 77, "checked": "2026-11-01"},
            "C": {"price": 5, "rating": 4.9, "reviews_count": 500, "checked": "2026-11-12"}}), encoding="utf-8")
        holiday_picks.award_asins = lambda: ["A", "B", "C"]
        # category files: A re-scraped 11-10 (newer than its holiday entry), C scraped 11-05 (older)
        holiday_picks._last_ratings = lambda: {"A": (4.6, 90, "2026-11-10"), "C": (4.7, 450, "2026-11-05")}
        fake = type("F", (), {})()
        fake.get_items = lambda asins: ({"A": {}, "B": {}, "C": {}}, [])
        fake.record = lambda a, it: {"price": "$9.50", "buybox": True, "notfound": False} if a != "B" else             {"price": None, "buybox": False, "notfound": True}
        holiday_picks.creators_api = fake
        holiday_picks.TODAY = TODAY
        holiday_picks.api()
        got = json.loads(holiday_picks.OUT.read_text(encoding="utf-8"))
        assert got["A"] == {"price": 9.5, "rating": 4.6, "reviews_count": 90, "checked": TODAY}
        assert got["C"] == {"price": 9.5, "rating": 4.9, "reviews_count": 500, "checked": TODAY}
        assert "B" not in got


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ok ({len(tests)} tests)")
