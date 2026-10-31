"""Price tracker pages, built from data/price-history.json.

Every build logs each tracked listing's Amazon price under its page's capture date, so
the history grows on its own. This module turns that log into:

  docs/price-tracker.html          the hub: biggest 30-day drops and rises, listings at
                                   their lowest price in our checks, a per-category table
  docs/price-report-YYYY-MM.html   one report per month with enough data (the current
                                   month reads "so far")
  docs/price-history.csv / .json   the raw data, free to reuse with a link back

Pure Python, no dependencies. build.py calls build() and hands in the site's own page()
renderer and helpers, so both sites share this file unchanged.
"""
import csv
import datetime
import io
import json
import statistics

WINDOW_DAYS = 30        # the "recent" window on the hub page
MIN_MOVE_PCT = 3.0      # a move smaller than this is noise (Amazon pennies)
MIN_MOVE_USD = 2.0
MAX_STALE_DAYS = 10     # a listing's latest check must be this fresh to count as "now"
TOP_N = 12
LOW_N = 20

# Appended to each site's stylesheet. Colors validated with the dataviz palette checker
# against both sites' dark card surfaces (OKLCH L inside the dark band, >= 3:1 contrast,
# normal-vision dE 24). Polarity is never color-alone: every change also carries its sign.
CSS = r"""
.pt-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:16px 0 6px}
.pt-stats div{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:14px 16px}
.pt-stats b{display:block;font-size:1.6rem;line-height:1.1}
.pt-stats span{font-size:.8rem;color:var(--muted)}
.pt-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(480px,100%),1fr));gap:18px}
.pt-grid .tablewrap{margin-top:0}
.pt table{min-width:0;font-size:.88rem}
.pt td.n,.pt th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.pt .sub{color:var(--muted);font-size:.78rem;white-space:normal}
.pt td.name{white-space:normal;min-width:180px}
.pt-change{display:inline-flex;align-items:center;gap:8px;white-space:nowrap;flex-wrap:wrap;max-width:150px}
.pt-bar{display:inline-block;height:8px;border-radius:4px;min-width:2px}
.pt-down{color:#31a56a}.pt-down .pt-bar{background:#31a56a}
.pt-up{color:#d96c3a}.pt-up .pt-bar{background:#d96c3a}
.pt-flat{color:var(--muted)}
.pt-spark{display:block;width:120px;height:28px;overflow:visible}
.pt-spark polyline{fill:none;stroke:currentColor;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.pt-spark circle{fill:currentColor}
.pt-note{font-size:.85rem;color:var(--muted);max-width:80ch}
.pt-reports li{margin:6px 0}
.pt-dl a{margin-right:14px}
@media (max-width:640px){.pt-spark{width:90px}}
"""


# ----------------------------------------------------------------------------- helpers
def _d(iso):
    return datetime.date.fromisoformat(iso)


def _long(iso):
    d = _d(iso)
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def _short(iso):
    d = _d(iso)
    return f"{d.strftime('%b')} {d.day}"


def _month_name(ym):
    y, m = ym.split("-")
    return f"{datetime.date(int(y), int(m), 1).strftime('%B')} {y}"


def _pct(then, now):
    return (now - then) / then * 100 if then else 0.0


def _point_on_or_before(series, day):
    """Latest (date, price) at or before `day`, else None."""
    best = None
    for d, p in series:
        if d <= day:
            best = (d, p)
        else:
            break
    return best


