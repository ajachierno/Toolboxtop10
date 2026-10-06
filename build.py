#!/usr/bin/env python3
"""ToolTop10 static site generator.

Reads data/site.json + data/<category>.json, scores and ranks each product on a
single 100-point scale, then writes a static site into docs/ (served by GitHub Pages).

No third-party dependencies. Run:  python build.py
"""
import datetime
import json
import math
import re
import html
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
OUT = ROOT / "docs"
ASSETS = OUT / "assets"


# ----------------------------------------------------------------------------- data
def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


# ------------------------------------------------------------------- price history
# data/price-history.json: {asin: [[date, price], ...]}. Every build records each
# product's current price under its category's data_captured date, so each refresh
# adds a point automatically. Seeded from git history by scripts/seed_price_history.py.
PRICE_HISTORY = {}


def record_prices(site):
    path = DATA / "price-history.json"
    hist = {a: dict(v) for a, v in json.loads(path.read_text(encoding="utf-8")).items()} if path.exists() else {}
    before = json.dumps(hist, sort_keys=True)
    for c in site["categories"]:
        cat = load(f"{c['slug']}.json")
        when = cat.get("data_captured") or site["updated"]
        for p in cat["products"] + cat.get("avoid", []):
            if isinstance(p.get("price"), (int, float)):
                hist.setdefault(p["asin"], {})[when] = p["price"]
    PRICE_HISTORY.clear()
    PRICE_HISTORY.update({a: sorted(d.items()) for a, d in hist.items()})
    if json.dumps(hist, sort_keys=True) != before:
        lines = [f"  {json.dumps(a)}: {json.dumps(v)}" for a, v in sorted(PRICE_HISTORY.items())]
        path.write_text("{\n" + ",\n".join(lines) + "\n}\n", encoding="utf-8")


def price_note(p):
    """'Lowest in our checks' line, shown once a product has 2+ dated captures."""
    pts = PRICE_HISTORY.get(p["asin"], [])
    if len(pts) < 2 or not isinstance(p.get("price"), (int, float)):
        return ""
    low = min(v for _, v in pts)
    since = _short_date(pts[0][0])
    if all(v == p["price"] for _, v in pts):
        n = "both" if len(pts) == 2 else f"all {len(pts)}"
        return f'<div class="lowprice">Same price in {n} of our checks since {since}</div>'
    if p["price"] <= low:
        return f'<div class="lowprice best">Lowest price in our {len(pts)} checks since {since}</div>'
    low_date = max(d for d, v in pts if v == low)
    return (f'<div class="lowprice">Lowest in our checks: {money(low)} on {_short_date(low_date)}'
            f'</div>')


def amazon_url(asin, tag, domain):
    base = f"https://{domain}/dp/{asin}"
    return f"{base}?tag={tag}&linkCode=ll1" if tag else base


# --------------------------------------------------------------------------- scoring
def feature_score(features, fweights):
    return min(1.0, sum(fweights.get(k, 0) for k, on in features.items() if on))


def score_product(p, cat):
    w = cat["weights"]
    ceil = cat.get("reviews_ceiling", 60000)
    rating_s = p["rating"] / 5.0
    reviews_s = min(1.0, math.log10(p["reviews_count"] + 1) / math.log10(ceil))
    feat_s = feature_score(p["features"], cat["feature_weights"])
    composite = w["rating"] * rating_s + w["reviews"] * reviews_s + w["features"] * feat_s
    # Kept for the "Why this score" breakdown on each card: (label, weight, 0-1 sub-score).
    p["score_parts"] = [("Star rating", w["rating"], rating_s),
                        ("Number of reviews", w["reviews"], reviews_s),
                        ("Features", w["features"], feat_s)]
    return round(composite * 100)


def rank_products(cat):
    for p in cat["products"]:
        p["score"] = score_product(p, cat)
    ranked = sorted(cat["products"], key=lambda p: (-p["score"], -p["reviews_count"]))
    for i, p in enumerate(ranked, 1):
        p["rank"] = i
    cap = cat.get("budget_cap", 60)
    # Badges go to ready-to-use kits (battery included), never a tool-only unit.
    kits = [p for p in ranked if p["features"].get("kit")]
    # Editorial overrides (data flags) take precedence over the computed pick.
    forced_overall = next((p for p in ranked if p.get("force_overall")), None)
    forced_budget = next((p for p in ranked if p.get("force_budget")), None)
    overall = forced_overall or (max(kits, key=lambda p: p["score"]) if kits else ranked[0])
    budget_pool = ([p for p in kits if p["price"] <= cap and p is not overall]
                   or [p for p in ranked if p["price"] <= cap and p is not overall])
    budget = forced_budget or (max(budget_pool, key=lambda p: p["score"]) if budget_pool else None)
    # Editorial "money no object" pick — the best regardless of price (data flag).
    premium = next((p for p in ranked if p.get("premium")), None)
    for p in ranked:
        p["badge"] = None
        p["badge_kind"] = None
    overall["badge"] = "Best Overall"
    overall["badge_kind"] = "overall"
    if budget and budget is not overall:
        budget["badge"] = "Best Budget"
        budget["badge_kind"] = "budget"
    if premium and premium is not overall and premium is not budget:
        premium["badge"] = "Money No Object"
        premium["badge_kind"] = "premium"
    return ranked, overall, budget, premium


# --------------------------------------------------------------------------- helpers
def esc(s):
    return html.escape(str(s)) if s is not None else ""


def money(v):
    return f"${v:,.2f}".rstrip("0").rstrip(".") if v == int(v) else f"${v:,.2f}"


def stars(rating):
    pct = round(rating / 5 * 100)
    return (f'<span class="stars" style="--pct:{pct}%" '
            f'aria-label="{rating} out of 5 stars"></span>')


# Fallback schema (cordless drills / impact drivers). Categories may override via
# "spec_fields" (card grid) and "table_columns" (comparison table) in their JSON.
DEFAULT_SPEC_FIELDS = [
    {"key": "voltage", "label": "Voltage"}, {"key": "chuck", "label": "Chuck"},
    {"key": "max_rpm", "label": "Max speed"}, {"key": "speeds", "label": "Transmission"},
    {"key": "torque", "label": "Torque"}, {"key": "clutch", "label": "Clutch"},
    {"key": "battery", "label": "Battery"}, {"key": "weight", "label": "Weight"},
]
DEFAULT_TABLE_COLUMNS = [
    {"key": "voltage", "label": "Voltage"}, {"key": "max_rpm", "label": "Max speed"},
    {"key": "chuck", "label": "Chuck"}, {"key": "brushless", "label": "Brushless", "type": "bool"},
]


def spec_rows(specs, fields):
    out = []
    for f in fields:
        key, label = f["key"], f["label"]
        v = specs.get(key)
        if v is None or v == "":
            v = "&mdash;"
        elif key == "max_rpm" and isinstance(v, (int, float)):
            v = f"{v:,} rpm"
        else:
            v = esc(v)
        out.append(f'<div class="spec"><dt>{esc(label)}</dt><dd>{v}</dd></div>')
    return "\n".join(out)


# --------------------------------------------------------------------------- render
def render_hero_card(p, site, cat):
    url = amazon_url(p["asin"], site["affiliate_tag"], site["amazon_domain"])
    return f"""
    <a class="hero-card {esc(p['badge_kind'])}"
       href="{url}" target="_blank" rel="sponsored nofollow noopener">
      <span class="hero-tag">{esc(p['badge'])}</span>
      <img src="{esc(p['image'])}" alt="{esc(p['name'])}" loading="lazy">
      <div class="hero-body">
        <div class="hero-brand">{esc(p['brand'])}</div>
        <div class="hero-name">{esc(p['name'])}</div>
        <div class="hero-meta">{stars(p['rating'])} <b>{p['rating']}</b>
          <span class="muted">({p['reviews_count']:,})</span></div>
        <div class="hero-price">{money(p['price'])}</div>
        <span class="btn">View on Amazon &rarr;</span>
      </div>
    </a>"""


def render_breakdown(p, cat):
    """Collapsible per-factor breakdown that adds up to the card's 0-100 score."""
    parts = [x for x in p.get("score_parts", []) if x[1]]
    # Whole points per factor that add up exactly to the rounded score (largest remainder).
    raw = [w * sub * 100 for _, w, sub in parts]
    pts = [math.floor(v) for v in raw]
    for i in sorted(range(len(raw)), key=lambda i: raw[i] - pts[i], reverse=True)[:max(0, p["score"] - sum(pts))]:
        pts[i] += 1
    rows = []
    for (label, weight, sub), pt in zip(parts, pts):
        rows.append(f'<li><span class="bd-label">{esc(label)} <i>{round(weight * 100)}% of score</i></span>'
                    f'<span class="bd-bar"><span style="width:{round(sub * 100)}%"></span></span>'
                    f'<span class="bd-num">{round(sub * 100)}/100 &rarr; <b>{pt}</b> pts</span></li>')
    fw = cat.get("feature_weights", {})
    has = [k for k in fw if p["features"].get(k)]
    lacks = [k for k in fw if not p["features"].get(k)]
    feat = ""
    if fw:
        fmt = lambda ks: ", ".join(esc(FEATURE_PROSE.get(k, k.replace("_", " "))) for k in ks)
        if not lacks:
            feat = f"<b>Has every feature we score:</b> {fmt(has)}."
        else:
            feat = (f"<b>Has:</b> {fmt(has)}. " if has else "") + f"<b>Missing:</b> {fmt(lacks)}."
        feat = f'<p class="bd-feat">{feat}</p>'
    return (f'<details class="breakdown"><summary>Why this score</summary>'
            f'<ul>{"".join(rows)}</ul>{feat}'
            f'<p class="bd-total">Total: <b>{p["score"]}</b>/100. '
            f'<a href="#howwerank">How the score works</a></p></details>')


def render_card(p, site, spec_fields, cat=None):
    url = amazon_url(p["asin"], site["affiliate_tag"], site["amazon_domain"])
    badge = (f'<span class="badge {esc(p["badge_kind"])}">{esc(p["badge"])}</span>'
             if p["badge"] else "")
    pros = "\n".join(f"<li>{esc(x)}</li>" for x in p["pros"])
    cons = "\n".join(f"<li>{esc(x)}</li>" for x in p["cons"])
    return f"""
    <article class="card" id="{esc(p['asin'])}">
      <div class="rank">#{p['rank']}</div>
      <div class="card-head">
        <div class="card-img"><img src="{esc(p['image'])}" alt="{esc(p['name'])}" loading="lazy"></div>
        <div class="card-title">
          {badge}
          <div class="brand">{esc(p['brand'])}</div>
          <h3>{esc(p['name'])}</h3>
          <div class="rate">{stars(p['rating'])} <b>{p['rating']}</b>
            <span class="muted">{p['reviews_count']:,} reviews</span></div>
          <div class="scorebar"><span style="width:{p['score']}%"></span>
            <em>Score {p['score']}/100</em></div>
          {render_breakdown(p, cat) if cat else ""}
        </div>
        <div class="card-buy">
          <div class="price">{money(p['price'])}</div>
          {price_note(p)}
          <a class="btn" href="{url}" target="_blank" rel="sponsored nofollow noopener">Check price on Amazon</a>
          <div class="tiny muted">{esc(p.get('bought',''))}</div>
        </div>
      </div>
      <p class="verdict">{esc(p['verdict'])}</p>
      <dl class="specs">{spec_rows(p['specs'], spec_fields)}</dl>
      <div class="pc">
        <div class="pros"><h4>Pros</h4><ul>{pros}</ul></div>
        <div class="cons"><h4>Cons</h4><ul>{cons}</ul></div>
      </div>
    </article>"""


def _table_cell(p, col):
    key = col["key"]
    if col.get("type") == "bool":
        return "Yes" if p["features"].get(key) else "No"
    v = p["specs"].get(key)
    if v is None or v == "":
        return "&mdash;"
    if key == "max_rpm" and isinstance(v, (int, float)):
        return f"{v:,}"
    return esc(v)


def render_table(ranked, avoid, site, columns):
    heads = "".join(f"<th>{esc(c['label'])}</th>" for c in columns)
    head = (f"<tr><th>#</th><th>Tool</th><th>Price</th><th>Rating</th>"
            f"<th>Reviews</th>{heads}<th>Score</th></tr>")
    rows = []
    for p in ranked:
        cells = "".join(
            f'<td class="{"c" if c.get("type") == "bool" else ""}">{_table_cell(p, c)}</td>'
            for c in columns)
        rows.append(
            f'<tr data-brand="{esc(p["brand"])}"><td class="c">{p["rank"]}</td>'
            f'<td><a href="#{p["asin"]}">{esc(p["brand"])} {esc(p["model"])}</a></td>'
            f'<td>{money(p["price"])}</td>'
            f'<td class="c">{p["rating"]}</td>'
            f'<td class="c">{p["reviews_count"]:,}</td>'
            f'{cells}'
            f'<td class="c"><b>{p["score"]}</b></td></tr>')
    for a in avoid:
        rows.append(
            f'<tr class="avoid-row"><td class="c">&#10005;</td>'
            f'<td><a href="#avoid-{a["asin"]}">{esc(a["brand"])} {esc(a["model"])}</a></td>'
            f'<td>{money(a["price"])}</td>'
            f'<td class="c">{a["rating"]}</td>'
            f'<td class="c">{a["reviews_count"]:,}</td>'
            f'<td class="c" colspan="{len(columns)}">{esc(a.get("flag", "Avoid"))}</td>'
            f'<td class="c"><b>AVOID</b></td></tr>')
    return f'<div class="tablewrap"><table>{head}{"".join(rows)}</table></div>'


