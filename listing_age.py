"""Listing age for the review-count score (shared by ThemisReviews and ToolboxTop10; keep both copies identical).

Review counts prove a rating is real; past FULL_CREDIT (200) reviews they add nothing more, so rating and
features decide between well-reviewed products.

A listing that has been on Amazon for 10 years has had 10 years to collect reviews. To keep a newer product
from being buried by review volume alone, the score counts a young listing's reviews at a higher rate:

    effective reviews = reviews * min(2, 24 / age_in_months)    only when the listing is under 24 months old
                                                                  and has at least 30 reviews

Older listings are never penalized (multiplier 1), the boost is capped at 2x, ages under 6 months count as
6 months, and listings with fewer than 30 reviews get no boost, so a handful of early reviews can't jump a
product to the top.

Listing date: Amazon's "Date First Available" when a capture has seen it (data/listing-dates.json). Most
listings don't show it, so otherwise the date is estimated from the ASIN: Amazon hands out ASINs in a
roughly increasing order, so characters 3-6 read as a base-36 number line up with listing date. Known
dates calibrate that line (running median of 9, forced to only go forward in time) and other ASINs are
placed on it by interpolation.
"""
import bisect
import datetime
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATES_FILE = HERE / "data" / "listing-dates.json"

REF_MONTHS = 24      # listings younger than this get a boost
MIN_MONTHS = 6       # floor on age, so a brand-new listing isn't boosted without limit
MAX_BOOST = 2.0      # most a review count can be multiplied by
MIN_REVIEWS = 30     # below this, no boost
FULL_CREDIT = 200    # review count (after the age boost) that earns the full review score on every page;
                     # past this, rating and features decide. A page's own reviews_ceiling only applies if lower.

ASIN_RE = re.compile(r"^B0[0-9A-Z]{8}$")
_DATE_FORMATS = ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d")
_cache = None


def parse_date(raw):
    s = (raw or "").replace("‎", "").replace("‏", "").strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def harvest(paths):
    """{asin: earliest date} from capture JSON files. Reads both shapes the sites use: dicts keyed by ASIN,
    and dicts that carry an "asin" field; the date is a "first_available" field or a "Date First Available"
    specs row."""
    found = {}

    def walk(o, asin=None):
        if isinstance(o, dict):
            if isinstance(o.get("asin"), str):
                asin = o["asin"]
            for k, v in o.items():
                if k in ("first_available", "Date First Available") and isinstance(v, str) and asin:
                    d = parse_date(v)
                    if d and (asin not in found or d < found[asin]):
                        found[asin] = d
                else:
                    walk(v, k if ASIN_RE.match(k) else asin)
        elif isinstance(o, list):
            for x in o:
                walk(x, asin)

    for p in paths:
        try:
            walk(json.loads(Path(p).read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return found


def update_dates(paths):
    """Merge newly seen listing dates from capture files into data/listing-dates.json (earliest date wins;
    nothing is ever removed). Returns how many ASINs were added or moved earlier."""
    global _cache
    known = load_dates()
    changed = 0
    for asin, d in harvest(paths).items():
        if asin not in known or d.isoformat() < known[asin]:
            known[asin] = d.isoformat()
            changed += 1
    if changed:
        DATES_FILE.write_text(json.dumps(dict(sorted(known.items())), indent=1) + "\n", encoding="utf-8")
        _cache = None
    return changed


def load_dates():
    if DATES_FILE.exists():
        return json.loads(DATES_FILE.read_text(encoding="utf-8"))
    return {}


def _asin_value(asin):
    n = 0
    for ch in asin[2:6]:
        n = n * 36 + int(ch, 36)
    return n


def _model():
    global _cache
    if _cache is None:
        known = load_dates()
        cal = sorted((_asin_value(a), datetime.date.fromisoformat(d).toordinal())
                     for a, d in known.items() if ASIN_RE.match(a))
        xs = [c[0] for c in cal]
        ys = [c[1] for c in cal]
        sm = [sorted(ys[max(0, i - 4):i + 5])[len(ys[max(0, i - 4):i + 5]) // 2] for i in range(len(ys))]
        for i in range(1, len(sm)):
            sm[i] = max(sm[i], sm[i - 1])
        _cache = (known, xs, sm)
    return _cache


def listed(asin, first_available=None):
    """(date, "listed" | "estimated") or (None, "none")."""
    d = parse_date(first_available) if first_available else None
    if d:
        return d, "listed"
    known, xs, sm = _model()
    if asin in known:
        return datetime.date.fromisoformat(known[asin]), "listed"
    if not ASIN_RE.match(asin or "") or len(xs) < 2:
        return None, "none"
    v = _asin_value(asin)
    i = bisect.bisect_left(xs, v)
    if i <= 0:
        o = sm[0]
    elif i >= len(xs):
        o = sm[-1]
    else:
        x0, x1, y0, y1 = xs[i - 1], xs[i], sm[i - 1], sm[i]
        o = y0 + (y1 - y0) * ((v - x0) / (x1 - x0) if x1 != x0 else 0)
    return datetime.date.fromordinal(int(o)), "estimated"


def review_multiplier(p, as_of):
    """(multiplier, listed date or None, how the date was found) for a product dict with asin and
    reviews_count. as_of is the date the page's numbers were captured."""
    d, how = listed(p.get("asin", ""), p.get("first_available"))
    if not d or p.get("reviews_count", 0) < MIN_REVIEWS:
        return 1.0, d, how
    months = max(MIN_MONTHS, (as_of - d).days / 30.44)
    return min(max(1.0, REF_MONTHS / months), MAX_BOOST), d, how


def review_ceiling(cat, default):
    """Review count that earns full review credit on this page: the page's reviews_ceiling, at most FULL_CREDIT."""
    return min(cat.get("reviews_ceiling", default), FULL_CREDIT)


def review_subscore(p, cat, default_ceiling):
    """0-1 review score: log scale up to review_ceiling, using the age-boosted count. Also records
    review_weight / listed / listed_how on p for the page data."""
    import math
    mult, listed, how = review_multiplier(p, as_of_date(cat))
    p["review_weight"] = round(mult, 2)
    if listed:
        p["listed"], p["listed_how"] = listed.isoformat(), how
    return min(1.0, math.log10(p["reviews_count"] * mult + 1) / math.log10(review_ceiling(cat, default_ceiling))), mult


def as_of_date(cat):
    try:
        return datetime.date.fromisoformat(str(cat.get("data_captured", ""))[:10])
    except ValueError:
        return datetime.date.today()
