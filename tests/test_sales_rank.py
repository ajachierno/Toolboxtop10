"""Plain-assert tests for sales rank history and Amazon list prices. Run: python tests/test_sales_rank.py"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import sales_rank  # noqa: E402
import creators_api  # noqa: E402

ITEM = {
    "asin": "B00ET5VMTU",
    "itemInfo": {"title": {"displayValue": "DEWALT 20V Max XR Drill Driver"}},
    "browseNodeInfo": {
        "browseNodes": [
            {"contextFreeName": "Power Drill Drivers", "displayName": "Drill Drivers", "salesRank": 4},
            {"contextFreeName": "391fa3a0-755b-400e-98cb-8baba1d2b47e_1901", "displayName": "391fa3a0-755b", "salesRank": 1},
            {"contextFreeName": "Power Tools", "displayName": "Power Tools", "salesRank": 40},
            {"contextFreeName": "No Rank Here", "displayName": "No Rank Here"},
        ],
        "websiteSalesRank": {"salesRank": 1672},
    },
    "offersV2": {"listings": [
        {"isBuyBoxWinner": True, "availability": {"message": "In Stock"},
         "price": {"money": {"amount": 99.0, "displayAmount": "$99.00"},
                   "savingBasis": {"money": {"amount": 179.0}, "savingBasisType": "LIST_PRICE",
                                   "savingBasisTypeLabel": "List Price:"},
                   "savings": {"money": {"amount": 80.0}, "percentage": 45}}},
        {"isBuyBoxWinner": False, "price": {"money": {"amount": 77.35}}},
    ]},
}


def test_resources_ask_for_rank():
    assert "browseNodeInfo.browseNodes.salesRank" in creators_api.RESOURCES
    assert "browseNodeInfo.websiteSalesRank" in creators_api.RESOURCES


def test_record_reads_rank_and_list_price():
    r = creators_api.record("B00ET5VMTU", ITEM)
    assert (r["cat_rank"], r["cat_node"], r["site_rank"]) == (4, "Power Drill Drivers", 1672), \
        "best named category rank; hidden id-named nodes don't count"
    assert (r["list_price"], r["price"]) == (179.0, "$99.00")


def test_record_ignores_other_saving_types_and_missing_rank():
    item = json.loads(json.dumps(ITEM))
    item["offersV2"]["listings"][0]["price"]["savingBasis"]["savingBasisType"] = "WAS_PRICE"
    item["browseNodeInfo"] = {}
    r = creators_api.record("B00ET5VMTU", item)
    assert r["list_price"] is None, "only Amazon's own List Price counts"
    assert (r["cat_rank"], r["cat_node"], r["site_rank"]) == (None, None, None)
    gone = creators_api.record("B00ET5VMTU", None)
    assert gone["cat_rank"] is None and gone["list_price"] is None


def test_history_and_slipping():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sales-rank.json"
        days = ["2026-11-1%d" % i for i in range(1, 6)]
        ranks = {"2026-11-11": 150, "2026-11-12": 90, "2026-11-13": 130, "2026-11-14": 210, "2026-11-15": 180}
        for d in days:
            sales_rank.update(path, {"A": (ranks[d], "Drill Drivers", 5000), "B": (None, None, None)}, d)
        sales_rank.update(path, {"A": (181, "Drill Drivers", 5001)}, "2026-11-15")  # same day re-run replaces
        hist = sales_rank.load(path)
        assert [e[0] for e in hist["A"]] == days and hist["A"][-1][1] == 181
        assert "B" not in hist, "no rank, nothing recorded"
        assert sales_rank.slipping(hist, "A") == ["2026-11-15", 181, "Drill Drivers", 5001], "best #90, now #181"
        assert sales_rank.slipping(hist, "B") is None
        hist["A"][-3][1] = 99  # back in the top 100 two checks ago
        assert sales_rank.slipping(hist, "A") is None
        assert sales_rank.slipping({"A": [["2026-11-15", 500, "X", 1]]}, "A") is None, "needs 3 checks"
        steady = {"A": [["2026-11-1%d" % i, 500, "X", 1] for i in range(1, 6)]}
        assert sales_rank.slipping(steady, "A") is None, "behind the line but not falling"


def test_history_keeps_last_30():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sales-rank.json"
        for i in range(35):
            sales_rank.update(path, {"A": (i + 1, "N", None)}, f"2026-{10 + i // 28:02d}-{i % 28 + 1:02d}")
        assert len(sales_rank.load(path)["A"]) == 30


def test_holiday_card_shows_list_price_only_for_its_own_check():
    import build
    site = {"updated": "2026-11-01"}
    p = {"asin": "A", "price": 120.0, "rating": 4.5, "reviews_count": 10}
    cat = {"data_captured": "2026-11-10", "products": [p]}
    real = build.HOLIDAY_PRICES
    try:
        build.HOLIDAY_PRICES = {"A": {"checked": "2026-11-15", "price": 99.0, "rating": 4.5, "reviews_count": 10,
                                      "list_price": 179.0}}
        q, d = build.holiday_price(p, cat, site)
        assert (q["price"], q["list_price"], d) == (99.0, 179.0, "2026-11-15")
        assert build.list_note(q) == " &middot; Amazon list price $179 (45% off)"
        same_day = {**p, "price": 99.0, "price_checked": "2026-11-15"}  # morning API pass, same price
        q, d = build.holiday_price(same_day, {**cat, "products": [same_day]}, site)
        assert q.get("list_price") == 179.0, "same check, same price: the list price applies"
        moved = {**p, "price": 105.0, "price_checked": "2026-11-15"}
        q, d = build.holiday_price(moved, {**cat, "products": [moved]}, site)
        assert q.get("list_price") is None and build.list_note(q) == "", "a different price: no list price claim"
        assert build.list_note({"price": 200.0, "list_price": 179.0}) == "", "no 'off' when the price is above list"
    finally:
        build.HOLIDAY_PRICES = real


def test_holiday_api_saves_list_price():
    import holiday_picks
    with tempfile.TemporaryDirectory() as tmp:
        holiday_picks.OUT = Path(tmp) / "holiday-prices.json"
        holiday_picks.OUT.write_text(json.dumps({"A": {"price": 5, "rating": 4.4, "reviews_count": 77,
                                                       "checked": "2026-11-01", "list_price": 9.0}}), encoding="utf-8")
        holiday_picks.award_asins = lambda: ["A", "B"]
        holiday_picks._last_ratings = lambda: {"A": (4.4, 77, "2026-10-01"), "B": (4.0, 50, "2026-10-01")}
        fake = type("F", (), {})()
        fake.get_items = lambda asins: ({"A": {}, "B": {}}, [])
        fake.record = lambda a, it: {"price": "$99.00", "buybox": True, "notfound": False,
                                     "list_price": 179.0 if a == "B" else None}
        holiday_picks.creators_api = fake
        holiday_picks.TODAY = "2026-11-15"
        holiday_picks.api()
        got = json.loads(holiday_picks.OUT.read_text(encoding="utf-8"))
        assert got["B"]["list_price"] == 179.0
        assert "list_price" not in got["A"], "yesterday's list price doesn't carry over"


def test_price_pass_records_ranks_and_flags_falling_picks():
    import api_prices
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sales-rank.json"
        prods = [{"asin": a, "brand": "DEWALT", "model": m} for a, m in
                 (("A", "DCD771C2"), ("B", "DCD777"), ("D", "DCD791"), ("E", "DCD800"))]
        pages = {"drills": {"products": prods, "avoid": [{"asin": "C", "brand": "X", "model": "Y"}]}}

        def day(d, a_rank):
            recs = {x: {"cat_rank": r, "cat_node": "Drill Drivers", "site_rank": None}
                    for x, r in (("A", a_rank), ("B", 12), ("D", 20), ("E", 30), ("C", 9000))}
            return api_prices.rank_flags(pages, recs, d, path)

        assert day("2026-11-12", 60) == []
        assert day("2026-11-13", 130) == []
        assert day("2026-11-14", 200) == []
        # page median (20 + 30) / 2 = 25, so the line is the top-100 floor; A went 60 -> 250
        assert day("2026-11-15", 250) == ["drills A DEWALT DCD771C2: falling, #250 in Drill Drivers "
                                          "(best #60 in its last 30 checks, page line #100)"],             "the avoid pick never flags"
        assert set(sales_rank.load(path)) == {"A", "B", "C", "D", "E"}


def test_steady_weak_picks_never_flag():
    """Live 2026-11-15: 106 picks on 73 pages sat behind their page line, almost all steady
    (#139 against #100). Only a pick whose rank at least doubled flags."""
    import api_prices
    ranks = {"H1": 258, "H2": 354, "H3": 463, "H4": 150, "H5": 87, "H6": 1, "H7": 106, "H8": 115, "H9": 2,
             "H10": 137, "H11": 1400}
    pages = {"engine-hoists": {"products": [{"asin": a, "brand": "B", "model": a} for a in ranks]}}

    def recs(rk):
        return {a: {"cat_rank": r, "cat_node": "Engine Hoists & Stands", "site_rank": None} for a, r in rk.items()}

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sales-rank.json"
        for d in ("2026-11-12", "2026-11-13", "2026-11-14", "2026-11-15"):
            assert api_prices.rank_flags(pages, recs(ranks), d, path) == [], "steady ranks, however weak"
        worse = {**ranks, "H3": 926, "H8": 230}  # H3 doubled past the line (#450, median #150); H8 doubled but stays inside
        for d in ("2026-11-16", "2026-11-17", "2026-11-18"):
            flags = api_prices.rank_flags(pages, recs(worse), d, path)
    assert [f.split()[1] for f in flags] == ["H3"], flags


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ok ({len(tests)} tests)")