def render_table_filters(ranked):
    """Brand filter chips for the comparison table (wired up by TABLE_JS)."""
    brands = sorted(set(p["brand"] for p in ranked), key=str.lower)
    if len(brands) < 2:
        return ""
    chips = "".join(f'<button type="button" data-brand="{esc(b)}">{esc(b)}</button>' for b in brands)
    return (f'<div class="tfilter" hidden><span class="muted">Brand:</span>'
            f'<button type="button" class="on" data-brand="">All</button>{chips}</div>')


# Click a column header to sort the comparison table; brand chips filter rows.
# Without JS the static table (ranked by score) is unchanged. Avoid rows stay last.
TABLE_JS = r"""<script>(function(){
var sec=document.getElementById('compare');if(!sec)return;var t=sec.querySelector('table');if(!t)return;
var rows=function(){return Array.prototype.slice.call(t.rows,1)};
function val(td){var x=td.textContent.trim().replace(/[$,]/g,'');if(x===''||x==='—')return null;
var m=x.match(/^(\d+)[ -]+(\d+)\/(\d+)/);if(m)return +m[1]+m[2]/m[3];
m=x.match(/^(\d+)\/(\d+)/);if(m)return m[1]/m[2];
var n=parseFloat(x);return isNaN(n)?x.toLowerCase():n}
var ths=t.rows[0].cells;
Array.prototype.forEach.call(ths,function(th,i){if(i===1)return;
var b=document.createElement('button');b.type='button';b.className='sortbtn';b.textContent=th.textContent;
th.textContent='';th.appendChild(b);
b.addEventListener('click',function(){
var asc=th.getAttribute('aria-sort')?th.getAttribute('aria-sort')!=='ascending':(i===0||i===2);
Array.prototype.forEach.call(ths,function(h){h.removeAttribute('aria-sort')});
th.setAttribute('aria-sort',asc?'ascending':'descending');
var rs=rows(),keep=rs.filter(function(r){return !r.classList.contains('avoid-row')}),
av=rs.filter(function(r){return r.classList.contains('avoid-row')});
keep.sort(function(a,c){var x=val(a.cells[i]),y=val(c.cells[i]);
if(x===null&&y===null)return 0;if(x===null)return 1;if(y===null)return -1;
var r=(typeof x===typeof y)?(x<y?-1:x>y?1:0):(typeof x==='number'?-1:1);return asc?r:-r});
keep.concat(av).forEach(function(r){r.parentNode.appendChild(r)})})});
var f=sec.querySelector('.tfilter');if(!f)return;f.hidden=false;
f.addEventListener('click',function(e){var b=e.target.closest('button');if(!b)return;
Array.prototype.forEach.call(f.children,function(c){c.classList&&c.classList.toggle('on',c===b)});
var want=b.getAttribute('data-brand');
rows().forEach(function(r){if(r.classList.contains('avoid-row'))return;
r.hidden=!!want&&r.getAttribute('data-brand')!==want})})})();</script>"""


def render_feature_weights(cat):
    fw = sorted(cat.get("feature_weights", {}).items(), key=lambda kv: -kv[1])
    if not fw:
        return ""
    prose = lambda k: re.sub(r" \(.*\)$", "", FEATURE_PROSE.get(k, k.replace("_", " ")))
    parts = ", ".join(f"{esc(prose(k))} ({round(v * 100)}%)" for k, v in fw)
    ceil = cat.get("reviews_ceiling", 60000)
    return (f"<p>The features score is built from {parts}, capped at 100. The review-count score "
            f"is on a log scale, so each tenfold jump in reviews adds the same amount, and {ceil:,} or "
            f"more reviews gets full marks. Open <b>Why this score</b> on any tool to see its numbers.</p>")


def render_changes(cat):
    """Last few dated changelog entries from the category JSON, newest first."""
    log = sorted(cat.get("changelog", []), key=lambda e: e["date"], reverse=True)[:3]
    if not log:
        return ""
    items = "".join(
        f'<li><time datetime="{esc(e["date"])}">{_short_date(e["date"])}</time> {esc(e["note"])}</li>'
        for e in log)
    return f"""
  <section class="changes" id="changes">
    <h2>What changed</h2>
    <p class="muted">We re-check every listing on this page on a rotation. The most recent changes:</p>
    <ul>{items}</ul>
  </section>"""


def _short_date(iso):
    d = datetime.date.fromisoformat(iso)
    return f"{d:%b} {d.day}, {d.year}"


def render_avoid(avoid, site):
    if not avoid:
        return ""
    cards = []
    for a in avoid:
        url = amazon_url(a["asin"], site["affiliate_tag"], site["amazon_domain"])
        reasons = "\n".join(f"<li>{esc(r)}</li>" for r in a["reasons"])
        cards.append(f"""
      <article class="avoid-card" id="avoid-{esc(a['asin'])}">
        <span class="avoid-flag">&#10005; Avoid</span>
        <div class="avoid-head">
          <div class="card-img"><img src="{esc(a['image'])}" alt="{esc(a['name'])}" loading="lazy"></div>
          <div class="card-title">
            <div class="brand">{esc(a['brand'])}</div>
            <h3>{esc(a['name'])}</h3>
            <div class="rate">{stars(a['rating'])} <b>{a['rating']}</b>
              <span class="muted">{a['reviews_count']:,} reviews</span> &nbsp;
              <span class="muted">{money(a['price'])}</span></div>
          </div>
        </div>
        <p class="verdict"><b>{esc(a['verdict'])}</b></p>
        <div class="reasons"><h4>Why we'd skip it</h4><ul>{reasons}</ul></div>
        <a class="btn ghost" href="{url}" target="_blank" rel="sponsored nofollow noopener">See the listing on Amazon (so you recognize it)</a>
      </article>""")
    return f"""
  <section class="avoid" id="avoid">
    <h2>Tools to avoid</h2>
    <p class="avoid-lead">Not everything in the search results deserves your money.
    This one would rank dead last on our scale — here's the listing to walk past, and exactly why.</p>
    {''.join(cards)}
  </section>"""


def render_guide(items):
    out = []
    for it in items:
        out.append(f"<details><summary>{esc(it['q'])}</summary>"
                   f"<p>{esc(it['a'])}</p></details>")
    return "\n".join(out)


def meta_desc(text, limit=157):
    """Trim to a clean, search-friendly meta description length at a word boundary."""
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",.;:—- ")
    return cut + "…"


def jsonld(*objs):
    """Render one or more schema.org objects as a JSON-LD script block."""
    items = [o for o in objs if o]
    if not items:
        return ""
    payload = items[0] if len(items) == 1 else items
    return ('<script type="application/ld+json">'
            + json.dumps(payload, ensure_ascii=False) + '</script>')


_TRACKING_FORMATS = {
    "cloudflare_beacon_token": r"[0-9a-f]{32}",
    "ga4_measurement_id": r"G-[A-Z0-9]{4,16}",
    "google_site_verification": r"[A-Za-z0-9_-]{20,100}",
    "bing_site_verification": r"[A-F0-9]{32}",
    "pinterest_site_verification": r"[a-f0-9]{32}",
    "indexnow_key": r"[a-f0-9]{32}",
}


def load_tracking():
    """Read data/tracking.json (kept apart from site.json so the daily category
    process never collides with it). Blank values are skipped; a malformed value
    stops the build rather than shipping a broken or injectable tag."""
    path = DATA / "tracking.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    ids = {}
    for key, pattern in _TRACKING_FORMATS.items():
        value = (raw.get(key) or "").strip()
        if value and not re.fullmatch(pattern, value):
            raise SystemExit(f"data/tracking.json: {key}={value!r} does not look valid")
        if value:
            ids[key] = value
    return ids


def tracking_head(ids, is_home):
    """Analytics on every page; ownership-verification tags on the home page only
    (that is where Search Console and Bing look for them)."""
    tags = []
    if is_home and ids.get("google_site_verification"):
        tags.append(f'<meta name="google-site-verification" content="{ids["google_site_verification"]}">')
    if is_home and ids.get("bing_site_verification"):
        tags.append(f'<meta name="msvalidate.01" content="{ids["bing_site_verification"]}">')
    if is_home and ids.get("pinterest_site_verification"):
        tags.append(f'<meta name="p:domain_verify" content="{ids["pinterest_site_verification"]}">')
    if ids.get("cloudflare_beacon_token"):
        tags.append("<script type=\"module\" src=\"https://static.cloudflareinsights.com/beacon.min.js\" "
                    f"data-cf-beacon='{{\"token\": \"{ids['cloudflare_beacon_token']}\"}}'></script>")
    if ids.get("ga4_measurement_id"):
        gid = ids["ga4_measurement_id"]
        tags.append(f'<script async src="https://www.googletagmanager.com/gtag/js?id={gid}"></script>\n'
                    "<script>window.dataLayer=window.dataLayer||[];"
                    "function gtag(){dataLayer.push(arguments);}"
                    f"gtag('js',new Date());gtag('config','{gid}');</script>")
    return "".join("\n" + t for t in tags)


TRACKING = load_tracking()


def page(site, title, body, is_home=False, description=None, canonical=None,
         image=None, structured_data="", updated=None, noindex=False):
    tag_state = ("" if site["affiliate_tag"] else
                 '<div class="notice">Preview build &mdash; affiliate links are '
                 'untagged until the Amazon Associates account is approved.</div>')
    home_link = "" if is_home else '<a href="./">&larr; All categories</a>'
    desc = meta_desc(description or site["description"])
    base = f"https://{site['custom_domain']}" if site.get("custom_domain") else ""
    canonical_url = canonical if canonical else (f"{base}/" if base else "")
    og_image = image or (f"{base}/assets/logo.png" if base else "assets/logo.png")
    canonical_tag = f'\n<link rel="canonical" href="{esc(canonical_url)}">' if canonical_url else ""
    og_url = f'\n<meta property="og:url" content="{esc(canonical_url)}">' if canonical_url else ""
    social = (
        f'\n<meta property="og:type" content="{"website" if is_home else "article"}">'
        f'\n<meta property="og:site_name" content="{esc(site["brand"])}">'
        f'\n<meta property="og:title" content="{esc(title)}">'
        f'\n<meta property="og:description" content="{esc(desc)}">'
        f'{og_url}'
        f'\n<meta property="og:image" content="{esc(og_image)}">'
        f'\n<meta name="twitter:card" content="summary_large_image">'
        f'\n<meta name="twitter:title" content="{esc(title)}">'
        f'\n<meta name="twitter:description" content="{esc(desc)}">'
        f'\n<meta name="twitter:image" content="{esc(og_image)}">')
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="robots" content="{"noindex, follow" if noindex else "index, follow, max-image-preview:large, max-snippet:-1"}">{canonical_tag}
<meta name="theme-color" content="#000000">
<link rel="icon" href="assets/logo.png">{social}{tracking_head(TRACKING, is_home)}
{site.get('head_extra', '')}
{structured_data}
<link rel="stylesheet" href="assets/styles.css">
</head>
<body>
<header class="site">
  <a class="logo" href="./"><img src="assets/logo.webp" width="336" height="112" alt="{esc(site['brand'])}"></a>
  <span class="slogan">{esc(site['tagline'])}</span>
</header>
{tag_state}
<main>
{body}
</main>
<footer>
  <p class="disclosure"><b>Affiliate disclosure.</b> {esc(site['brand'])} is reader-supported.
  When you buy through links on this site we may earn an Amazon Associates commission, at no
  extra cost to you. Prices and ratings are pulled from Amazon and change over time; the figures
  here were captured on the date shown and are not guaranteed to be current.</p>
  <p class="muted">{home_link} &nbsp; Last updated on {esc(updated or site['updated'])}. Not affiliated with Amazon or any manufacturer.</p>
</footer>
{REVEAL_JS + chr(10) if 'data-show-from' in body else ''}</body>
</html>"""


def oxford(items):
    """Join names with commas and a final 'and' — DEWALT, Milwaukee, and RYOBI."""
    items = [esc(i) for i in items]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def cat_date(cat, site):
    """The date this category's prices/ratings were captured (or last audited)."""
    return cat.get("data_captured") or site["updated"]


