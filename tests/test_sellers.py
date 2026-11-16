"""Plain-assert tests for buy-box seller tracking. Run: python tests/test_sellers.py"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import sellers  # noqa: E402
import creators_api  # noqa: E402


def item(seller, condition="New"):
    return {"asin": "A", "itemInfo": {"title": {"displayValue": "DEWALT drill"}},
            "offersV2": {"listings": [
                {"isBuyBoxWinner": True, "merchantInfo": {"name": seller, "id": "X"},
                 "condition": {"value": condition}, "price": {"money": {"amount": 99.0}}},
                {"isBuyBoxWinner": False, "merchantInfo": {"name": "Other"}, "condition": {"value": "New"}}]}}


def test_record_reads_buy_box_seller():
    r = creators_api.record("A", item("Amazon.com"))
    assert (r["seller"], r["condition"]) == ("Amazon.com", "New")
    r = creators_api.record("A", item("Amazon Resale", "Used"))
    assert (r["seller"], r["condition"]) == ("Amazon Resale", "Used")
    assert creators_api.record("A", None)["seller"] is None


def test_trusted():
    assert sellers.trusted("Amazon.com", "New", "DEWALT")
    assert sellers.trusted("DEWALT Official Store", "New", "DEWALT"), "the brand's own store"
    assert sellers.trusted("Black & Decker Store", "New", "BLACK+DECKER"), "brand matched on its letters"
    assert not sellers.trusted("Amazon Resale", "Used", "DEWALT")
    assert not sellers.trusted("Amazon.com", "Used", "DEWALT"), "used stock is never the pick we reviewed"
    assert not sellers.trusted("ToolsDirect LLC", "New", "DEWALT")
    assert not sellers.trusted(None, None, "DEWALT")


def test_flip_fires_once_after_two_checks():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sellers.json"
        days = [("2026-11-12", "Amazon.com"), ("2026-11-13", "Amazon.com"), ("2026-11-14", "ToolsDirect LLC")]
        for d, s in days:
            hist = sellers.update(path, {"A": (s, "New")}, d)
            assert sellers.flipped(hist, "A", "DEWALT") is None, "one check of a new seller is not a flip yet"
        hist = sellers.update(path, {"A": ("ToolsDirect LLC", "New")}, "2026-11-15")
        assert sellers.flipped(hist, "A", "DEWALT") == ("Amazon.com", "ToolsDirect LLC")
        hist = sellers.update(path, {"A": ("ToolsDirect LLC", "New")}, "2026-11-16")
        assert sellers.flipped(hist, "A", "DEWALT") is None, "reported once, not every day after"


def test_bouncing_buy_box_and_unreturned_listings():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sellers.json"
        for d, s in (("2026-11-12", "Amazon.com"), ("2026-11-13", "ToolsDirect LLC"), ("2026-11-14", "Amazon.com"),
                     ("2026-11-15", "ToolsDirect LLC")):
            hist = sellers.update(path, {"A": (s, "New"), "B": (None, None)}, d)
        assert sellers.flipped(hist, "A", "DEWALT") is None, "bouncing every other day never flags"
        assert "B" not in hist, "a listing the API didn't return records nothing"
        assert sellers.flipped({}, "A", "DEWALT") is None


def test_used_stock_takes_the_buy_box():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sellers.json"
        for d, s, c in (("2026-11-13", "Amazon.com", "New"), ("2026-11-14", "Amazon Resale", "Used"),
                        ("2026-11-15", "Amazon Resale", "Used")):
            hist = sellers.update(path, {"A": (s, c)}, d)
        assert sellers.flipped(hist, "A", "DEWALT") == ("Amazon.com", "Amazon Resale (Used)")


def test_price_pass_seller_flags():
    import api_prices
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sellers.json"
        pages = {"drills": {"products": [{"asin": "A", "brand": "DEWALT", "model": "DCD771C2"}],
                            "avoid": [{"asin": "C", "brand": "X", "model": "Y"}]}}
        out = []
        for d, s in (("2026-11-13", "Amazon.com"), ("2026-11-14", "ToolsDirect LLC"), ("2026-11-15", "ToolsDirect LLC")):
            recs = {"A": {"seller": s, "condition": "New"}, "C": {"seller": s, "condition": "New"}}
            out = api_prices.seller_flags(pages, recs, d, path)
        assert out == ["drills A DEWALT DCD771C2: seller changed, Amazon.com -> ToolsDirect LLC on the last 2 checks"], \
            "the avoid pick never flags"


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ok ({len(tests)} tests)")
