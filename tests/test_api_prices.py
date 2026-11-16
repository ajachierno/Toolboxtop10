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
        assert after["prices_checked"] == TODAY
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
        assert "prices_checked" not in after, "nothing priced, so no stamp"
        assert after["changelog"] == before["changelog"]


def test_price_date_and_overlays():
    import build
    site = {"updated": "2026-11-01"}
    assert build.price_date({"data_captured": "2026-11-10"}, site) == "2026-11-10"
    assert build.price_date({"data_captured": "2026-11-10", "prices_checked": "2026-11-15"}, site) == "2026-11-15"
    assert build.price_date({"data_captured": "2026-11-16", "prices_checked": "2026-11-15"}, site) == "2026-11-16"
    cat = {"data_captured": "2026-11-10", "prices_checked": "2026-11-15"}
    real = build.HOLIDAY_PRICES
    build.HOLIDAY_PRICES = {"A": {"checked": "2026-11-12", "price": 1, "rating": 1, "reviews_count": 1}}
    try:
        p, d = build.holiday_price({"asin": "A", "price": 50}, cat, site)
        assert (p["price"], d) == (50, "2026-11-15"), "an older holiday check must not beat the API price"
    finally:
        build.HOLIDAY_PRICES = real


def test_best_of_uses_price_date():
    import best_of
    real_rank, real_hp = best_of.rank, best_of.HOLIDAY_PRICES
    p = {"asin": "A", "brand": "B", "model": "M", "price": 10, "rating": 4.5, "reviews_count": 9}
    best_of.rank = lambda cat: ([p], p, None, None)
    best_of.HOLIDAY_PRICES = {}
    try:
        r = best_of.live_rows({"updated": "2026-11-01"}, [{"slug": "s", "title": "The 10 Best S",
                                                           "data_captured": "2026-11-10", "prices_checked": "2026-11-15",
                                                           "products": [p]}])[0]
        assert r["price_date"] == "2026-11-15"
    finally:
        best_of.rank, best_of.HOLIDAY_PRICES = real_rank, real_hp


def test_holiday_api_keeps_ratings():
    import holiday_picks
    with tempfile.TemporaryDirectory() as tmp:
        holiday_picks.OUT = Path(tmp) / "holiday-prices.json"
        holiday_picks.OUT.write_text(json.dumps({"A": {"price": 5, "rating": 4.4, "reviews_count": 77, "checked": "2026-11-01"}}),
                                     encoding="utf-8")
        holiday_picks.award_asins = lambda: ["A", "B"]
        fake = type("F", (), {})()
        fake.get_items = lambda asins: ({"A": {}, "B": {}}, [])
        fake.record = lambda a, it: {"price": "$9.50", "buybox": True, "notfound": False} if a == "A" else \
            {"price": None, "buybox": False, "notfound": True}
        holiday_picks.creators_api = fake
        holiday_picks.TODAY = TODAY
        holiday_picks.api()
        got = json.loads(holiday_picks.OUT.read_text(encoding="utf-8"))
        assert got["A"] == {"price": 9.5, "rating": 4.4, "reviews_count": 77, "checked": TODAY}
        assert "B" not in got


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ok ({len(tests)} tests)")