def render_deals(brands, site, captured):
    """Short deals note for a category page, naming the brands on that page."""
    if not brands:
        return ""
    names = oxford(brands)
    top = oxford(brands[:2]) if len(brands) >= 2 else names
    return f"""
  <section class="deals">
    <h2>Where the deals are</h2>
    <p>The tools ranked here come from {names}. Prices on these brands move week to
    week on Amazon, and the deepest cuts usually land around Prime Day and Black Friday.
    Every price button on this page opens the live listing, so you always see today's
    number, not the one we captured on {esc(captured)}. If your pick is over budget
    right now, check back in a few days &mdash; {top} rotate through sales and bundle
    deals often.</p>
  </section>"""


def render_home_deals(major_brands, site, oldest, newest):
    """Short deals note for the home page, naming the brands seen across the site."""
    if not major_brands:
        return ""
    names = oxford(major_brands)
    return f"""
  <section class="deals">
    <h2>Deals on the major brands</h2>
    <p>The same names turn up across these lists: {names}. Those brands run their
    steepest Amazon markdowns around Prime Day and Black Friday, and cordless kits get
    bundled and discounted all year. The prices we show were captured
    {f"on {esc(newest)}" if oldest == newest else f"between {esc(oldest)} and {esc(newest)} (each list shows its own date)"} and drift over time, so every price button goes straight to the
    live Amazon listing &mdash; click through to see what a tool actually costs today
    before you buy.</p>
  </section>"""


def render_jump(has_avoid):
    """On-this-page links for category pages. Hidden on desktop, sticky on phones."""
    avoid = '<a href="#avoid" class="avoid-link">Avoid</a>' if has_avoid else ""
    return ('<nav class="jump" aria-label="On this page">'
            '<a href="#picks">Top picks</a><a href="#compare">Compare</a>'
            f'<a href="#ranked">Full ranking</a><a href="#howwerank">How we rank</a>{avoid}</nav>')


# Back-to-top button for the long category pages; shows after scrolling (phones only, via CSS).
TO_TOP = """<a href="#" class="to-top" aria-label="Back to top">&uarr;</a>
  <script>(function(){var b=document.querySelector('.to-top');
  addEventListener('scroll',function(){b.classList.toggle('show',scrollY>900)},{passive:true});
  b.addEventListener('click',function(e){e.preventDefault();scrollTo({top:0,behavior:'smooth'})});})();</script>"""


def build_category(site, filename):
    cat = load(filename)
    ranked, overall, budget, premium = rank_products(cat)
    avoid = cat.get("avoid", [])
    spec_fields = cat.get("spec_fields") or DEFAULT_SPEC_FIELDS
    columns = cat.get("table_columns") or DEFAULT_TABLE_COLUMNS
    heroes = "".join(render_hero_card(p, site, cat) for p in (overall, budget, premium) if p)
    cards = "".join(render_card(p, site, spec_fields, cat) for p in ranked)
    brands = list(dict.fromkeys(p["brand"] for p in ranked))
    cat["_brands"] = brands  # picked up by build_home for the site-wide deals note
    quicknav = render_quicknav(nav_groups_from_site(site), compact=True, back_home=True)
    compare_link = ""
    if cat["slug"] in COMPARE and budget:
        build_comparison(site, cat, overall, budget, premium, spec_fields, columns)
        compare_link = (f'\n  <p class="vs-link">Torn between the top two? '
                        f'<a href="{compare_filename(cat["slug"])}"><b>{esc(_short(overall))} vs '
                        f'{esc(_short(budget))}</b>, compared side by side &rarr;</a></p>')
    twin = twin_of(site, cat["slug"])
    twin_link = ""
    if twin:
        kind = "cordless" if twin["slug"].startswith("cordless-") else "corded"
        twin_link = (f'\n    <p class="vs-link">Looking for {kind} instead? '
                     f'<a href="{twin["slug"]}.html">See the 10 best {esc(twin["title"].lower())} &rarr;</a></p>')
    body = f"""
  {quicknav}
  <section class="lead">
    <h1>{esc(cat['title'])}</h1>
    <p class="sub">{esc(cat['subtitle'])}</p>
    <p class="intro">{esc(cat['intro'])}</p>{twin_link}
  </section>
  {render_jump(bool(avoid))}
  <section class="heroes" id="picks">{heroes}</section>{compare_link}
  {render_deals(brands, site, cat_date(cat, site))}
  <section class="compare" id="compare">
    <h2>Side-by-side comparison</h2>
    <p class="swipe-hint">Swipe the table sideways for more columns &rarr;</p>
    {render_table_filters(ranked)}
    {render_table(ranked, avoid, site, columns)}
    <p class="tiny muted sort-hint">Tap a column heading to sort.</p>
  </section>
  <section class="ranked" id="ranked">
    <h2>The full ranking</h2>
    {cards}
  </section>
  <section class="howwerank" id="howwerank">
    <h2>How we rank</h2>
    <p>Every tool gets one score from 0 to 100, weighted
    {int(cat['weights']['rating']*100)}% on its star rating,
    {int(cat['weights']['reviews']*100)}% on how many people have reviewed it (more reviews = more
    confidence the rating is real), and {int(cat['weights']['features']*100)}% on the features that
    matter for the job. The list is ordered by that score. <b>Best Overall</b> is our pick for the
    best all-around, ready-to-use tool; <b>Best Budget</b> the best value at or under
    ${cat['budget_cap']}; and <b>Money No Object</b> the one to buy if price is no object.</p>
    {render_feature_weights(cat)}
  </section>{render_changes(cat)}
  <section class="guide">
    <h2>Buyer's guide</h2>
    {render_guide(cat['buyers_guide'])}
  </section>
  {render_avoid(avoid, site)}
  {render_related(site, cat)}
  {TABLE_JS}
  {TO_TOP}"""
    base = f"https://{site['custom_domain']}" if site.get("custom_domain") else ""
    canonical = f"{base}/{cat['slug']}.html" if base else ""
    year = str(cat_date(cat, site))[:4]
    title = f"{cat['title']}{f' ({year})' if year else ''} — {site['brand']}"
    description = (f"{cat['title']} ranked from real Amazon ratings, review counts and prices. "
                  f"Best Overall: {overall['brand']} {overall['model']}; Best Budget: "
                  f"{budget['brand']} {budget['model']}. Specs, pros, cons, and a pick to avoid.")
    # Structured data: breadcrumb trail, the ranked list, and the buyer's-guide FAQ.
    breadcrumb = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": site["brand"], "item": f"{base}/"},
        {"@type": "ListItem", "position": 2, "name": cat["title"], "item": canonical}]} if base else None
    itemlist = {"@context": "https://schema.org", "@type": "ItemList", "name": cat["title"],
                "numberOfItems": len(ranked), "itemListOrder": "https://schema.org/ItemListOrderDescending",
                "itemListElement": [
                    {"@type": "ListItem", "position": p["rank"], "name": f"{p['brand']} {p['model']}",
                     "url": f"{canonical}#{p['asin']}" if canonical else None} for p in ranked]}
    faq = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q["q"],
         "acceptedAnswer": {"@type": "Answer", "text": q["a"]}} for q in cat.get("buyers_guide", [])]}
    sd = jsonld(breadcrumb, itemlist) + jsonld(faq)
    (OUT / f"{cat['slug']}.html").write_text(
        page(site, title, body, description=description, canonical=canonical,
             image=overall["image"] if overall else None,
             structured_data=sd, updated=cat_date(cat, site)), encoding="utf-8")
    return cat, overall, budget


# ------------------------------------------------------------------ comparison pages
# "Best Overall vs Best Budget" per category, generated from the same ranked data so
# they update whenever the category does. Only slugs listed in data/compare.json get
# a page, so new comparisons can be released in batches and watched in Search Console.
def compare_config():
    path = DATA / "compare.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


COMPARE = set(compare_config().get("overall_vs_budget", []))
# noindex: built and linked from category pages, but kept out of Google and the sitemap.
COMPARE_NOINDEX = bool(compare_config().get("noindex"))


def compare_filename(slug):
    return f"{slug}-overall-vs-budget.html"


# How each scored feature reads mid-sentence ("For the extra money you get: ...").
FEATURE_PROSE = {
    "digital_display": "a digital temperature display", "safety_clutch": "a safety clutch",
    "two_speed_fan": "a two-speed fan", "variable_temp": "variable temperature control",
    "vibration_control": "vibration control",
    "accessories": "extra accessories", "anti_vibe": "an anti-vibration grip", "auto_lock": "an auto-locking blade",
    "ball_bearing": "ball-bearing drawer slides", "ball_end": "ball-end tips", "both_units": "both SAE and metric sizes",
    "brake": "an electric blade brake", "brushless": "a brushless motor", "case": "a carrying case",
    "comfort_grip": "comfort grips", "cutter": "a built-in wire cutter", "cutters": "cutting pliers in the set",
    "double_sided": "double-sided markings", "dual_battery": "two batteries in the box",
    "dual_material": "dual-material handles", "dual_scale": "dual inch/metric scales", "dust_blower": "a dust blower",
    "dust_box": "a dust box", "forward_reverse": "forward/reverse", "fractions": "fraction markings",
    "groove_joint": "groove-joint pliers", "hammer": "a hammer-drill mode", "hard_base": "a hard, waterproof base",
    "heavy_duty": "heavy-duty construction", "high_bevel": "a high bevel capacity", "hog_ring": "a hog-ring anvil (fast socket swaps)",
    "impact_rated": "impact-rated sockets", "keyless": "a keyless chuck", "kickback_brake": "a kickback brake",
    "kit": "a complete kit (everything you need in the box)", "laser": "a laser guide", "laser_light": "a laser guide",
    "led": "an LED work light", "led_light": "an LED work light", "lifetime_warranty": "a lifetime warranty",
    "lighted": "a built-in light", "lock": "locking drawers", "long_reach": "extra reach",
    "magnetic": "magnetic tips", "magnetic_hook": "a magnetic hook", "magnetic_start": "a magnetic start",
    "metal_gear_case": "a metal gear case", "metal_latches": "metal latches", "multi_drive": "multiple drive sizes",
    "multi_mode": "multiple modes", "nut_driver": "nut drivers", "one_piece": "one-piece forged construction",
    "orbital": "orbital action", "paddle_switch": "a paddle switch", "pouch": "a storage pouch",
    "power_strip": "a built-in power strip", "ratcheting": "a ratcheting handle", "removable_tray": "a removable tray",
    "riser": "a riser/top chest", "sae_metric": "both SAE and metric sizes", "set": "a multi-piece set",
    "shoulder_strap": "a shoulder strap", "side_puller": "side-puller jaws", "soft_grip": "soft grips",
    "stackable": "a stackable design", "tool_free": "tool-free adjustments", "tool_free_blade": "tool-free blade changes",
    "tool_free_guard": "a tool-free guard", "torx": "Torx bits", "two_speed": "a 2-speed gearbox",
    "vac_port": "a vacuum port", "variable_speed": "variable speed", "vsr": "a variable-speed reversing trigger",
    "water_resistant": "water resistance", "wide_jaw": "a wide jaw opening", "wood_top": "a wood worktop",
    "zippered": "a zippered closure",
    # table saws / miter saws (queued in data/category-queue.json)
    "stand": "a stand", "rack_pinion_fence": "a rack-and-pinion fence", "dado": "dado-blade capability",
    "soft_start": "a soft start", "sliding": "a sliding rail for wider cuts", "dual_bevel": "dual bevel",
    "cut_guide": "a laser or LED cut guide",
    # shop vacuums
    "blower": "a blower port", "wide_hose": "a wide (1-7/8 in. or larger) hose",
    "drain_port": "a drain port", "stainless_tank": "a stainless steel tank",
}


def _feature_labels(cat, columns):
    labels = {c["key"]: c["label"] for c in columns if c.get("type") == "bool"}
    return {k: labels.get(k, k.replace("_", " ").capitalize()) for k in cat["feature_weights"]}


def _short(p):
    return f"{p['brand']} {p['model']}"