def sparkline(esc, series, label):
    """Inline SVG: one 2px line, last point marked, dates on a real time axis.
    Single series, so no legend; the <title> is the hover tooltip."""
    if len(series) < 2:
        return ""
    w, h, pad = 120, 28, 4
    d0, d1 = _d(series[0][0]), _d(series[-1][0])
    span = max((d1 - d0).days, 1)
    lo, hi = min(p for _, p in series), max(p for _, p in series)
    rng = hi - lo or 1.0
    pts = []
    for d, p in series:
        x = pad + (w - 2 * pad) * (_d(d) - d0).days / span
        y = pad + (h - 2 * pad) * (1 - (p - lo) / rng)
        pts.append(f"{x:.1f},{y:.1f}")
    lx, ly = pts[-1].split(",")
    return (f'<svg class="pt-spark" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(label)}">'
            f'<title>{esc(label)}</title><polyline points="{" ".join(pts)}"/>'
            f'<circle cx="{lx}" cy="{ly}" r="4"/></svg>')


def change_cell(money, then, now, scale):
    """Signed change with a short bar whose length is relative to the biggest move shown."""
    pct = _pct(then, now)
    cls = "pt-down" if pct < 0 else ("pt-up" if pct > 0 else "pt-flat")
    width = max(2, round(56 * min(abs(pct), scale) / scale)) if scale else 2
    sign = "−" if pct < 0 else ("+" if pct > 0 else "")
    return (f'<span class="pt-change {cls}"><span class="pt-bar" style="width:{width}px"></span>'
            f'<b>{sign}{abs(pct):.0f}%</b> <span class="sub">({sign}{money(abs(now - then))})</span></span>')


# ----------------------------------------------------------------------------- analysis
def analyse(meta, history):
    """meta: {asin: {...listing facts...}}; history: {asin: [(date, price), ...]} sorted.
    Only listings that are on the site today are analysed (they are the ones we can link)."""
    rows = {}
    for asin, m in meta.items():
        series = [(d, p) for d, p in history.get(asin, []) if isinstance(p, (int, float))]
        if not series:
            continue
        rows[asin] = dict(m, series=series, first=series[0], last=series[-1],
                          low=min(series, key=lambda t: (t[1], t[0])), high=max(series, key=lambda t: (t[1], t[0])))
    return rows


def recent_moves(rows, latest, days=WINDOW_DAYS):
    """(then, now) per listing with a check at least `days` before the latest capture."""
    cutoff = (_d(latest) - datetime.timedelta(days=days)).isoformat()
    fresh = (_d(latest) - datetime.timedelta(days=MAX_STALE_DAYS)).isoformat()
    out = []
    for asin, r in rows.items():
        if r["last"][0] < fresh:
            continue  # not re-checked lately; its "now" would be stale
        then = _point_on_or_before(r["series"], cutoff)
        if not then or then == r["last"]:
            continue
        out.append((asin, then, r["last"]))
    return out


def month_moves(rows, ym):
    """Per listing: last check before the month vs last check inside it."""
    start = f"{ym}-01"
    end = f"{ym}-31"
    out = []
    for asin, r in rows.items():
        before = [t for t in r["series"] if t[0] < start]
        inside = [t for t in r["series"] if start <= t[0] <= end]
        if before and inside:
            out.append((asin, before[-1], inside[-1]))
    return out


def is_new_low(r):
    """Latest check is the lowest of 3+ checks and sits a real amount below the high."""
    return (len(r["series"]) >= 3 and r["last"][1] <= r["low"][1]
            and r["high"][1] - r["last"][1] >= MIN_MOVE_USD
            and abs(_pct(r["high"][1], r["last"][1])) >= MIN_MOVE_PCT)


def summarise(moves):
    pcts = [_pct(t[1], n[1]) for _, t, n in moves]
    real = [(a, t, n) for a, t, n in moves
            if abs(_pct(t[1], n[1])) >= MIN_MOVE_PCT and abs(n[1] - t[1]) >= MIN_MOVE_USD]
    down = sorted((x for x in real if x[2][1] < x[1][1]), key=lambda x: _pct(x[1][1], x[2][1]))
    up = sorted((x for x in real if x[2][1] > x[1][1]), key=lambda x: -_pct(x[1][1], x[2][1]))
    return {"n": len(moves), "median": statistics.median(pcts) if pcts else 0.0,
            "down": down, "up": up, "flat": len(moves) - len(down) - len(up)}


