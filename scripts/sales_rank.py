"""Daily Amazon sales rank history, from the Creators API (written by the daily price pass).

data/sales-rank.json holds {asin: [[date, category_rank, category_name, site_rank], ...]}, the
last KEEP checks per listing. category_rank is the listing's best rank in a named Amazon
category (Amazon also lists hidden id-named nodes; those don't count).

A pick is FALLING when, on each of its last RUNS checks, it ranked outside the top LIMIT in its
best category AND worse than FACTOR x the median rank of its page's picks (page_line), and its
latest rank is at least DROP x its best rank in the kept history. Steady picks never flag, however
weak: on 2026-11-15, 106 picks on 73 pages sat behind their page line, almost all steady. That only flags the page for a full audit, where the best-seller search decides
whether it goes; a rank never removes a pick by itself.
"""
import json
import re
from pathlib import Path

LIMIT, FACTOR, DROP, RUNS, KEEP = 100, 3, 2, 3, 30
_HIDDEN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-")


def best_rank(item):
    """(category_rank, category_name, site_rank) for one API item; None where Amazon gave none."""
    bni = (item or {}).get("browseNodeInfo") or {}
    named = []
    for n in bni.get("browseNodes") or []:
        name = n.get("contextFreeName") or n.get("displayName") or ""
        if isinstance(n.get("salesRank"), int) and name and not _HIDDEN.match(name):
            named.append((n["salesRank"], name))
    rank, name = min(named) if named else (None, None)
    site = (bni.get("websiteSalesRank") or {}).get("salesRank")
    return rank, name, site if isinstance(site, int) else None


def load(path):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def update(path, ranks, today):
    """Record today's {asin: (category_rank, category_name, site_rank)}; listings with no
    category rank are skipped. A second run on the same day replaces that day's entry."""
    path = Path(path)
    hist = load(path)
    for asin, (rank, name, site) in ranks.items():
        if rank is None:
            continue
        rows = [r for r in hist.get(asin, []) if r[0] != today] + [[today, rank, name, site]]
        hist[asin] = sorted(rows)[-KEEP:]
    lines = [f"  {json.dumps(a)}: {json.dumps(v, ensure_ascii=False)}" for a, v in sorted(hist.items())]
    path.write_text("{\n" + ",\n".join(lines) + "\n}\n", encoding="utf-8")
    return hist


def page_line(ranks):
    """The rank a pick must fall behind to count as slipping on its page: outside the top LIMIT
    AND worse than FACTOR x the median of the page's picks. Niche pages sit in broad Amazon
    categories (engine hoists rank in the hundreds among stands and parts), so the top 100 alone
    would flag most of them; the median keeps the test relative to the page's own peers."""
    ranks = sorted(r for r in ranks if isinstance(r, int))
    if not ranks:
        return LIMIT
    mid = len(ranks) // 2
    median = ranks[mid] if len(ranks) % 2 else (ranks[mid - 1] + ranks[mid]) / 2
    return max(LIMIT, FACTOR * median)


def slipping(hist, asin, line=LIMIT):
    """The latest entry when the pick is FALLING: its last RUNS checks were all worse than `line`
    and its latest rank is at least DROP x its best rank in the kept history. A pick that has
    always ranked where it ranks now is steady, not falling, however weak; the audit rotation
    handles those. Else None."""
    rows = hist.get(asin) or []
    last = rows[-RUNS:]
    if len(last) == RUNS and all(r[1] > line for r in last) and rows[-1][1] >= DROP * min(r[1] for r in rows):
        return rows[-1]
    return None


def best(hist, asin):
    """The listing's best (lowest) rank in the kept history, or None."""
    return min((r[1] for r in hist.get(asin) or []), default=None)