def build_comparison(site, cat, overall, budget, premium, spec_fields, columns):
    a, b = overall, budget
    A, B = _short(a), _short(b)
    flabels = _feature_labels(cat, columns)
    prose = {k: FEATURE_PROSE.get(k, k.replace("_", " ")) for k in flabels}
    only_a = [prose[k] for k in flabels if a["features"].get(k) and not b["features"].get(k)]
    only_b = [prose[k] for k in flabels if b["features"].get(k) and not a["features"].get(k)]
    diff = a["price"] - b["price"]
    pct = round(abs(diff) / b["price"] * 100) if b["price"] else 0
    base = f"https://{site['custom_domain']}" if site.get("custom_domain") else ""
    cat_page = f"{cat['slug']}.html"
    short_title = cat["title"].replace("The 10 Best ", "")

    # --- the computed verdict: every sentence comes from the data, nothing generic
    if diff > 0:
        price_line = (f"The {esc(A)} costs <b>{money(diff)} more</b> ({pct}% more) than the "
                      f"{esc(B)} &mdash; {money(a['price'])} vs {money(b['price'])}.")
    elif diff < 0:
        price_line = (f"Unusually, our Best Overall is the <b>cheaper</b> one right now: the {esc(A)} is "
                      f"{money(-diff)} less than the {esc(B)} ({money(a['price'])} vs {money(b['price'])}).")
    else:
        price_line = f"Both cost {money(a['price'])} right now."
    if only_a:
        feat_line = f"For the extra money you get: <b>{esc(oxford(only_a))}</b>."
    else:
        feat_line = "On the features we score, the Best Overall adds nothing the budget pick lacks."
    if only_b:
        feat_line += f" Meanwhile the {esc(B)} has {esc(oxford(only_b))}, which the {esc(A)} doesn't."
    trust = ("more" if a["reviews_count"] > b["reviews_count"] else "fewer")
    trust_line = (f"Buyers rate them {a['rating']} vs {b['rating']} stars, and the {esc(A)} has "
                  f"{trust} reviews behind its rating ({a['reviews_count']:,} vs {b['reviews_count']:,}). "
                  f"On our 100-point scale that works out to <b>{a['score']} vs {b['score']}</b>.")
    gap = a["score"] - b["score"]
    if diff > 0 and gap < 0:
        bottom = (f"<b>Bottom line:</b> by our numbers the {esc(B)} wins outright &mdash; it scores higher "
                  f"({b['score']} vs {a['score']}) and costs {money(diff)} less. Only pay more for the "
                  f"{esc(A)} if the strengths listed below matter to you.")
    elif diff > 0 and gap <= 3:
        closeness = "the scores are tied" if gap == 0 else f"only {gap} point{'s' if gap > 1 else ''} separate them"
        need = esc(oxford(only_a)) if only_a else f"what the table below shows the {esc(A)} does better"
        bottom = (f"<b>Bottom line:</b> {closeness}, so the {esc(B)} is the smarter buy unless "
                  f"you specifically need {need}.")
    elif diff > 0:
        bottom = (f"<b>Bottom line:</b> if you'll use it often, the {esc(A)} is worth the {money(diff)}. "
                  f"For occasional jobs around the house, the {esc(B)} does the work for less.")
    else:
        bottom = f"<b>Bottom line:</b> the {esc(A)} is the better tool and costs no more &mdash; buy it."

    # --- side-by-side table: key numbers, every spec field, every scored feature
    def row(label, va, vb):
        return f"<tr><th>{esc(label)}</th><td>{va}</td><td>{vb}</td></tr>"

    def spec(p, key):
        v = p["specs"].get(key)
        if v is None or v == "":
            return "&mdash;"
        return f"{v:,} rpm" if key == "max_rpm" and isinstance(v, (int, float)) else esc(v)

    rows = [row("Price", money(a["price"]), money(b["price"])),
            row("Rating", f"{stars(a['rating'])} {a['rating']}", f"{stars(b['rating'])} {b['rating']}"),
            row("Reviews", f"{a['reviews_count']:,}", f"{b['reviews_count']:,}"),
            row("Our score", f"<b>{a['score']}</b>/100 (#{a['rank']})", f"<b>{b['score']}</b>/100 (#{b['rank']})")]
    if a.get("bought") or b.get("bought"):
        rows.append(row("Bought on Amazon", esc(a.get("bought") or "&mdash;"), esc(b.get("bought") or "&mdash;")))
    rows += [row(f["label"], spec(a, f["key"]), spec(b, f["key"])) for f in spec_fields]
    rows += [row(lbl, "Yes" if a["features"].get(k) else "No", "Yes" if b["features"].get(k) else "No")
             for k, lbl in flabels.items()]
    table = (f'<div class="tablewrap"><table class="vs-table"><tr><th></th>'
             f'<th>{esc(A)}<br><span class="badge overall">Best Overall</span></th>'
             f'<th>{esc(B)}<br><span class="badge budget">Best Budget</span></th></tr>'
             f'{"".join(rows)}</table></div>')

    def side(p, kind, label):
        url = amazon_url(p["asin"], site["affiliate_tag"], site["amazon_domain"])
        pros = "".join(f"<li>{esc(x)}</li>" for x in p["pros"])
        cons = "".join(f"<li>{esc(x)}</li>" for x in p["cons"])
        return f"""
    <article class="card vs-side {kind}">
      <span class="badge {kind}">{label}</span>
      <div class="card-head">
        <div class="card-img"><img src="{esc(p['image'])}" alt="{esc(p['name'])}" loading="lazy"></div>
        <div class="card-title"><div class="brand">{esc(p['brand'])}</div><h3>{esc(p['name'])}</h3></div>
      </div>
      <p class="verdict">{esc(p['verdict'])}</p>
      <div class="pc">
        <div class="pros"><h4>Choose it for</h4><ul>{pros}</ul></div>
        <div class="cons"><h4>Watch out for</h4><ul>{cons}</ul></div>
      </div>
      <a class="btn" href="{url}" target="_blank" rel="sponsored nofollow noopener">Check today's price &rarr;</a>
    </article>"""

    premium_note = ""
    if premium and premium is not a and premium is not b:
        premium_note = (f'<p class="muted">Price no object? Our pick is the '
                        f'<a href="{cat_page}#{esc(premium["asin"])}"><b>{esc(_short(premium))}</b></a> '
                        f'({money(premium["price"])}) &mdash; see why on the full ranking.</p>')

    qa = [
        (f"Is the {A} worth the extra money over the {B}?",
         re.sub(r"<[^>]+>", "", f"{price_line} {feat_line} {bottom}").replace("&mdash;", "—")),
        (f"Which has better reviews, the {A} or the {B}?",
         f"The {A} is rated {a['rating']} stars from {a['reviews_count']:,} reviews; the {B} is rated "
         f"{b['rating']} stars from {b['reviews_count']:,} reviews."),
        (f"What is the best {short_title.lower()} pick overall?",
         f"Our Best Overall is the {A} (score {a['score']}/100), ranked against 9 other "
         f"{short_title.lower()} on rating, review volume and features."),
    ]
    faq_html = "\n".join(f"<details><summary>{esc(q)}</summary><p>{esc(ans)}</p></details>" for q, ans in qa)

    others = [c for c in site["categories"] if c["slug"] in COMPARE and c["slug"] != cat["slug"]]
    group = [c for c in others if c.get("power") == next(
        (x.get("power") for x in site["categories"] if x["slug"] == cat["slug"]), None)] or others
    related = "".join(f'<li><a href="{compare_filename(c["slug"])}">{esc(c["title"])}: Best Overall vs Best Budget</a></li>'
                      for c in group[:6])
    related_html = f'<section class="guide"><h2>More head-to-heads</h2><ul class="vs-related">{related}</ul></section>' if related else ""

    captured = cat_date(cat, site)
    body = f"""
  {render_quicknav(nav_groups_from_site(site), compact=True, back_home=True)}
  <section class="lead">
    <p class="muted"><a href="{cat_page}">&larr; {esc(cat['title'])}</a></p>
    <h1>{esc(A)} vs {esc(B)}</h1>
    <p class="sub">Our Best Overall vs our Best Budget {esc(short_title.lower())} &mdash; is the upgrade worth it?</p>
  </section>
  <section class="deals vs-verdict">
    <h2>The short answer</h2>
    <p>{price_line} {feat_line}</p>
    <p>{trust_line}</p>
    <p>{bottom}</p>
    {premium_note}
  </section>
  <section class="compare"><h2>Side by side</h2>{table}
    <p class="tiny muted">Prices, ratings and review counts captured from Amazon on {esc(captured)}; prices change often.</p></section>
  <section class="vs-grid">{side(a, "overall", "Best Overall")}{side(b, "budget", "Best Budget")}</section>
  <section class="guide"><h2>Quick answers</h2>{faq_html}</section>
  <section class="howwerank"><h2>See the full top 10</h2>
    <p>These two are picked from a ranking of 10 {esc(short_title.lower())}, scored on star rating,
    review volume and the features that matter for the job. <a href="{cat_page}"><b>See all 10 and the one to avoid &rarr;</b></a></p></section>
  {related_html}"""
    canonical = f"{base}/{compare_filename(cat['slug'])}" if base else ""
    title = f"{A} vs {B}: Best Overall vs Best Budget {short_title} ({captured[:4]})"
    description = (f"{A} vs {B} compared: price, rating, specs and features side by side. "
                   f"Is the {money(diff) + ' ' if diff > 0 else ''}upgrade worth it? Our verdict from real Amazon data.")
    breadcrumb = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": site["brand"], "item": f"{base}/"},
        {"@type": "ListItem", "position": 2, "name": cat["title"], "item": f"{base}/{cat_page}"},
        {"@type": "ListItem", "position": 3, "name": f"{A} vs {B}", "item": canonical}]} if base else None
    faq = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": ans}} for q, ans in qa]}
    (OUT / compare_filename(cat["slug"])).write_text(
        page(site, title, body, description=description, canonical=canonical, image=a["image"],
             structured_data=jsonld(breadcrumb) + jsonld(faq), updated=captured,
             noindex=COMPARE_NOINDEX), encoding="utf-8")


# --------------------------------------------------------------- seasonal hub pages
# Gift guides and the Black Friday page, generated from the already-ranked category
# data so every pick stays in step with its category. Copy lives in data/seasonal.json.
def load_seasonal():
    path = DATA / "seasonal.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


SEASONAL = load_seasonal()


def seasonal_pages():
    """[(slug, label, link_from)] of enabled seasonal pages, for cross-links, the home strip
    and sitemap. link_from: on-site links stay hidden until this date (see reveal_attr)."""
    out = [(g["slug"], g.get("label") or g["title"].split(" (")[0], g.get("link_from"))
           for g in SEASONAL.get("gifts", []) if g.get("enabled")]
    bf = SEASONAL.get("black_friday")
    if bf and bf.get("enabled"):
        out.append((bf["slug"], f"Black Friday Tool Deals {bf['year']}", bf.get("link_from")))
    return out


def reveal_attr(link_from):
    """Hide a link until link_from (YYYY-MM-DD). The page itself stays live and in the
    sitemap, so search engines index it; REVEAL_JS un-hides the link on the day, and any
    build after that date renders it plainly."""
    if not link_from or datetime.date.today() >= datetime.date.fromisoformat(link_from):
        return ""
    return f' hidden data-show-from="{esc(link_from)}"'


REVEAL_JS = ("<script>document.querySelectorAll('[data-show-from]').forEach(function(e){"
             "var p=e.getAttribute('data-show-from').split('-');"
             "if(new Date()>=new Date(+p[0],p[1]-1,+p[2]))e.hidden=false;});</script>")


def gift_pick(cat, lo, hi):
    """Best-scoring product in [lo, hi]. Where a category sells kits, only kits
    qualify — nobody wants to unwrap a cordless tool with no battery. Unbranded
    ("Generic") listings are skipped: fine to buy for yourself, a poor gift."""
    pool = cat["products"]
    if any("kit" in p["features"] for p in pool):
        pool = [p for p in pool if p["features"].get("kit")]
    pool = [p for p in pool if lo <= p["price"] <= hi and p["brand"].lower() != "generic"]
    return max(pool, key=lambda p: (p["score"], p["reviews_count"])) if pool else None


def cat_name(cat):
    """'The 10 Best Cordless Drills' -> 'Cordless Drills'."""
    return re.sub(r"^The \d+ Best ", "", cat["title"])


def render_pick_card(p, cat, site, label=None, price_note="", tags=""):
    url = amazon_url(p["asin"], site["affiliate_tag"], site["amazon_domain"])
    tag = f'<span class="badge {esc(p["badge_kind"] or "")}">{esc(label)}</span>' if label else ""
    return f"""
      <article class="card pick-card" id="{esc(cat['slug'])}">
        <div class="card-head">
          <div class="card-img"><img src="{esc(p['image'])}" alt="{esc(p['name'])}" loading="lazy"></div>
          <div class="card-title">
            {tag}
            <div class="brand">{esc(cat_name(cat))} &middot; {esc(p['brand'])}</div>
            <h3>{esc(p['name'])}</h3>
            <div class="rate">{stars(p['rating'])} <b>{p['rating']}</b>
              <span class="muted">{p['reviews_count']:,} reviews &middot; score {p['score']}/100</span></div>
            {f'<div class="tags">{tags}</div>' if tags else ''}
          </div>
          <div class="card-buy">
            <div class="price">{money(p['price'])}</div>
            <a class="btn" href="{url}" target="_blank" rel="sponsored nofollow noopener">Check today's price</a>
            <div class="tiny muted">{price_note}</div>
          </div>
        </div>
        <p class="verdict">{esc(p['verdict'])}</p>
        <p class="tiny"><a class="pick-more" href="{esc(cat['slug'])}.html#{esc(p['asin'])}">Ranked #{p['rank']} of {len(cat['products'])} {esc(cat_name(cat).lower())} &mdash; see the full list &rarr;</a></p>
      </article>"""


TOOLS_FIRST = {"wireless": 0, "wired": 1, "hand": 2, "storage": 3}