# ----------------------------------------------------------------------------- rendering
def _moves_table(ctx, rows, moves, heading, empty, limit=TOP_N):
    esc, money = ctx["esc"], ctx["money"]
    moves = moves[:limit]
    if not moves:
        return f'<div class="tablewrap pt"><table><tr><th>{esc(heading)}</th></tr><tr><td class="sub">{esc(empty)}</td></tr></table></div>'
    scale = max(abs(_pct(t[1], n[1])) for _, t, n in moves)
    body = []
    for asin, then, now in moves:
        r = rows[asin]
        label = (f"{len(r['series'])} checks since {_short(r['first'][0])}: low {money(r['low'][1])} on "
                 f"{_short(r['low'][0])}, high {money(r['high'][1])} on {_short(r['high'][0])}")
        body.append(
            f'<tr><td class="name"><a href="{esc(r["url"])}">{esc(r["brand"])} {esc(r["model"])}</a>'
            f'<div class="sub"><a href="{esc(r["cat_url"])}">{esc(r["cat_title"])}</a></div></td>'
            f'<td class="n">{money(then[1])} &rarr; <b>{money(now[1])}</b><div class="sub">{_short(then[0])} &rarr; {_short(now[0])}</div></td>'
            f'<td>{change_cell(money, then[1], now[1], scale)}</td>'
            f'<td class="{"pt-down" if now[1] < then[1] else "pt-up"}">{sparkline(esc, r["series"], label)}</td></tr>')
    return (f'<div class="tablewrap pt"><table><thead><tr><th>{esc(heading)}</th><th class="n">Was &rarr; now</th>'
            f'<th>Change</th><th>Trend</th></tr></thead><tbody>{"".join(body)}</tbody></table></div>')


def _lowest_table(ctx, rows, latest):
    esc, money = ctx["esc"], ctx["money"]
    cands = []
    for asin, r in rows.items():
        if is_new_low(r):
            cands.append((asin, _pct(r["high"][1], r["last"][1])))
    cands.sort(key=lambda t: t[1])
    if not cands:
        return '<p class="pt-note">Nothing is sitting at a new low right now.</p>'
    body = []
    for asin, pct in cands[:LOW_N]:
        r = rows[asin]
        body.append(
            f'<tr><td class="name"><a href="{esc(r["url"])}">{esc(r["brand"])} {esc(r["model"])}</a>'
            f'<div class="sub"><a href="{esc(r["cat_url"])}">{esc(r["cat_title"])}</a></div></td>'
            f'<td class="n">{money(r["last"][1])}<div class="sub">checked {_short(r["last"][0])}</div></td>'
            f'<td class="n">{money(r["high"][1])}<div class="sub">{_short(r["high"][0])}</div></td>'
            f'<td><span class="pt-change pt-down"><b>−{abs(pct):.0f}%</b> <span class="sub">vs its high in our checks</span></span></td>'
            f'<td class="n">{len(r["series"])}</td></tr>')
    return (f'<div class="tablewrap pt"><table><thead><tr><th>{esc(ctx["noun"].capitalize())}</th><th class="n">Now</th>'
            f'<th class="n">High</th><th>Below its high</th><th class="n">Checks</th></tr></thead><tbody>{"".join(body)}</tbody></table></div>')


