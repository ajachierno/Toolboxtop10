"""Plain-assert tests for best_of.py (no pytest here). Run: python tests/test_best_of.py"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import best_of  # noqa: E402

SITE = {"updated": "2026-11-01", "categories": [{"slug": "drills"}, {"slug": "saws"}]}


def prod(asin, price=50.0, brand="B", model="M"):
    return {"asin": asin, "brand": brand, "model": model, "price": price, "rating": 4.5, "reviews_count": 100}


def cats(budget=True, premium=True):
    d = {"slug": "drills", "title": "The 10 Best Cordless Drills", "data_captured": "2026-11-10",
         "products": [prod("A1", 100), prod("A2", 40)] + ([prod("A3", 300)] if premium else [])}
    s = {"slug": "saws", "title": "The 10 Best Saws", "data_captured": "2026-11-12", "products": [prod("S1", 80)]}
    picks = {"drills": ("A1", "A2" if budget else None, "A3" if premium else None), "saws": ("S1", None, None)}
    return [d, s], picks


def with_fake_ranking(picks):
    def fake(cat):
        by = {p["asin"]: p for p in cat["products"]}
        o, b, m = picks[cat["slug"]]
        return cat["products"], by[o], by.get(b), by.get(m)
    return fake


def setup(tmp, budget=True, premium=True):
    best_of.FROZEN = Path(tmp) / "best-of-2026.json"
    cs, picks = cats(budget, premium)
    best_of.rank = with_fake_ranking(picks)
    best_of.HOLIDAY_PRICES = {}
    return cs


def test_with_prices_newer_only():
    row = {"asin": "A1", "price": 99, "price_date": "2026-12-31", "rating": 4.5, "reviews_count": 100}
    newer = {"A1": {"price": 89, "checked": "2027-01-03", "rating": 1.0, "reviews_count": 1}}
    out = best_of.with_prices([row], newer)[0]
    assert (out["price"], out["price_date"], out["rating"], out["reviews_count"]) == (89, "2027-01-03", 4.5, 100)
    assert row["price"] == 99, "input row must not be mutated"
    older = {"A1": {"price": 89, "checked": "2026-12-20", "rating": 4.0, "reviews_count": 5}}
    assert best_of.with_prices([row], older)[0] == row
    assert best_of.with_prices([row], {})[0] == row


def test_ensure_frozen_once():
    with tempfile.TemporaryDirectory() as tmp:
        cs = setup(tmp)
        assert best_of.ensure_frozen(SITE, cs, "2026-12-30") is False
        assert not best_of.FROZEN.exists()
        assert best_of.ensure_frozen(SITE, cs, "2026-12-31") is True
        before = best_of.FROZEN.read_bytes()
        cs[0]["products"][0]["price"] = 1.0
        assert best_of.ensure_frozen(SITE, cs, "2027-01-02") is False
        assert best_of.FROZEN.read_bytes() == before


def test_live_rows_order_and_fields():
    with tempfile.TemporaryDirectory() as tmp:
        rows = best_of.live_rows(SITE, setup(tmp))
        assert [(r["slug"], r["award"]) for r in rows] == [
            ("drills", "Best Overall"), ("drills", "Best Budget"), ("drills", "Money No Object"),
            ("saws", "Best Overall")]
        r = rows[0]
        assert r == {"slug": "drills", "category": "Cordless Drills", "award": "Best Overall", "asin": "A1",
                     "title": "B M", "rating": 4.5, "reviews_count": 100, "price": 100,
                     "price_date": "2026-11-10"}


def test_live_rows_skips_missing_awards():
    with tempfile.TemporaryDirectory() as tmp:
        rows = best_of.live_rows(SITE, setup(tmp, budget=False, premium=False))
        assert [r["award"] for r in rows if r["slug"] == "drills"] == ["Best Overall"]


def test_live_rows_uses_newer_holiday_price():
    with tempfile.TemporaryDirectory() as tmp:
        cs = setup(tmp)
        best_of.HOLIDAY_PRICES = {"A1": {"price": 95, "checked": "2026-11-15", "rating": 4.6, "reviews_count": 120}}
        r = best_of.live_rows(SITE, cs)[0]
        assert (r["price"], r["price_date"], r["rating"], r["reviews_count"]) == (95, "2026-11-15", 4.6, 120)


def test_rows_for_page_frozen_vs_live():
    with tempfile.TemporaryDirectory() as tmp:
        cs = setup(tmp)
        assert best_of.rows_for_page(SITE, cs)[0]["price"] == 100
        best_of.ensure_frozen(SITE, cs, "2026-12-31")
        cs[0]["products"][0]["price"] = 1.0   # a later refresh must not reach the frozen page
        best_of.HOLIDAY_PRICES = {"A1": {"price": 77, "checked": "2027-02-01", "rating": 1, "reviews_count": 1}}
        r = best_of.rows_for_page(SITE, cs)[0]
        assert (r["price"], r["price_date"], r["rating"]) == (77, "2027-02-01", 4.5)


def test_frozen_asins_dedup():
    with tempfile.TemporaryDirectory() as tmp:
        best_of.FROZEN = Path(tmp) / "best-of-2026.json"
        assert best_of.frozen_asins() == []
        best_of.FROZEN.write_text(json.dumps({"frozen_on": "2026-12-31", "rows": [{"asin": "X"}, {"asin": "Y"}, {"asin": "X"}]}), encoding="utf-8")
        assert best_of.frozen_asins() == ["X", "Y"]


def test_is_public():
    assert best_of.is_public("2026-12-31") is False
    assert best_of.is_public("2027-01-01") is True


def test_render_header_and_noindex():
    import build
    site = build.load("site.json")
    rows = [{"slug": site["categories"][0]["slug"], "category": "Real Cat", "award": "Best Overall", "asin": "A1",
             "title": "B M", "rating": 4.5, "reviews_count": 1234, "price": 99.5, "price_date": "2026-11-15"},
            {"slug": "gone-category", "category": "Gone Cat", "award": "Best Budget", "asin": "A2",
             "title": "C D", "rating": 4.1, "reviews_count": 50, "price": 20, "price_date": "2026-11-14"}]
    real_rows, real_out, real_freeze = best_of.rows_for_page, build.OUT, best_of.ensure_frozen
    best_of.rows_for_page = lambda site, cats: rows
    try:
        with tempfile.TemporaryDirectory() as tmp:
            build.OUT = Path(tmp)
            best_of.FROZEN = Path(tmp) / "never-written.json"
            best_of.ensure_frozen = lambda *a: False
            assert build.build_best_of(site, [], "2026-11-20") is None
            html = (Path(tmp) / "best-of-2026.html").read_text(encoding="utf-8")
            assert "<th>Current price</th>" in html and "as of Nov 15" in html
            assert "noindex" in html
            assert 'href="gone-category.html"' not in html and "Gone Cat" in html
            assert f'href="{rows[0]["slug"]}.html"' in html and "1,234" in html
            out = build.build_best_of(site, [], "2027-01-01")
            assert out == ("best-of-2026", "2026-11-15")
            assert "noindex" not in (Path(tmp) / "best-of-2026.html").read_text(encoding="utf-8")
    finally:
        best_of.rows_for_page, build.OUT, best_of.ensure_frozen = real_rows, real_out, real_freeze


def test_award_asins_includes_frozen():
    sys.path.insert(0, str(ROOT / "scripts"))
    import holiday_picks
    real = best_of.FROZEN
    with tempfile.TemporaryDirectory() as tmp:
        best_of.FROZEN = Path(tmp) / "best-of-2026.json"
        try:
            live = holiday_picks.award_asins()
            best_of.FROZEN.write_text(json.dumps({"frozen_on": "2026-12-31", "rows": [{"asin": "ZZFROZEN01"}, {"asin": live[0]}]}), encoding="utf-8")
            got = holiday_picks.award_asins()
            assert got.count("ZZFROZEN01") == 1 and got.count(live[0]) == 1
            assert len(got) == len(live) + 1
        finally:
            best_of.FROZEN = real


def test_build_never_freezes():
    import build
    site = build.load("site.json")
    real_rows, real_out, real_frozen = best_of.rows_for_page, build.OUT, best_of.FROZEN
    best_of.rows_for_page = lambda *a: []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            build.OUT = Path(tmp)
            best_of.FROZEN = Path(tmp) / "best-of-2026.json"
            build.build_best_of(site, [], "2026-12-31")
            assert not best_of.FROZEN.exists(), "only `python best_of.py freeze` may write the file"
    finally:
        best_of.rows_for_page, build.OUT, best_of.FROZEN = real_rows, real_out, real_frozen


def test_frozen_on_recorded_and_shown():
    import build
    with tempfile.TemporaryDirectory() as tmp:
        cs = setup(tmp)
        assert best_of.frozen_on() is None
        best_of.ensure_frozen(SITE, cs, "2027-01-03")
        assert best_of.frozen_on() == "2027-01-03"
        assert best_of.load_frozen()[0]["asin"] == "A1"
        site = build.load("site.json")
        real_out = build.OUT
        try:
            build.OUT = Path(tmp)
            build.build_best_of(site, cs, "2027-01-03")
            assert "locked on January 3, 2027" in (Path(tmp) / "best-of-2026.html").read_text(encoding="utf-8")
        finally:
            build.OUT = real_out


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ok ({len(tests)} tests)")