def _grouped(site, by_slug, pick, order=None):
    """Picks per home group, in home-page order (or by `order`). pick(cat) -> html or ''."""
    out = []
    groups = sorted(HOME_GROUPS, key=lambda g: order.get(g[2], 9)) if order else HOME_GROUPS
    for label, _sub, key in groups:
        cards = [pick(by_slug[c["slug"]]) for c in site["categories"]
                 if c.get("power") == key and c["slug"] in by_slug]
        cards = [c for c in cards if c]
        if cards:
            out.append(f'<section class="pick-group"><h2>{esc(label)}</h2>{"".join(cards)}</section>')
    return "".join(out)


def _seasonal_related(current):
    links = "".join(f'<li{reveal_attr(lf)}><a href="{s}.html">{esc(t)}</a></li>'
                    for s, t, lf in seasonal_pages() if s != current)
    return f'<section class="guide"><h2>More holiday guides</h2><ul class="vs-related">{links}</ul></section>' if links else ""


def _write_hub(site, cfg, body, captured_dates, extra_sd=None, image=None):
    base = f"https://{site['custom_domain']}" if site.get("custom_domain") else ""
    canonical = f"{base}/{cfg['slug']}.html" if base else ""
    faq = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q["q"], "acceptedAnswer": {"@type": "Answer", "text": q["a"]}}
        for q in cfg.get("faq", [])]}
    breadcrumb = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": site["brand"], "item": f"{base}/"},
        {"@type": "ListItem", "position": 2, "name": cfg["title"], "item": canonical}]} if base else None
    updated = max(captured_dates) if captured_dates else site["updated"]
    (OUT / f"{cfg['slug']}.html").write_text(
        page(site, f"{cfg['title']} — {site['brand']}", body, description=cfg["subtitle"],
             canonical=canonical, image=image, structured_data=jsonld(breadcrumb, extra_sd) + jsonld(faq),
             updated=updated, noindex=bool(cfg.get("noindex"))), encoding="utf-8")
    return updated


def _itemlist(name, items, base):
    return {"@context": "https://schema.org", "@type": "ItemList", "name": name,
            "numberOfItems": len(items), "itemListElement": [
                {"@type": "ListItem", "position": i, "name": f"{p['brand']} {p['model']}",
                 "url": f"{base}/{cat['slug']}.html#{p['asin']}"} for i, (cat, p) in enumerate(items, 1)]}


def premium_tags(p, cat, cordless):
    """Battery platform + bare-tool warning for a cordless premium pick (pro cordless
    tools are often sold tool-only, which is only a good gift for a brand owner)."""
    if not cordless:
        return ""
    tags = []
    brand = next((b for b in BRANDS if b["brand"].lower() == p["brand"].lower()), None)
    plat = brand_platform(p, brand) if brand else None
    if plat:
        tags.append(f'<span class="tag">{esc(p["brand"])} {esc(plat)}</span>')
    if any("kit" in x["features"] for x in cat["products"]):
        tags.append('<span class="tag">Kit: battery + charger</span>' if p["features"].get("kit")
                    else '<span class="tag">Bare tool: battery sold separately</span>')
    return "".join(tags)


def build_gift_page(site, cfg, by_slug):
    premium = cfg.get("kind") == "premium"
    lo, hi = cfg.get("min_price", 0), cfg.get("max_price", 0)
    power = {c["slug"]: c.get("power") for c in site["categories"]}
    chosen = []

    def pick(cat):
        if premium:
            p = next((x for x in sorted(cat["products"], key=lambda x: x["rank"]) if x.get("premium")), None)
        else:
            p = gift_pick(cat, lo, hi)
        if not p:
            return ""
        chosen.append((cat, p))
        note = f"price on {esc(cat_date(cat, site))}"
        if premium:
            return render_pick_card(p, cat, site, "Money No Object", note,
                                    premium_tags(p, cat, power.get(cat["slug"]) == "wireless"))
        return render_pick_card(p, cat, site, price_note=note)

    groups = _grouped(site, by_slug, pick, TOOLS_FIRST if premium else None)
    base = f"https://{site['custom_domain']}" if site.get("custom_domain") else ""
    dates = [cat_date(cat, site) for cat, _ in chosen]
    body = f"""
  {render_quicknav(nav_groups_from_site(site), compact=True, back_home=True)}
  <section class="lead">
    <h1>{esc(cfg['title'])}</h1>
    <p class="sub">{esc(cfg['subtitle'])}</p>
    <p class="intro">{esc(cfg['intro'])}</p>
    <p class="muted">{len(chosen)} gifts, one per category{f", from {money(min(p['price'] for _, p in chosen))} to {money(max(p['price'] for _, p in chosen))}" if premium and chosen else ""}. Prices were captured from Amazon
    {f"on {esc(min(dates))}" if dates and min(dates) == max(dates) else f"between {esc(min(dates))} and {esc(max(dates))}" if dates else ""}
    and change often, so check the live price before you buy.</p>
  </section>
  {groups}
  <section class="guide"><h2>Gift-buying questions</h2>{render_guide(cfg.get('faq', []))}</section>
  {_seasonal_related(cfg['slug'])}"""
    return _write_hub(site, cfg, body, dates, _itemlist(cfg["title"], chosen, base) if base else None,
                      chosen[0][1]["image"] if chosen else None)


def _long_date(iso):
    d = datetime.date.fromisoformat(iso)
    return f"{d:%A, %B} {d.day}, {d.year}"


def build_black_friday(site, cfg, by_slug):
    rows, dates = [], []

    def pick(entry):
        cat, overall, budget = entry
        dates.append(cat_date(cat, site))
        rows.append((cat, overall, budget))
        note = f"regular price on {esc(cat_date(cat, site))}"
        cards = render_pick_card(overall, cat, site, "Best Overall", note)
        if budget and budget is not overall:
            cards += render_pick_card(budget, cat, site, "Best Budget", note)
        return cards

    groups = _grouped(site, by_slug, pick)
    table_rows = "".join(
        f'<tr><td><a href="#{esc(cat["slug"])}">{esc(cat_name(cat))}</a></td>'
        f'<td>{esc(_short(o))}</td><td>{money(o["price"])}</td>'
        f'<td>{esc(_short(b)) if b else "&mdash;"}</td><td>{money(b["price"]) if b else "&mdash;"}</td></tr>'
        for cat, o, b in rows)
    bf = cfg["black_friday"]
    cm = cfg["cyber_monday"]
    body = f"""
  {render_quicknav(nav_groups_from_site(site), compact=True, back_home=True)}
  <section class="lead">
    <h1>{esc(cfg['title'])}</h1>
    <p class="sub">{esc(cfg['subtitle'])}</p>
    <p class="intro">{esc(cfg['intro'])}</p>
  </section>
  <section class="deals">
    <h2>Key dates</h2>
    <p><b>Black Friday:</b> {_long_date(bf)}. <b>Cyber Monday:</b> {_long_date(cm)}. Early deals usually
    start the week before. Every button below opens the live Amazon listing, so you see
    today's price next to the regular price we recorded.</p>
  </section>
  <section class="compare" id="price-to-beat">
    <h2>Price-to-beat cheat sheet</h2>
    <p class="swipe-hint">Swipe the table sideways for more columns &rarr;</p>
    <div class="tablewrap"><table class="bf-table"><tr><th>Category</th><th>Best Overall</th><th>Regular</th>
      <th>Best Budget</th><th>Regular</th></tr>{table_rows}</table></div>
    <p class="tiny muted">"Regular" = the Amazon price when we last checked each category
    ({esc(min(dates))} to {esc(max(dates))}). If the Black Friday price is at or above it, it isn't a deal.</p>
  </section>
  {groups}
  <section class="guide"><h2>Black Friday tool questions</h2>{render_guide(cfg.get('faq', []))}</section>
  {_seasonal_related(cfg['slug'])}"""
    return _write_hub(site, cfg, body, dates)


def build_seasonal(site, cats):
    """Build every enabled seasonal page; returns [(slug, lastmod)] for the sitemap
    (pages flagged noindex are built but left out)."""
    by_slug = {cat["slug"]: (cat, overall, budget) for cat, overall, budget in cats}
    built = []
    for g in SEASONAL.get("gifts", []):
        if g.get("enabled"):
            lastmod = build_gift_page(site, g, {s: v[0] for s, v in by_slug.items()})
            if not g.get("noindex"):
                built.append((g["slug"], lastmod))
    bf = SEASONAL.get("black_friday")
    if bf and bf.get("enabled"):
        lastmod = build_black_friday(site, bf, by_slug)
        if not bf.get("noindex"):
            built.append((bf["slug"], lastmod))
    return built


def render_seasonal_strip():
    pages = seasonal_pages()
    if not pages:
        return ""
    links = "".join(f'<a class="btn" href="{s}.html"{reveal_attr(lf)}>{esc(t)} &rarr;</a>' for s, t, lf in pages)
    return f"""
  <section class="deals seasonal-strip">
    <h2>Holiday gift guides</h2>
    <p>Our top-ranked tool picks, sorted by budget.</p>
    <div class="strip-links">{links}</div>
  </section>"""


# ------------------------------------------------------------------ brand hub pages
# "Best DEWALT tools" etc.: the brand's top-ranked product in every category where it
# made our top 10, for readers staying on one battery platform. Copy in data/brands.json.
def load_brands():
    path = DATA / "brands.json"
    return json.loads(path.read_text(encoding="utf-8")).get("brands", []) if path.exists() else []


BRANDS = [b for b in load_brands() if b.get("enabled")]
for _b in BRANDS:
    for _k in ("button", "button_text"):
        if _b.get(_k) and not re.fullmatch(r"#[0-9A-Fa-f]{6}", _b[_k]):
            raise SystemExit(f"data/brands.json: {_b['brand']} {_k}={_b[_k]!r} is not a #RRGGBB color")


def brand_style(cfg):
    """Inline CSS variables so this brand's buttons use its own colors."""
    if not cfg.get("button"):
        return ""
    return f' style="--brand-btn:{cfg["button"]};--brand-btn-ink:{cfg.get("button_text", "#000000")}"'


def brand_platform(p, cfg):
    for rule in cfg.get("platforms", []):
        if re.search(rule["match"], p["name"], re.I):
            return rule["label"]
    return None


def render_brand_card(p, cat, site, cfg, others, cordless):
    url = amazon_url(p["asin"], site["affiliate_tag"], site["amazon_domain"])
    name = cat_name(cat)
    ranked = sorted(cat["products"], key=lambda x: x["rank"])
    top = ranked[0]
    tags = []
    plat = brand_platform(p, cfg)
    if plat:
        tags.append(f'<span class="tag">{esc(plat)}</span>')
    # "kit" means battery + charger only for cordless tools (corded kits are case/accessory kits).
    if cordless and any("kit" in x["features"] for x in cat["products"]):
        tags.append('<span class="tag">Kit: battery + charger</span>' if p["features"].get("kit")
                    else '<span class="tag">Bare tool: battery sold separately</span>')
    if p["badge"]:
        tags.append(f'<span class="badge {esc(p["badge_kind"])}">{esc(p["badge"])}</span>')
    if p["badge_kind"] == "overall":
        verdict = f"This is also our <b>Best Overall</b> {esc(name.lower())} pick, from any brand."
    elif p["rank"] == 1:
        verdict = f"The <b>highest score of any brand</b> in our {esc(name.lower())} list."
    else:
        verdict = (f'Top score from any brand: the <a href="{esc(cat["slug"])}.html#{esc(top["asin"])}">'
                   f'{esc(_short(top))}</a> ({top["score"]}/100), {top["score"] - p["score"]} '
                   f'point{"s" if top["score"] - p["score"] != 1 else ""} ahead.')
    also = ""
    if others:
        links = ", ".join(f'<a href="{esc(cat["slug"])}.html#{esc(o["asin"])}">{esc(o["model"])}</a> (#{o["rank"]})'
                          for o in others)
        also = f'<p class="tiny muted brand-also">Also in our top 10: {links}</p>'
    return f"""
      <article class="card pick-card brand-card" id="{esc(cat['slug'])}">
        <div class="card-head">
          <div class="card-img"><img src="{esc(p['image'])}" alt="{esc(p['name'])}" loading="lazy"></div>
          <div class="card-title">
            <div class="brand">{esc(name)} &middot; ranked #{p['rank']} of {len(cat['products'])}</div>
            <h3>{esc(p['name'])}</h3>
            <div class="rate">{stars(p['rating'])} <b>{p['rating']}</b>
              <span class="muted">{p['reviews_count']:,} reviews &middot; score {p['score']}/100</span></div>
            <div class="tags">{"".join(tags)}</div>
          </div>
          <div class="card-buy">
            <div class="price">{money(p['price'])}</div>
            <a class="btn" href="{url}" target="_blank" rel="sponsored nofollow noopener">Check today's price</a>
            <div class="tiny muted">price on {esc(cat_date(cat, site))}</div>
          </div>
        </div>
        <p class="verdict">{esc(p['verdict'])}</p>
        <p class="brand-vs">{verdict}</p>
        {also}
        <p class="tiny"><a class="pick-more" href="{esc(cat['slug'])}.html">See all 10 {esc(name.lower())} &rarr;</a></p>
      </article>"""