def _category_table(ctx, rows, moves, days=WINDOW_DAYS):
    esc, money = ctx["esc"], ctx["money"]
    by_cat = {}
    for asin, r in rows.items():
        by_cat.setdefault(r["cat_slug"], {"title": r["cat_title"], "url": r["cat_url"], "n": 0, "pcts": [], "low": 0, "best": None})
        c = by_cat[r["cat_slug"]]
        c["n"] += 1
        if is_new_low(r):
            c["low"] += 1
    for asin, then, now in moves:
        c = by_cat[rows[asin]["cat_slug"]]
        pct = _pct(then[1], now[1])
        c["pcts"].append(pct)
        real = abs(pct) >= MIN_MOVE_PCT and abs(now[1] - then[1]) >= MIN_MOVE_USD
        if pct < 0 and real and (c["best"] is None or pct < c["best"][1]):
            c["best"] = (asin, pct)
    body = []
    for slug, c in sorted(by_cat.items(), key=lambda kv: kv[1]["title"].lower()):
        med = statistics.median(c["pcts"]) if c["pcts"] else None
        med_cell = ("—" if med is None else
                    f'<span class="{"pt-down" if med < -0.05 else "pt-up" if med > 0.05 else "pt-flat"}">'
                    f'{"-" if med < -0.05 else "+" if med > 0.05 else ""}{abs(med):.1f}%</span>')
        best = ""
        if c["best"]:
            r = rows[c["best"][0]]
            best = f'<a href="{esc(r["url"])}">{esc(r["brand"])} {esc(r["model"])}</a> <span class="pt-down">-{abs(c["best"][1]):.0f}%</span>'
        body.append(f'<tr><td class="name"><a href="{esc(c["url"])}">{esc(c["title"])}</a></td><td class="c">{c["n"]}</td>'
                    f'<td class="c">{len(c["pcts"])}</td><td class="c">{med_cell}</td><td class="c">{c["low"]}</td><td class="name">{best}</td></tr>')
    return (f'<div class="tablewrap pt"><table><tr><th>{esc(ctx["category_label"])}</th><th>Tracked</th><th>With {days}-day data</th>'
            f'<th>Median {days}-day change</th><th>At a new low</th><th>Biggest drop</th></tr>{"".join(body)}</table></div>')


def _stats(items):
    return '<div class="pt-stats">' + "".join(f"<div><b>{v}</b><span>{k}</span></div>" for k, v in items) + "</div>"