def build_brand_page(site, cfg, by_slug):
    want = cfg["brand"].lower()
    chosen, missing, dates, total, n_top, n_overall = [], [], [], 0, 0, 0
    sections = []
    # Battery platform is why people stay loyal, so cordless leads; storage goes last.
    for label, _sub, key in sorted(HOME_GROUPS, key=lambda g: TOOLS_FIRST.get(g[2], 9)):
        cards = []
        for c in site["categories"]:
            if c.get("power") != key or c["slug"] not in by_slug:
                continue
            cat = by_slug[c["slug"]]
            mine = sorted((p for p in cat["products"] if p["brand"].lower() == want), key=lambda p: p["rank"])
            if not mine:
                missing.append(cat)
                continue
            p = mine[0]
            chosen.append((cat, p))
            dates.append(cat_date(cat, site))
            total += len(mine)
            n_top += p["rank"] == 1
            n_overall += p["badge_kind"] == "overall"
            cards.append(render_brand_card(p, cat, site, cfg, mine[1:], key == "wireless"))
        if cards:
            sections.append(f'<section class="pick-group"><h2>{esc(label)}</h2>{"".join(cards)}</section>')
    brand = esc(cfg["brand"])
    miss = ""
    if missing:
        links = "".join(f'<li><a href="{esc(c["slug"])}.html">{esc(cat_name(c))}</a></li>' for c in missing)
        miss = (f'<section class="guide"><h2>Where {brand} didn\'t make our top 10</h2>'
                f'<p class="muted">No {brand} product made these lists when we last checked. '
                f'Here are the best picks from any brand:</p><ul class="vs-related brand-missing">{links}</ul></section>')
    others = [b for b in BRANDS if b["slug"] != cfg["slug"]]
    related = "".join(f'<li><a href="{b["slug"]}.html">Best {esc(b["brand"])} tools</a></li>' for b in others)
    related += "".join(f'<li{reveal_attr(lf)}><a href="{s}.html">{esc(t)}</a></li>' for s, t, lf in seasonal_pages())
    related_html = f'<section class="guide"><h2>More guides</h2><ul class="vs-related">{related}</ul></section>' if related else ""
    body = f"""
  {render_quicknav(nav_groups_from_site(site), compact=True, back_home=True)}
  <div class="brand-theme"{brand_style(cfg)}>
  <section class="lead">
    <h1>{esc(cfg['title'])}</h1>
    <p class="sub">{esc(cfg['subtitle'])}</p>
    <p class="intro">{esc(cfg['intro'])}</p>
  </section>
  <section class="deals brand-stats">
    <h2>{brand} at a glance</h2>
    <p><b>{total} {brand} tools</b> made our top-10 lists, across <b>{len(chosen)} of {len(by_slug)}</b> categories.
    {brand} scores highest of any brand in <b>{n_top}</b> of them and is our Best Overall pick in <b>{n_overall}</b>.
    Below is the best {brand} in each category, with an honest note wherever another brand ranked higher.</p>
  </section>
  {''.join(sections)}
  {miss}
  <section class="guide"><h2>{brand} questions</h2>{render_guide(cfg.get('faq', []))}</section>
  {related_html}
  </div>"""
    base = f"https://{site['custom_domain']}" if site.get("custom_domain") else ""
    return _write_hub(site, cfg, body, dates, _itemlist(cfg["title"], chosen, base) if base else None,
                      chosen[0][1]["image"] if chosen else None)


def build_brands(site, cats):
    by_slug = {cat["slug"]: cat for cat, _o, _b in cats}
    built = [(b, build_brand_page(site, b, by_slug)) for b in BRANDS]
    return [(b["slug"], lastmod) for b, lastmod in built if not b.get("noindex")]


def render_brand_strip():
    if not BRANDS:
        return ""
    links = "".join(f'<a class="btn ghost-btn brand-btn" href="{b["slug"]}.html"{brand_style(b)}>Best {esc(b["brand"])} tools &rarr;</a>' for b in BRANDS)
    return f"""
  <section class="deals seasonal-strip brand-strip">
    <h2>Shop by brand</h2>
    <p>Staying on one battery platform? The top-ranked tool from each brand, in every category.</p>
    <div class="strip-links">{links}</div>
  </section>"""


# Home-page groups (label, blurb, power-key). Shared by the home sections and the
# quick-navigation dropdown so both stay in sync.
HOME_GROUPS = [
    ("Tool storage", "Boxes, chests, cabinets, and bags &mdash; keep every tool organized, portable, and secure.", "storage"),
    ("Wireless tools", "Battery powered &mdash; cut, drive, and drill anywhere, no cord.", "wireless"),
    ("Wired tools", "Corded &mdash; full unlimited power for the least money, never a dead battery.", "wired"),
    ("Hand tools", "No batteries, no cords &mdash; the essentials every toolbox needs.", "hand"),
]


def nav_groups_from_site(site):
    """[(label, key, members)] straight from site.json — for pages that don't
    build the ranked results (category pages) but still need the nav dropdown."""
    out = []
    for label, _sub, key in HOME_GROUPS:
        members = [c for c in site["categories"] if c.get("power") == key]
        if members:
            out.append((label, key, members))
    return out


def twin_of(site, slug):
    """The corded/cordless counterpart of a category, if the site has one."""
    for a, b in (("corded-", "cordless-"), ("cordless-", "corded-")):
        if slug.startswith(a):
            other = b + slug[len(a):]
            return next((c for c in site["categories"] if c["slug"] == other), None)
    return None


RELATED_COUNT = 5


def render_related(site, cat):
    """Plain <a> links to the twin plus the next few categories in the same home group,
    wrapping around, so every category page gets crawlable links from its neighbours
    (the quick-nav dropdown is JavaScript and search engines don't follow it)."""
    power = next((c.get("power") for c in site["categories"] if c["slug"] == cat["slug"]), None)
    group = [c for c in site["categories"] if c.get("power") == power]
    i = next((n for n, c in enumerate(group) if c["slug"] == cat["slug"]), None)
    twin = twin_of(site, cat["slug"])
    picks = [twin] if twin else []
    if i is not None:
        for c in group[i + 1:] + group[:i]:
            if len(picks) >= RELATED_COUNT + bool(twin):
                break
            if c not in picks:
                picks.append(c)
    if not picks:
        return ""
    items = "".join(f'<li><a href="{c["slug"]}.html">The 10 best {esc(c["title"].lower())}</a></li>' for c in picks)
    return f'<section class="guide" id="related"><h2>Related tools</h2><ul class="vs-related">{items}</ul></section>'


def render_quicknav(nav_groups, compact=False, back_home=False):
    """Linked dropdowns (category -> sub-category) + Go button.

    nav_groups: list of (label, key, members).
    compact:    omit the heading/blurb; render as a slim top-of-page toolbar.
    back_home:  prepend a "Home" button that returns to the homepage (./).
    """
    if not nav_groups:
        return ""
    cat_opts = "".join(
        f'<option value="{esc(key)}">{esc(label)}</option>'
        for label, key, _ in nav_groups)
    data = {key: [{"slug": c["slug"], "title": c["title"]} for c in members]
            for label, key, members in nav_groups}
    js = """
    (function(){
      var cats = __DATA__;
      var catSel = document.getElementById('qn-category');
      var subSel = document.getElementById('qn-subcategory');
      var go = document.getElementById('qn-go');
      if(!catSel || !subSel || !go){ return; }
      function fillSubs(){
        var list = cats[catSel.value] || [];
        subSel.innerHTML = '<option value="">Sub-category\\u2026</option>';
        list.forEach(function(c){
          var o = document.createElement('option');
          o.value = c.slug; o.textContent = c.title;
          subSel.appendChild(o);
        });
        subSel.disabled = list.length === 0;
        updateGo();
      }
      function updateGo(){ go.disabled = !subSel.value; }
      function navigate(){ if(subSel.value){ window.location.href = subSel.value + '.html'; } }
      catSel.addEventListener('change', fillSubs);
      subSel.addEventListener('change', updateGo);
      go.addEventListener('click', navigate);
      subSel.addEventListener('keydown', function(e){ if(e.key === 'Enter'){ navigate(); } });
    })();
    """.replace("__DATA__", json.dumps(data))
    back = ('<a class="back-home" href="./">&larr; Home</a>\n      '
            if back_home else "")
    controls = f"""<div class="quicknav-controls">
      {back}<select id="qn-category" aria-label="Category">
        <option value="">Category&hellip;</option>
        {cat_opts}
      </select>
      <select id="qn-subcategory" aria-label="Sub-category" disabled>
        <option value="">Sub-category&hellip;</option>
      </select>
      <button type="button" id="qn-go" class="btn" disabled>Go</button>
    </div>"""
    if compact:
        return f"""
  <nav class="quicknav quicknav-bar" aria-label="Quick navigation">
    {controls}
    <script>{js}</script>
  </nav>"""
    return f"""
  <section class="quicknav" aria-labelledby="qn-h">
    <h2 id="qn-h">Quick navigation</h2>
    <p class="group-sub">Pick a category, choose a tool, and jump straight to its top&#8209;10 list.</p>
    {controls}
    <script>{js}</script>
  </section>"""


def build_home(site, cats):
    by_slug = {cat["slug"]: (cat, overall, budget) for cat, overall, budget in cats}

    def card(c):
        cat, overall, budget = by_slug[c["slug"]]
        return f"""
      <a class="cat-card" href="{esc(c['slug'])}.html">
        <h3>{esc(c['title'])}</h3>
        <p>{esc(c['blurb'])}</p>
        <div class="cat-picks">
          <span><b>Best Overall:</b> {esc(overall['brand'])} {esc(overall['model'])}</span>
          <span><b>Best Budget:</b> {esc(budget['brand'])} {esc(budget['model'])}</span>
        </div>
        <span class="btn ghost">See the top {c['count']} &rarr;</span>
      </a>"""

    sections = []
    nav_groups = []
    for label, sub, key in HOME_GROUPS:
        members = [c for c in site["categories"] if c.get("power") == key and c["slug"] in by_slug]
        if not members:
            continue
        cards = "".join(card(c) for c in members)
        sections.append(
            f'\n  <details class="cats">'
            f'\n    <summary><h2>{esc(label)}</h2></summary>'
            f'\n    <button type="button" class="cats-collapse" hidden>Collapse</button>'
            f'\n    <p class="group-sub">{sub}</p>'
            f'\n    <div class="cat-grid">{cards}</div>\n  </details>')
        nav_groups.append((label, key, members))
    # "Major" brands = those appearing across more than one category, most-common first.
    counts, order = {}, []
    for c in site["categories"]:
        entry = by_slug.get(c["slug"])
        if not entry:
            continue
        for b in entry[0].get("_brands", []):
            if b not in counts:
                counts[b] = 0
                order.append(b)
            counts[b] += 1
    major = [b for b in order if counts[b] >= 2]
    major.sort(key=lambda b: (-counts[b], order.index(b)))
    if len(major) < 4:  # fallback for a small site: most-common brands overall
        major = sorted(order, key=lambda b: (-counts[b], order.index(b)))
    major = major[:10]
    dates = [cat_date(entry[0], site) for entry in by_slug.values()] or [site["updated"]]
    # Groups open on hover or click/tap and stay open; only the Collapse button
    # closes one. (Without JS the native <details> toggle still works.)
    hover_js = ("(function(){document.querySelectorAll('details.cats')"
                ".forEach(function(d){"
                "var s=d.querySelector('summary'),c=d.querySelector('.cats-collapse');"
                "c.hidden=false;"
                "d.addEventListener('mouseenter',function(){d.open=true;});"
                "s.addEventListener('click',function(e){e.preventDefault();d.open=true;});"
                "c.addEventListener('click',function(){d.open=false;s.focus();});"
                "});})();")
    body = f"""
  <section class="lead home">
    <h1>{esc(site['brand'])}</h1>
    <p class="sub">{esc(site['description'])}</p>
  </section>
  {render_seasonal_strip()}
  {render_brand_strip()}
  {render_quicknav(nav_groups)}
  <h2 class="shop-head">Shop by category</h2>
  {''.join(sections)}
  {render_home_deals(major, site, min(dates), max(dates))}
  <script>{hover_js}</script>"""
    base = f"https://{site['custom_domain']}" if site.get("custom_domain") else ""
    org = {"@context": "https://schema.org", "@type": "Organization", "name": site["brand"],
           "url": f"{base}/" if base else "", "logo": f"{base}/assets/logo.png" if base else ""}
    website = {"@context": "https://schema.org", "@type": "WebSite", "name": site["brand"],
               "url": f"{base}/" if base else "", "description": site["description"]}
    (OUT / "index.html").write_text(
        page(site, f"{site['brand']} — {site['tagline']}", body, is_home=True,
             canonical=f"{base}/" if base else "", structured_data=jsonld(org, website),
             updated=max(dates)),
        encoding="utf-8")