def _write_downloads(ctx, rows):
    out = ctx["out"]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["asin", "brand", "model", ctx["category_label"].lower().replace(" ", "_"), "date", "price_usd", "page_url"])
    for asin, r in sorted(rows.items()):
        for d, p in r["series"]:
            w.writerow([asin, r["brand"], r["model"], r["cat_slug"], d, f"{p:.2f}", r.get("abs_url", r["url"])])
    (out / "price-history.csv").write_text(buf.getvalue(), encoding="utf-8")
    data = {"site": ctx["brand"], "url": f"{ctx['base']}/price-tracker.html", "source": "Amazon listing prices captured on the dates shown",
            "reuse": "Free to quote and reuse with a link back to the tracker page.",
            "listings": {asin: {"brand": r["brand"], "model": r["model"], "name": r["name"], ctx["category_label"].lower().replace(" ", "_"): r["cat_slug"],
                                "page_url": r.get("abs_url", r["url"]), "prices": [{"date": d, "usd": p} for d, p in r["series"]]}
                         for asin, r in sorted(rows.items())}}
    (out / "price-history.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------- pages
def build(site, meta, history, ctx):
    """Build the hub, the monthly reports and the downloads. Returns [(slug, lastmod)]."""
    esc, money, base = ctx["esc"], ctx["money"], ctx["base"]
    rows = analyse(meta, history)
    if not rows:
        return []
    dates = sorted({d for r in rows.values() for d, _ in r["series"]})
    latest, first = dates[-1], dates[0]
    checks = sum(len(r["series"]) for r in rows.values())
    cats = {r["cat_slug"] for r in rows.values()}
    days = WINDOW_DAYS
    moves = recent_moves(rows, latest, days)
    for alt in (14, 7):
        if len(moves) >= 20:
            break
        days = alt
        moves = recent_moves(rows, latest, days)
    s = summarise(moves)
    low_now = sum(1 for r in rows.values() if is_new_low(r))
    months = sorted({d[:7] for d in dates})
    reports = []
    for ym in months:
        mm = month_moves(rows, ym)
        if len(mm) >= (10 if ym == latest[:7] else 1):
            reports.append((ym, mm))
    for stale in ctx["out"].glob("price-report-*.html"):
        if stale.stem[len("price-report-"):] not in {ym for ym, _ in reports}:
            stale.unlink()
    _write_downloads(ctx, rows)

    noun, nouns = ctx["noun"], ctx["nouns"]
    med_txt = ("n/a" if not s["n"] else "flat" if abs(s["median"]) < 0.05 else
               f'{"down" if s["median"] < 0 else "up"} {abs(s["median"]):.1f}%')
    report_links = "".join(
        f'<li><a href="price-report-{ym}.html">{esc(_month_name(ym))}{" (so far)" if ym == latest[:7] else ""}</a>: '
        f'{len(mm)} {nouns} compared</li>' for ym, mm in reversed(reports))
    body = f"""
  {ctx["nav"]}
  <section class="lead">
    <h1>{esc(ctx["brand"])} price tracker</h1>
    <p class="sub">{len(rows):,} Amazon {nouns} across {len(cats)} {ctx["category_label_plural"]}, re-checked on a rotation since {_long(first)}.</p>
    <p class="intro">Every time we refresh a page we log each {noun}'s Amazon price under that day's date. This page reads that log:
    which {nouns} moved most in the last {days} days, which are sitting at the lowest price we have ever recorded, and how each
    {ctx["category_label"].lower()} is trending. Prices are what Amazon showed on the dates listed; they change daily, so check the listing before you buy.
    Last capture: {_long(latest)}.</p>
  </section>
  {_stats([(f"{nouns} tracked", f"{len(rows):,}"), ("price checks logged", f"{checks:,}"), (f"{nouns} with {days}-day data", f"{s['n']:,}"),
           (f"median {days}-day change", med_txt), ("at a new low right now", f"{low_now:,}")])}
  <p class="pt-note">Of the {s['n']:,} {nouns} with a check at least {days} days old, {len(s['down'])} fell and {len(s['up'])} rose by {MIN_MOVE_PCT:.0f}% or more; {s['flat']} held within that band.{(" " + ctx["caveat"]) if ctx.get("caveat") else ""}</p>
  <p class="swipe-hint">Swipe a table sideways for the trend column.</p>
  <section class="pt-grid">
    <div>
      <h2>Biggest drops, last {days} days</h2>
      {_moves_table(ctx, rows, s["down"], noun.capitalize(), f"No {noun} fell {MIN_MOVE_PCT:.0f}% or more in this window.")}
    </div>
    <div>
      <h2>Biggest rises, last {days} days</h2>
      {_moves_table(ctx, rows, s["up"], noun.capitalize(), f"No {noun} rose {MIN_MOVE_PCT:.0f}% or more in this window.")}
    </div>
  </section>
  <section>
    <h2>At their lowest price in our checks</h2>
    <p class="pt-note">{nouns.capitalize()} with at least three checks whose latest price is the lowest we have recorded, ranked by how far below their high they sit.</p>
    {_lowest_table(ctx, rows, latest)}
  </section>
  <section class="compare" id="compare">
    <h2>By {ctx["category_label"].lower()}</h2>
    {'<p class="tiny muted sort-hint">Tap a column heading to sort.</p>' if ctx["table_js"] else ""}
    {_category_table(ctx, rows, moves, days)}
  </section>
  <section>
    <h2>Monthly price reports</h2>
    <ul class="pt-reports">{report_links or "<li>The first report arrives once a month has ten or more comparable checks.</li>"}</ul>
  </section>
  <section class="about-body">
    <h2 id="how-this-is-measured">How this is measured</h2>
    <p>A check is the price Amazon showed for a listing on the day one of our pages was refreshed. Each page is re-priced about weekly,
    so most {nouns} have one check per week. The {days}-day change compares the latest check with the last check taken at least
    {days} days earlier; {nouns} without a check that old are left out rather than guessed. Moves under {MIN_MOVE_PCT:.0f}% or
    under {money(MIN_MOVE_USD)} are treated as noise. A monthly report compares each {noun}'s last check before the month with its last
    check inside it. We only track {nouns} currently ranked on the site; when one is removed, its history stops.</p>
    <h2>Download the data</h2>
    <p class="pt-dl"><a href="price-history.csv">price-history.csv</a> <a href="price-history.json">price-history.json</a></p>
    <p class="pt-note">Free to quote and reuse with a link back to this page. Columns: ASIN, brand, model, {ctx["category_label"].lower()}, date, price in USD, our page.
    {ctx["extra_note"]}</p>
  </section>
  {ctx["table_js"]}
  {ctx["to_top"]}"""
    slug = "price-tracker"
    title = f"{ctx['brand']} price tracker: {len(rows):,} Amazon {nouns}, re-checked weekly"
    desc = (f"Tracked Amazon prices for {len(rows):,} {nouns} across {len(cats)} {ctx['category_label_plural']}: the biggest drops and rises of the "
            f"last {days} days, {nouns} at their lowest recorded price, and the full dataset to download.")
    sd = {"@context": "https://schema.org", "@type": "Dataset", "name": f"{ctx['brand']} Amazon price history",
          "description": desc, "url": f"{base}/{slug}.html", "license": f"{base}/{slug}.html#how-this-is-measured",
          "creator": {"@type": "Organization", "name": ctx["brand"], "url": f"{base}/"},
          "temporalCoverage": f"{first}/{latest}", "dateModified": latest,
          "keywords": [f"{noun} prices", "Amazon price history", ctx["brand"]],
          "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{base}/price-history.csv"},
                           {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{base}/price-history.json"}]}
    ctx["write"](slug, title, body, desc, sd, latest)
    out = [(slug, latest)]
    for ym, mm in reports:
        out.append(_report(site, ctx, rows, ym, mm, latest, reports))
    return out


def _report(site, ctx, rows, ym, mm, latest, reports):
    esc, money, base = ctx["esc"], ctx["money"], ctx["base"]
    s = summarise(mm)
    noun, nouns = ctx["noun"], ctx["nouns"]
    name = _month_name(ym)
    current = ym == latest[:7]
    month_dates = sorted({d for r in rows.values() for d, _ in r["series"] if d.startswith(ym)})
    lastmod = month_dates[-1]
    others = "".join(f'<li><a href="price-report-{o}.html">{esc(_month_name(o))}</a></li>' for o, _ in reversed(reports) if o != ym)
    # Per-category medians for the month
    by_cat = {}
    for asin, then, now in mm:
        r = rows[asin]
        by_cat.setdefault(r["cat_slug"], {"title": r["cat_title"], "url": r["cat_url"], "pcts": []})["pcts"].append(_pct(then[1], now[1]))
    cat_rows = sorted(((statistics.median(c["pcts"]), c) for c in by_cat.values() if len(c["pcts"]) >= 3), key=lambda t: t[0])
    cat_table = ""
    if cat_rows:
        def cell(m):
            cls = "pt-down" if m < -0.05 else "pt-up" if m > 0.05 else "pt-flat"
            return f'<span class="{cls}">{"−" if m < -0.05 else "+" if m > 0.05 else ""}{abs(m):.1f}%</span>'
        cat_table = ('<div class="tablewrap pt"><table><tr><th>' + esc(ctx["category_label"]) + f'</th><th class="c">{nouns.capitalize()} compared</th><th class="c">Median change</th></tr>'
                     + "".join(f'<tr><td class="name"><a href="{esc(c["url"])}">{esc(c["title"])}</a></td><td class="c">{len(c["pcts"])}</td><td class="c">{cell(m)}</td></tr>' for m, c in cat_rows)
                     + "</table></div>")
    body = f"""
  {ctx["nav"]}
  <section class="lead">
    <p class="byline"><a href="price-tracker.html">&larr; Price tracker</a></p>
    <h1>{esc(ctx["brand"])} price report: {esc(name)}{" (so far)" if current else ""}</h1>
    <p class="sub">{s['n']:,} {nouns} with a price check before {esc(name)} and another inside it{f", through {_long(lastmod)}" if current else ""}.</p>
    <p class="intro">Across those {nouns} the median price change was {"down" if s["median"] < 0 else "up" if s["median"] > 0 else "flat at"} {abs(s["median"]):.1f}%.
    {len(s['down'])} fell and {len(s['up'])} rose by {MIN_MOVE_PCT:.0f}% or more; {s['flat']} stayed within that band. Each {noun} is compared with its own last
    check before the month, so the figures are per listing, not a basket average.</p>
  </section>
  {_stats([(f"{nouns} compared", f"{s['n']:,}"), ("median change", f'{"−" if s["median"] < 0 else "+" if s["median"] > 0 else ""}{abs(s["median"]):.1f}%'),
           (f"fell {MIN_MOVE_PCT:.0f}%+", f"{len(s['down'])}"), (f"rose {MIN_MOVE_PCT:.0f}%+", f"{len(s['up'])}"), ("check dates", f"{len(month_dates)}")])}
  <p class="swipe-hint">Swipe a table sideways for the trend column.</p>
  <section class="pt-grid">
    <div><h2>Biggest drops</h2>{_moves_table(ctx, rows, s["down"], noun.capitalize(), f"No {noun} fell {MIN_MOVE_PCT:.0f}% or more.", limit=10)}</div>
    <div><h2>Biggest rises</h2>{_moves_table(ctx, rows, s["up"], noun.capitalize(), f"No {noun} rose {MIN_MOVE_PCT:.0f}% or more.", limit=10)}</div>
  </section>
  {"<section><h2>By " + esc(ctx["category_label"].lower()) + "</h2><p class='pt-note'>" + esc(ctx["category_label_plural"].capitalize()) + " with three or more comparable " + esc(nouns) + ".</p>" + cat_table + "</section>" if cat_table else ""}
  <section class="about-body">
    <h2>Method and data</h2>
    <p>Prices are what Amazon showed on the dates we refreshed each page. The change for a {noun} is its last check in {esc(name)} against its
    last check before the month began. Moves under {MIN_MOVE_PCT:.0f}% or {money(MIN_MOVE_USD)} count as unchanged. Full method and the
    downloadable dataset are on the <a href="price-tracker.html">price tracker</a>. Free to quote with a link back.</p>
    {"<h2>Other months</h2><ul class='pt-reports'>" + others + "</ul>" if others else ""}
  </section>
  {ctx["to_top"]}"""
    slug = f"price-report-{ym}"
    title = f"{ctx['brand']} price report: {name}, Amazon {noun} prices"
    med_word = "flat" if abs(s["median"]) < 0.05 else ("down" if s["median"] < 0 else "up")
    med_desc = "median change flat" if med_word == "flat" else f"median change {abs(s['median']):.1f}% {med_word}"
    desc = (f"{s['n']:,} Amazon {nouns} compared across {name}: {med_desc}, {len(s['down'])} fell and {len(s['up'])} rose {MIN_MOVE_PCT:.0f}% or more. Biggest moves by {noun} and {ctx['category_label'].lower()}.")
    sd = {"@context": "https://schema.org", "@type": "Article", "headline": title, "datePublished": month_dates[0], "dateModified": lastmod,
          "author": {"@type": "Organization", "name": ctx["brand"], "url": f"{base}/"},
          "publisher": {"@type": "Organization", "name": ctx["brand"], "url": f"{base}/"},
          "mainEntityOfPage": f"{base}/{slug}.html", "description": desc}
    ctx["write"](slug, title, body, desc, sd, lastmod)
    return (slug, lastmod)