def build_redirects(site):
    """Stub pages for old URLs listed in data/redirects.json (see its _readme)."""
    path = DATA / "redirects.json"
    if not path.exists():
        return
    base = f"https://{site['custom_domain']}" if site.get("custom_domain") else ""
    for old, new in json.loads(path.read_text(encoding="utf-8")).get("redirects", {}).items():
        target = f"{base}/{new}" if base else new
        (OUT / old).write_text(f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Moved: {esc(new)}</title>
<link rel="canonical" href="{esc(target)}">
<meta http-equiv="refresh" content="0; url={esc(target)}">
</head>
<body>
<p>This page has moved to <a href="{esc(target)}">{esc(target)}</a>.</p>
</body>
</html>
""", encoding="utf-8")


def main():
    site = load("site.json")
    OUT.mkdir(exist_ok=True)
    ASSETS.mkdir(exist_ok=True)
    (ASSETS / "styles.css").write_text(CSS, encoding="utf-8")
    # GitHub Pages: custom-domain file + disable Jekyll processing
    if site.get("custom_domain"):
        (OUT / "CNAME").write_text(site["custom_domain"], encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    record_prices(site)
    cats = [build_category(site, f"{c['slug']}.json") for c in site["categories"]]
    build_home(site, cats)
    seasonal = build_seasonal(site, cats) + build_brands(site, cats)
    # sitemap.xml + robots.txt (SEO / Search Console)
    if site.get("custom_domain"):
        base = f"https://{site['custom_domain']}"
        # Per-page lastmod = the date that page's data was captured/audited, so Google
        # can trust it (a site-wide "today" on every URL teaches it to ignore lastmod).
        # Home changes whenever any category does, so it takes the newest date.
        cat_dates = [(cat["slug"], cat.get("data_captured") or site["updated"]) for cat, _, _ in cats]
        urls = ([(f"{base}/", "1.0", max(d for _, d in cat_dates))]
                + [(f"{base}/{slug}.html", "0.8", d) for slug, d in cat_dates]
                + [(f"{base}/{compare_filename(slug)}", "0.6", d) for slug, d in cat_dates
                   if slug in COMPARE and not COMPARE_NOINDEX]
                + [(f"{base}/{slug}.html", "0.7", d) for slug, d in seasonal])
        entries = "\n".join(
            f"  <url><loc>{u}</loc><lastmod>{lastmod}</lastmod>"
            f"<changefreq>weekly</changefreq><priority>{pr}</priority></url>" for u, pr, lastmod in urls)
        (OUT / "sitemap.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{entries}\n</urlset>\n", encoding="utf-8")
        (OUT / "robots.txt").write_text(
            f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n", encoding="utf-8")
    build_redirects(site)
    # IndexNow ownership key (Bing/Yandex/Seznam/Naver); pinged by .github/workflows/indexnow.yml
    if TRACKING.get("indexnow_key"):
        (OUT / f"{TRACKING['indexnow_key']}.txt").write_text(TRACKING["indexnow_key"], encoding="utf-8")
    print(f"Built {len(cats)} category page(s) + home into {OUT}")
    for cat, overall, budget in cats:
        print(f"  {cat['slug']}: Best Overall = {overall['brand']} {overall['model']} "
              f"(score {overall['score']}); Best Budget = {budget['brand']} {budget['model']} "
              f"(score {budget['score']})")


CSS = r"""
:root{
  --bg:#000000; --card:#14181f; --card-2:#1b2029; --ink:#eaeef4; --muted:#9aa6b7; --line:#282f3a;
  --brand:#ff9526; --brand-ink:#ffb35a; --overall:#37c07d; --budget:#5b9bff; --premium:#a78bfa;
  --star:#f5a623; --shadow:0 1px 2px rgba(0,0,0,.5),0 12px 34px rgba(0,0,0,.55);
  --radius:14px; --max:1060px;
}
*{box-sizing:border-box}
[hidden]{display:none!important}
body{margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.6 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
main{max-width:var(--max);margin:0 auto;padding:0 20px 40px}
h1{font-size:2.1rem;line-height:1.15;margin:.2em 0}
h2{font-size:1.5rem;margin:2.2rem 0 1rem}
.muted{color:var(--muted)} .tiny{font-size:.8rem} .c{text-align:center}
/* header */
header.site{max-width:var(--max);margin:0 auto;padding:16px 20px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.logo{display:inline-flex;align-items:center;line-height:0}
.logo img{height:56px;width:auto;max-width:72vw;display:block}
.slogan{color:var(--muted);font-size:.95rem}
.notice{max-width:var(--max);margin:0 auto 8px;padding:8px 20px;color:var(--brand-ink);font-size:.85rem}
/* lead */
.lead{padding:14px 0 8px}
.lead .sub{font-size:1.15rem;color:var(--muted);margin:.3em 0}
.lead .intro{max-width:70ch}
.home h1{font-size:2.6rem}
/* stars */
.stars{--pct:100%;display:inline-block;width:88px;height:16px;vertical-align:-2px;
  background:linear-gradient(90deg,var(--star) var(--pct),#3a4150 var(--pct));
  -webkit-mask:repeat-x left/17.6px 16px;mask:repeat-x left/17.6px 16px;
  -webkit-mask-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='17.6' height='16' viewBox='0 0 20 20'%3E%3Cpath d='M10 1l2.6 5.3 5.9.9-4.3 4.1 1 5.8L10 14.9 4.8 17.6l1-5.8L1.5 7.7l5.9-.9z'/%3E%3C/svg%3E");
  mask-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='17.6' height='16' viewBox='0 0 20 20'%3E%3Cpath d='M10 1l2.6 5.3 5.9.9-4.3 4.1 1 5.8L10 14.9 4.8 17.6l1-5.8L1.5 7.7l5.9-.9z'/%3E%3C/svg%3E")}
/* hero cards */
.heroes{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:18px;margin-top:14px}
.hero-card{display:flex;gap:14px;background:var(--card);border-radius:var(--radius);
  box-shadow:var(--shadow);padding:18px;border-top:4px solid var(--overall);position:relative;transition:transform .1s}
.hero-card.budget{border-top-color:var(--budget)}
.hero-card.premium{border-top-color:var(--premium)}
.hero-card:hover{transform:translateY(-2px)}
.hero-card img{width:104px;height:104px;object-fit:contain;flex:none;background:#fff;border-radius:10px}
.hero-tag{position:absolute;top:-11px;left:16px;background:var(--overall);color:#fff;
  font-size:.72rem;font-weight:700;letter-spacing:.03em;text-transform:uppercase;padding:3px 10px;border-radius:20px}
.hero-card.budget .hero-tag{background:var(--budget)}
.hero-card.premium .hero-tag{background:var(--premium)}
.hero-brand{font-size:.8rem;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.hero-name{font-weight:700;margin:2px 0 6px}
.hero-meta b{margin-left:4px}
.hero-price{font-size:1.5rem;font-weight:800;margin:8px 0}
/* buttons */
.btn{display:inline-block;background:var(--brand);color:#231400;font-weight:700;
  padding:9px 16px;border-radius:9px;font-size:.92rem}
.btn.ghost{background:transparent;color:var(--brand);padding:6px 0;font-weight:700}
/* comparison table */
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:var(--radius);background:var(--card)}
table{border-collapse:collapse;width:100%;min-width:760px;font-size:.9rem}
th,td{padding:10px 12px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}
th{background:rgba(128,128,128,.06);font-size:.8rem;text-transform:uppercase;letter-spacing:.03em;color:var(--muted)}
tbody tr:last-child td{border-bottom:0}
table a{color:var(--budget);font-weight:600}
/* product cards */
.card{background:var(--card);border-radius:var(--radius);box-shadow:var(--shadow);
  padding:22px;margin:18px 0;position:relative;overflow:hidden}
.rank{position:absolute;top:0;left:0;background:var(--ink);color:var(--bg);
  font-weight:800;font-size:.95rem;padding:4px 12px;border-bottom-right-radius:12px}
.card-head{display:grid;grid-template-columns:132px 1fr auto;gap:18px;align-items:start}
.card-img img{width:132px;height:132px;object-fit:contain;background:#fff;border-radius:10px}
.card-title .brand{font-size:.78rem;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;margin-top:6px}
.card-title h3{margin:.1em 0 .4em;font-size:1.15rem}
.rate b{margin:0 4px 0 6px}
.badge{display:inline-block;background:var(--overall);color:#fff;font-size:.7rem;font-weight:700;
  text-transform:uppercase;letter-spacing:.03em;padding:2px 9px;border-radius:20px}
.badge.budget{background:var(--budget)} .badge.premium{background:var(--premium)}
.card:has(.badge) .rank{background:var(--overall)}
.card:has(.badge.budget) .rank{background:var(--budget)}
.card:has(.badge.premium) .rank{background:var(--premium)}
.scorebar{position:relative;height:8px;background:var(--line);border-radius:6px;margin:12px 0 0;max-width:280px}
.scorebar span{position:absolute;left:0;top:0;bottom:0;background:var(--brand);border-radius:6px}
.scorebar em{position:absolute;right:-2px;top:12px;font-size:.75rem;color:var(--muted);font-style:normal}
.breakdown{margin-top:30px;font-size:.85rem;max-width:520px}
.breakdown summary{cursor:pointer;color:var(--brand-ink);font-weight:700}
.breakdown ul{list-style:none;padding:0;margin:10px 0 6px}
.breakdown li{display:grid;grid-template-columns:150px 1fr auto;gap:10px;align-items:center;margin:6px 0}
.bd-label i{display:block;color:var(--muted);font-style:normal;font-size:.72rem}
.bd-bar{position:relative;height:6px;background:var(--line);border-radius:4px;min-width:50px}
.bd-bar span{position:absolute;left:0;top:0;bottom:0;background:var(--brand);border-radius:4px}
.bd-num{white-space:nowrap;color:var(--muted)}
.bd-num b,.bd-total b{color:var(--ink)}
.bd-feat,.bd-total{margin:6px 0;color:var(--muted)}
.bd-total a{color:var(--brand-ink)}
.tfilter{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:0 0 10px}
.tfilter button{background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:999px;
  padding:4px 12px;font:inherit;font-size:.8rem;cursor:pointer}
.tfilter button.on{background:var(--brand);border-color:var(--brand);color:#231400;font-weight:700}
.sortbtn{all:unset;cursor:pointer;white-space:nowrap}
.sortbtn::after{content:" \2195";opacity:.35;font-size:.8em}
th[aria-sort=ascending] .sortbtn::after{content:" \25B2";opacity:1}
th[aria-sort=descending] .sortbtn::after{content:" \25BC";opacity:1}
.sortbtn:focus-visible{outline:2px solid var(--brand);outline-offset:2px}
.sort-hint{margin:6px 0 0}
.changes ul{list-style:none;padding:0;margin:8px 0 0}
.changes li{padding:8px 0;border-top:1px solid var(--line)}
.changes time{display:inline-block;min-width:110px;color:var(--brand-ink);font-weight:700}
@media (max-width:720px){
  .breakdown li{grid-template-columns:1fr auto}
  .bd-bar{grid-column:1/-1;order:3}
}
.card-buy{text-align:right}
.price{font-size:1.6rem;font-weight:800}
.lowprice{font-size:.75rem;color:var(--muted);margin-top:2px}
.lowprice.best{color:var(--overall);font-weight:700}
.card-buy .btn{margin:8px 0 6px}
.verdict{margin:18px 0 14px;font-size:1.02rem}
.specs{display:grid;grid-template-columns:repeat(4,1fr);gap:10px 18px;margin:0 0 16px;
  padding:14px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.spec dt{font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.03em}
.spec dd{margin:2px 0 0;font-weight:600;font-size:.92rem}
.pc{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.pc h4{margin:0 0 6px} .pc ul{margin:0;padding-left:18px} .pc li{margin:3px 0}
.pros h4{color:var(--overall)} .cons h4{color:#ff7a6b}
/* guide + home */
details{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin:8px 0}
summary{font-weight:700;cursor:pointer}
details p{margin:.6em 0 0;color:var(--muted)}
.group-sub{color:var(--muted);margin:-6px 0 16px}
.cat-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:18px}
.cat-card{display:block;background:var(--card);border-radius:var(--radius);box-shadow:var(--shadow);padding:22px;transition:transform .1s}
.cat-card:hover{transform:translateY(-2px)}
.cat-card h3{margin:.2em 0}
.cat-picks{display:flex;flex-direction:column;gap:4px;margin:12px 0;font-size:.9rem;color:var(--muted)}
/* quick navigation */
.quicknav{margin-top:8px}
.quicknav-controls{display:flex;flex-wrap:wrap;gap:12px;align-items:center}
.quicknav select{appearance:none;-webkit-appearance:none;background-color:var(--card-2);color:var(--ink);
  border:1px solid var(--line);border-radius:9px;padding:10px 40px 10px 14px;font-family:inherit;font-size:.95rem;
  min-width:220px;cursor:pointer;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath fill='none' stroke='%239aa6b7' stroke-width='1.6' d='M1 1.5l5 5 5-5'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 14px center}
.quicknav select:disabled{opacity:.5;cursor:not-allowed}
.quicknav select:focus-visible{outline:2px solid var(--brand);outline-offset:1px}
.quicknav .btn{border:0;cursor:pointer;font-family:inherit;font-size:.95rem}
.quicknav .btn:disabled{opacity:.5;cursor:not-allowed}
.back-home{display:inline-flex;align-items:center;gap:6px;background-color:var(--card-2);color:var(--ink);
  border:1px solid var(--line);border-radius:9px;padding:10px 16px;font-size:.95rem;font-weight:600;white-space:nowrap}
.back-home:hover{border-color:var(--brand);color:var(--brand-ink)}
.back-home:focus-visible{outline:2px solid var(--brand);outline-offset:1px}
/* compact top-of-page toolbar (category pages) */
.quicknav-bar{margin:6px 0 4px;padding-bottom:14px;border-bottom:1px solid var(--line)}
/* deals note */
.pick-group h2{border-top:1px solid var(--line);padding-top:1.2rem}
.pick-card .badge{margin-bottom:4px} .pick-card .verdict{margin:14px 0 6px}
.pick-more{color:var(--brand-ink)}
.seasonal-strip .strip-links{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px}
.bf-table a{color:var(--brand-ink)}
.tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.tag{display:inline-block;border:1px solid var(--line);background:var(--card-2);color:var(--ink);font-size:.72rem;font-weight:700;padding:2px 9px;border-radius:20px}
.brand-vs{margin:0 0 6px;color:var(--muted)} .brand-vs b{color:var(--ink)} .brand-vs a,.brand-also a{color:var(--brand-ink)}
.brand-missing{columns:2} .brand-missing a{color:var(--brand-ink)}
.ghost-btn{background:var(--card-2);color:var(--ink);border:1px solid var(--line)} .ghost-btn:hover{border-color:var(--brand)}
/* brand pages: buy buttons and the home "Shop by brand" buttons take the brand's own colors */
.brand-theme .brand-card .btn,.brand-btn[style]{background:var(--brand-btn);color:var(--brand-btn-ink);border-color:var(--brand-btn)}
.brand-theme .brand-card .btn:hover,.brand-btn[style]:hover{filter:brightness(1.1)}
.brand-theme .brand-card .btn:focus-visible,.brand-btn[style]:focus-visible{outline:2px solid var(--ink);outline-offset:2px}
.vs-link{margin:14px 0 0;color:var(--muted)} .vs-link a{color:var(--brand-ink)}
.vs-verdict p{margin:.5em 0 0} .vs-verdict a{color:var(--brand-ink)}
.vs-table{min-width:0;table-layout:fixed} .vs-table th,.vs-table td{white-space:normal;overflow-wrap:anywhere;padding:10px 8px}
.vs-table th:first-child{text-align:left;color:var(--muted);font-weight:600;width:30%;font-size:.7rem;letter-spacing:0;overflow-wrap:normal;hyphens:auto}
.vs-table .stars{width:66px;height:12px;-webkit-mask-size:13.2px 12px;mask-size:13.2px 12px}
.vs-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px;margin-top:2rem}
.vs-side .badge{margin-bottom:8px;display:inline-block} .vs-side .btn{margin-top:14px}
.vs-related{padding-left:18px} .vs-related li{margin:6px 0} .vs-related a,.howwerank a{color:var(--brand-ink)}
.deals{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--brand);
  border-radius:var(--radius);padding:16px 20px;margin:22px 0}
.deals h2{margin:0 0 .4rem;font-size:1.15rem}
.deals p{margin:0;color:var(--muted);max-width:80ch}
.deals b{color:var(--ink)}
/* collapsible home groups (heading only until hover/click) */
.shop-head{margin:2.4rem 0 0}
details.cats{--cats-top:1.1rem;--cats-side:16px;position:relative;margin:1.2rem 0 0;border-top:1px solid var(--line);padding-top:var(--cats-top)}
details.cats>summary{cursor:pointer;list-style:none;display:flex;align-items:center;gap:12px}
details.cats>summary::-webkit-details-marker{display:none}
details.cats>summary h2{margin:0}
details.cats>summary::after{content:"";margin-left:auto;flex:none;width:9px;height:9px;
  border-right:2px solid var(--muted);border-bottom:2px solid var(--muted);
  transform:rotate(45deg);transition:transform .15s}
details.cats[open]>summary::after{transform:rotate(-135deg)}
/* open groups swap the chevron for a Collapse button in the same spot */
details.cats[open]>summary{padding-right:120px}
details.cats[open]:has(.cats-collapse:not([hidden]))>summary::after{display:none}
.cats-collapse{display:none;position:absolute;top:var(--cats-top);right:var(--cats-side);margin-top:3px;
  background:var(--card-2);color:var(--ink);border:1px solid var(--line);border-radius:9px;
  padding:6px 12px;font:600 .85rem/1.2 inherit;font-family:inherit;cursor:pointer}
details.cats[open]>.cats-collapse:not([hidden]){display:inline-flex;align-items:center;gap:6px}
.cats-collapse::after{content:"";width:7px;height:7px;border-right:2px solid currentColor;border-bottom:2px solid currentColor;
  transform:rotate(-135deg);margin-top:4px}
.cats-collapse:hover{border-color:var(--brand);color:var(--brand-ink)}
.cats-collapse:focus-visible{outline:2px solid var(--brand);outline-offset:2px}
details.cats>summary:hover h2{color:var(--brand-ink)}
details.cats>summary:hover::after{border-color:var(--brand-ink)}
details.cats>summary:focus-visible{outline:2px solid var(--brand);outline-offset:3px;border-radius:6px}
details.cats .group-sub{margin-top:14px}
@media (max-width:720px){
  .quicknav-controls{flex-direction:column;align-items:stretch}
  .quicknav select,.quicknav .btn,.back-home{width:100%;text-align:center;justify-content:center}
}
/* avoid — comparison row */
tr.avoid-row td{background:#2a1414;color:#ff9d94;font-weight:600;border-bottom:1px solid #4a2222}
tr.avoid-row a{color:#ff9d94;text-decoration:underline}
tr.avoid-row td b{color:#ff6b5c;letter-spacing:.04em}
/* avoid — section + card */
.avoid h2{color:#ff6b5c}
.avoid-lead{max-width:75ch;color:var(--muted)}
.avoid-card{position:relative;background:var(--card);border:2px solid #e0483c;
  border-radius:var(--radius);padding:22px;margin:14px 0;box-shadow:var(--shadow)}
.avoid-card::before{content:"";position:absolute;inset:0;border-radius:var(--radius);
  background:linear-gradient(180deg,rgba(224,72,60,.10),transparent 120px);pointer-events:none}
.avoid-flag{position:absolute;top:-13px;left:18px;background:#c0261e;color:#fff;font-weight:800;
  font-size:.78rem;letter-spacing:.05em;text-transform:uppercase;padding:4px 14px;border-radius:20px;
  box-shadow:0 2px 6px rgba(192,38,30,.4)}
.avoid-head{display:grid;grid-template-columns:110px 1fr;gap:16px;align-items:center}
.avoid-card .card-img img{width:110px;height:110px;object-fit:contain;background:#fff;border-radius:10px;filter:grayscale(.15)}
.avoid-card .verdict{color:#ff9d94}
.reasons h4{margin:0 0 6px;color:#ff6b5c}
.reasons ul{margin:0 0 16px;padding-left:20px} .reasons li{margin:6px 0}
/* footer */
footer{max-width:var(--max);margin:0 auto;padding:24px 20px 50px;border-top:1px solid var(--line)}
.disclosure{font-size:.85rem;color:var(--muted);max-width:80ch}
/* responsive */
@media (max-width:720px){
  .heroes{grid-template-columns:1fr}
  .card-head{grid-template-columns:96px 1fr}
  .card-img img{width:96px;height:96px}
  .card-buy{grid-column:1/-1;text-align:left;display:flex;align-items:center;gap:14px}
  .card-buy .btn{margin:0}
  .specs{grid-template-columns:repeat(2,1fr)}
  .pc{grid-template-columns:1fr}
  .hero-card img{width:88px;height:88px}
}
/* mobile layer: jump bar, swipe hint and back-to-top are phone-only; desktop is unchanged */
.jump,.swipe-hint,.to-top{display:none}
@media (max-width:720px){
  /* header */
  header.site{padding:10px 16px;gap:8px}
  .logo img{height:40px}
  .slogan{display:none}
  main{padding:0 16px 32px}
  h1{font-size:1.7rem}
  .home h1{font-size:1.9rem}
  h2{font-size:1.3rem;margin:1.8rem 0 .8rem}
  .lead{padding:8px 0 4px}
  .lead .sub{font-size:1rem}

  /* compact quick nav: selects side by side, Home + Go side by side */
  .quicknav-controls{display:grid;grid-template-columns:1fr 1fr;gap:8px}
  .quicknav select{min-width:0;width:100%;padding:9px 28px 9px 10px;font-size:.88rem;text-align:left;
    background-position:right 10px center}
  .quicknav .btn,.back-home{padding:9px 12px;font-size:.9rem}
  .quicknav #qn-category{order:1} .quicknav #qn-subcategory{order:2}
  .quicknav .back-home{order:3} .quicknav #qn-go{order:4}
  .quicknav:not(.quicknav-bar) #qn-go{grid-column:1/-1}
  .quicknav-bar{margin:0 0 4px;padding-bottom:10px}

  /* on-this-page jump bar, sticks to the top while scrolling */
  .jump{display:flex;gap:8px;overflow-x:auto;position:sticky;top:0;z-index:20;
    margin:10px -16px 0;padding:8px 16px;background:rgba(0,0,0,.92);backdrop-filter:blur(6px);
    border-bottom:1px solid var(--line);scrollbar-width:none}
  .jump::-webkit-scrollbar{display:none}
  .jump a{flex:none;background:var(--card-2);border:1px solid var(--line);border-radius:20px;
    padding:6px 13px;font-size:.85rem;font-weight:600;color:var(--ink)}
  .jump a.avoid-link{color:#ff9d94;border-color:#4a2222}
  section[id]{scroll-margin-top:60px}

  /* hero picks */
  .heroes{gap:16px}
  .hero-card{padding:14px}
  .hero-card img{width:76px;height:76px}
  .hero-price{font-size:1.3rem;margin:6px 0}

  /* comparison table: pin # and Tool, hint that it scrolls */
  .swipe-hint{display:block;margin:-4px 0 8px;font-size:.8rem;color:var(--muted)}
  #compare table{font-size:.85rem}
  #compare th,#compare td{padding:9px 10px}
  #compare tr>:nth-child(1),#compare tr>:nth-child(2){position:sticky;z-index:1;background:var(--card)}
  #compare tr>:nth-child(1){left:0;width:38px;min-width:38px;max-width:38px}
  #compare tr>:nth-child(2){left:37px;white-space:normal;min-width:120px;max-width:130px;
    box-shadow:6px 0 8px -6px rgba(0,0,0,.9)}
  #compare tr>th:nth-child(-n+2){background:#181c23}
  #compare tr.avoid-row>:nth-child(-n+2){background:#2a1414}

  /* product cards: price + sales note on one line, full-width buy button under */
  .card{padding:16px;margin:14px 0}
  .card-head{gap:12px}
  .card-title h3{font-size:1.05rem}
  .card-buy{display:grid;grid-template-columns:1fr auto;align-items:center;gap:8px 12px;margin-top:4px}
  .card-buy .price{grid-row:1;grid-column:1;font-size:1.45rem}
  .card-buy .tiny{grid-row:1;grid-column:2}
  .card-buy .btn{grid-row:2;grid-column:1/-1;text-align:center;padding:13px 16px;font-size:1rem;margin:0}
  .verdict{margin:14px 0 12px;font-size:.98rem}
  .avoid-card{padding:18px 16px}

  /* home: less nested padding */
  details.cats{padding:12px;--cats-top:12px;--cats-side:12px}
  .cat-grid{gap:12px}
  .cat-card{padding:16px}
  .cat-picks{margin:8px 0}

  /* holiday strip on home */
  .seasonal-strip .strip-links .btn{flex:1 1 100%;text-align:center}

  /* back to top */
  .to-top{display:flex;align-items:center;justify-content:center;position:fixed;right:16px;bottom:18px;z-index:30;
    width:44px;height:44px;border-radius:50%;background:var(--brand);color:#231400;font-weight:800;font-size:1.2rem;
    box-shadow:0 4px 14px rgba(0,0,0,.6);opacity:0;pointer-events:none;transition:opacity .2s}
  .to-top.show{opacity:1;pointer-events:auto}
}
"""

if __name__ == "__main__":
    main()
