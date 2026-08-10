#!/usr/bin/env python3
"""ToolTop10 static site generator.

Reads data/site.json + data/<category>.json, scores and ranks each product on a
single 100-point scale, then writes a static site into docs/ (served by GitHub Pages).

No third-party dependencies. Run:  python build.py
"""
import json
import math
import html
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
OUT = ROOT / "docs"
ASSETS = OUT / "assets"


# ----------------------------------------------------------------------------- data
def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


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
    overall = max(kits, key=lambda p: p["score"]) if kits else ranked[0]
    budget_pool = [p for p in kits if p["price"] <= cap] or [p for p in ranked if p["price"] <= cap]
    budget = max(budget_pool, key=lambda p: p["score"]) if budget_pool else None
    for p in ranked:
        p["badge"] = None
    overall["badge"] = "Best Overall"
    if budget and budget is not overall:
        budget["badge"] = "Best Budget"
    return ranked, overall, budget


# --------------------------------------------------------------------------- helpers
def esc(s):
    return html.escape(str(s)) if s is not None else ""


def money(v):
    return f"${v:,.2f}".rstrip("0").rstrip(".") if v == int(v) else f"${v:,.2f}"


def stars(rating):
    pct = round(rating / 5 * 100)
    return (f'<span class="stars" style="--pct:{pct}%" '
            f'aria-label="{rating} out of 5 stars"></span>')


def spec_rows(specs):
    labels = {
        "voltage": "Voltage", "chuck": "Chuck", "max_rpm": "Max speed",
        "speeds": "Transmission", "torque": "Torque", "clutch": "Clutch",
        "battery": "Battery", "weight": "Weight",
    }
    out = []
    for k, label in labels.items():
        v = specs.get(k)
        if v is None or v == "":
            v = "&mdash;"
        elif k == "max_rpm":
            v = f"{v:,} rpm"
        else:
            v = esc(v)
        out.append(f'<div class="spec"><dt>{label}</dt><dd>{v}</dd></div>')
    return "\n".join(out)


# --------------------------------------------------------------------------- render
def render_hero_card(p, site, cat):
    url = amazon_url(p["asin"], site["affiliate_tag"], site["amazon_domain"])
    return f"""
    <a class="hero-card {'overall' if p['badge']=='Best Overall' else 'budget'}"
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


def render_card(p, site):
    url = amazon_url(p["asin"], site["affiliate_tag"], site["amazon_domain"])
    badge = f'<span class="badge">{esc(p["badge"])}</span>' if p["badge"] else ""
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
        </div>
        <div class="card-buy">
          <div class="price">{money(p['price'])}</div>
          <a class="btn" href="{url}" target="_blank" rel="sponsored nofollow noopener">Check price on Amazon</a>
          <div class="tiny muted">{esc(p.get('bought',''))}</div>
        </div>
      </div>
      <p class="verdict">{esc(p['verdict'])}</p>
      <dl class="specs">{spec_rows(p['specs'])}</dl>
      <div class="pc">
        <div class="pros"><h4>Pros</h4><ul>{pros}</ul></div>
        <div class="cons"><h4>Cons</h4><ul>{cons}</ul></div>
      </div>
    </article>"""


def render_table(ranked, avoid, site):
    head = ("<tr><th>#</th><th>Tool</th><th>Price</th><th>Rating</th>"
            "<th>Reviews</th><th>Voltage</th><th>Max speed</th><th>Chuck</th>"
            "<th>Brushless</th><th>Score</th></tr>")
    rows = []
    for p in ranked:
        rpm = f'{p["specs"]["max_rpm"]:,}' if p["specs"].get("max_rpm") else "&mdash;"
        rows.append(
            f'<tr><td class="c">{p["rank"]}</td>'
            f'<td><a href="#{p["asin"]}">{esc(p["brand"])} {esc(p["model"])}</a></td>'
            f'<td>{money(p["price"])}</td>'
            f'<td class="c">{p["rating"]}</td>'
            f'<td class="c">{p["reviews_count"]:,}</td>'
            f'<td>{esc(p["specs"].get("voltage") or "&mdash;")}</td>'
            f'<td>{rpm}</td>'
            f'<td>{esc(p["specs"].get("chuck") or "&mdash;")}</td>'
            f'<td class="c">{"Yes" if p["features"]["brushless"] else "No"}</td>'
            f'<td class="c"><b>{p["score"]}</b></td></tr>')
    for a in avoid:
        rows.append(
            f'<tr class="avoid-row"><td class="c">&#10005;</td>'
            f'<td><a href="#avoid-{a["asin"]}">{esc(a["brand"])} {esc(a["model"])}</a></td>'
            f'<td>{money(a["price"])}</td>'
            f'<td class="c">{a["rating"]}</td>'
            f'<td class="c">{a["reviews_count"]:,}</td>'
            f'<td class="c" colspan="4">{esc(a.get("flag", "Avoid"))}</td>'
            f'<td class="c"><b>AVOID</b></td></tr>')
    return f'<div class="tablewrap"><table>{head}{"".join(rows)}</table></div>'


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
  <section class="avoid">
    <h2>Tools to avoid</h2>
    <p class="avoid-lead">Not everything in the cordless-drill search results deserves your money.
    This one would rank dead last on our scale — here's the listing to walk past, and exactly why.</p>
    {''.join(cards)}
  </section>"""


def render_guide(items):
    out = []
    for it in items:
        out.append(f"<details><summary>{esc(it['q'])}</summary>"
                   f"<p>{esc(it['a'])}</p></details>")
    return "\n".join(out)


def page(site, title, body, is_home=False):
    tag_state = ("" if site["affiliate_tag"] else
                 '<div class="notice">Preview build &mdash; affiliate links are '
                 'untagged until the Amazon Associates account is approved.</div>')
    home_link = "" if is_home else '<a href="index.html">&larr; All categories</a>'
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(site['description'])}">
<link rel="stylesheet" href="assets/styles.css">
</head>
<body>
<header class="site">
  <a class="logo" href="index.html">{esc(site['brand'])}</a>
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
  <p class="muted">{home_link} &nbsp; Last updated on {esc(site['updated'])}. Not affiliated with Amazon or any manufacturer.</p>
</footer>
</body>
</html>"""


def build_category(site, filename):
    cat = load(filename)
    ranked, overall, budget = rank_products(cat)
    avoid = cat.get("avoid", [])
    heroes = "".join(render_hero_card(p, site, cat) for p in (overall, budget) if p)
    cards = "".join(render_card(p, site) for p in ranked)
    body = f"""
  <section class="lead">
    <h1>{esc(cat['title'])}</h1>
    <p class="sub">{esc(cat['subtitle'])}</p>
    <p class="intro">{esc(cat['intro'])}</p>
  </section>
  <section class="heroes">{heroes}</section>
  <section class="compare">
    <h2>Side-by-side comparison</h2>
    {render_table(ranked, avoid, site)}
  </section>
  <section class="ranked">
    <h2>The full ranking</h2>
    {cards}
  </section>
  <section class="howwerank">
    <h2>How we rank</h2>
    <p>Every drill gets one score from 0 to 100, weighted
    {int(cat['weights']['rating']*100)}% on its star rating,
    {int(cat['weights']['reviews']*100)}% on how many people have reviewed it (more reviews = more
    confidence the rating is real), and {int(cat['weights']['features']*100)}% on features like a
    brushless motor, two-speed gearbox, LED light, and a second battery. <b>Best Overall</b> is the
    highest score. <b>Best Budget</b> is the highest score at or under ${cat['budget_cap']}.</p>
  </section>
  <section class="guide">
    <h2>Buyer's guide</h2>
    {render_guide(cat['buyers_guide'])}
  </section>
  {render_avoid(avoid, site)}"""
    (OUT / f"{cat['slug']}.html").write_text(
        page(site, f"{cat['title']} — {site['brand']}", body), encoding="utf-8")
    return cat, overall, budget


def build_home(site, cats):
    cards = []
    for cat, overall, budget in cats:
        c = next(c for c in site["categories"] if c["slug"] == cat["slug"])
        cards.append(f"""
      <a class="cat-card" href="{esc(cat['slug'])}.html">
        <h3>{esc(c['title'])}</h3>
        <p>{esc(c['blurb'])}</p>
        <div class="cat-picks">
          <span><b>Best Overall:</b> {esc(overall['brand'])} {esc(overall['model'])}</span>
          <span><b>Best Budget:</b> {esc(budget['brand'])} {esc(budget['model'])}</span>
        </div>
        <span class="btn ghost">See the top {c['count']} &rarr;</span>
      </a>""")
    body = f"""
  <section class="lead home">
    <h1>{esc(site['brand'])}</h1>
    <p class="sub">{esc(site['description'])}</p>
  </section>
  <section class="cats">
    <h2>Categories</h2>
    <div class="cat-grid">{''.join(cards)}</div>
  </section>"""
    (OUT / "index.html").write_text(
        page(site, f"{site['brand']} — {site['tagline']}", body, is_home=True),
        encoding="utf-8")


def main():
    site = load("site.json")
    OUT.mkdir(exist_ok=True)
    ASSETS.mkdir(exist_ok=True)
    (ASSETS / "styles.css").write_text(CSS, encoding="utf-8")
    # GitHub Pages: custom-domain file + disable Jekyll processing
    if site.get("custom_domain"):
        (OUT / "CNAME").write_text(site["custom_domain"], encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    cats = [build_category(site, f"{c['slug']}.json") for c in site["categories"]]
    build_home(site, cats)
    print(f"Built {len(cats)} category page(s) + home into {OUT}")
    for cat, overall, budget in cats:
        print(f"  {cat['slug']}: Best Overall = {overall['brand']} {overall['model']} "
              f"(score {overall['score']}); Best Budget = {budget['brand']} {budget['model']} "
              f"(score {budget['score']})")


CSS = r"""
:root{
  --bg:#f6f7f9; --card:#fff; --ink:#14181f; --muted:#697386; --line:#e4e7ec;
  --brand:#f4820b; --brand-ink:#b45c00; --overall:#1a7f4b; --budget:#2563c9;
  --star:#f5a623; --shadow:0 1px 2px rgba(16,24,40,.06),0 8px 24px rgba(16,24,40,.06);
  --radius:14px; --max:1060px;
}
@media (prefers-color-scheme:dark){
  :root{--bg:#0f1319;--card:#171c24;--ink:#e9edf3;--muted:#94a0b3;--line:#252c37;
    --brand:#ff9526;--brand-ink:#ffb35a;--overall:#37c07d;--budget:#5b9bff;--shadow:0 8px 24px rgba(0,0,0,.35);}
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.6 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
main{max-width:var(--max);margin:0 auto;padding:0 20px 40px}
h1{font-size:2.1rem;line-height:1.15;margin:.2em 0}
h2{font-size:1.5rem;margin:2.2rem 0 1rem}
.muted{color:var(--muted)} .tiny{font-size:.8rem} .c{text-align:center}
/* header */
header.site{max-width:var(--max);margin:0 auto;padding:20px;display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}
.logo{font-weight:800;font-size:1.35rem;color:var(--brand)}
.slogan{color:var(--muted);font-size:.95rem}
.notice{max-width:var(--max);margin:0 auto 8px;padding:8px 20px;color:var(--brand-ink);font-size:.85rem}
/* lead */
.lead{padding:14px 0 8px}
.lead .sub{font-size:1.15rem;color:var(--muted);margin:.3em 0}
.lead .intro{max-width:70ch}
.home h1{font-size:2.6rem}
/* stars */
.stars{--pct:100%;display:inline-block;width:88px;height:16px;vertical-align:-2px;
  background:linear-gradient(90deg,var(--star) var(--pct),#c9ced8 var(--pct));
  -webkit-mask:repeat-x left/17.6px 16px;mask:repeat-x left/17.6px 16px;
  -webkit-mask-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='17.6' height='16' viewBox='0 0 20 20'%3E%3Cpath d='M10 1l2.6 5.3 5.9.9-4.3 4.1 1 5.8L10 14.9 4.8 17.6l1-5.8L1.5 7.7l5.9-.9z'/%3E%3C/svg%3E");
  mask-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='17.6' height='16' viewBox='0 0 20 20'%3E%3Cpath d='M10 1l2.6 5.3 5.9.9-4.3 4.1 1 5.8L10 14.9 4.8 17.6l1-5.8L1.5 7.7l5.9-.9z'/%3E%3C/svg%3E")}
/* hero cards */
.heroes{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:14px}
.hero-card{display:flex;gap:16px;background:var(--card);border-radius:var(--radius);
  box-shadow:var(--shadow);padding:18px;border-top:4px solid var(--overall);position:relative;transition:transform .1s}
.hero-card.budget{border-top-color:var(--budget)}
.hero-card:hover{transform:translateY(-2px)}
.hero-card img{width:120px;height:120px;object-fit:contain;flex:none;background:#fff;border-radius:10px}
.hero-tag{position:absolute;top:-11px;left:16px;background:var(--overall);color:#fff;
  font-size:.72rem;font-weight:700;letter-spacing:.03em;text-transform:uppercase;padding:3px 10px;border-radius:20px}
.hero-card.budget .hero-tag{background:var(--budget)}
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
.card:has(.badge) .rank{background:var(--overall)}
.scorebar{position:relative;height:8px;background:var(--line);border-radius:6px;margin:12px 0 0;max-width:280px}
.scorebar span{position:absolute;left:0;top:0;bottom:0;background:var(--brand);border-radius:6px}
.scorebar em{position:absolute;right:-2px;top:12px;font-size:.75rem;color:var(--muted);font-style:normal}
.card-buy{text-align:right}
.price{font-size:1.6rem;font-weight:800}
.card-buy .btn{margin:8px 0 6px}
.verdict{margin:18px 0 14px;font-size:1.02rem}
.specs{display:grid;grid-template-columns:repeat(4,1fr);gap:10px 18px;margin:0 0 16px;
  padding:14px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.spec dt{font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.03em}
.spec dd{margin:2px 0 0;font-weight:600;font-size:.92rem}
.pc{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.pc h4{margin:0 0 6px} .pc ul{margin:0;padding-left:18px} .pc li{margin:3px 0}
.pros h4{color:var(--overall)} .cons h4{color:#c0392b}
@media (prefers-color-scheme:dark){.cons h4{color:#ff7a6b}}
/* guide + home */
details{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin:8px 0}
summary{font-weight:700;cursor:pointer}
details p{margin:.6em 0 0;color:var(--muted)}
.cat-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:18px}
.cat-card{display:block;background:var(--card);border-radius:var(--radius);box-shadow:var(--shadow);padding:22px;transition:transform .1s}
.cat-card:hover{transform:translateY(-2px)}
.cat-card h3{margin:.2em 0}
.cat-picks{display:flex;flex-direction:column;gap:4px;margin:12px 0;font-size:.9rem;color:var(--muted)}
/* avoid — comparison row */
tr.avoid-row td{background:#fdecec;color:#a11a1a;font-weight:600;border-bottom:1px solid #f3c9c9}
tr.avoid-row a{color:#a11a1a;text-decoration:underline}
tr.avoid-row td b{color:#c0261e;letter-spacing:.04em}
@media (prefers-color-scheme:dark){
  tr.avoid-row td{background:#3a1515;color:#ff9d94;border-bottom-color:#5a2020}
  tr.avoid-row a{color:#ff9d94} tr.avoid-row td b{color:#ff6b5c}
}
/* avoid — section + card */
.avoid h2{color:#c0261e}
@media (prefers-color-scheme:dark){.avoid h2{color:#ff6b5c}}
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
.avoid-card .verdict{color:#a11a1a}
@media (prefers-color-scheme:dark){.avoid-card .verdict{color:#ff9d94}}
.reasons h4{margin:0 0 6px;color:#c0261e}
@media (prefers-color-scheme:dark){.reasons h4{color:#ff6b5c}}
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
"""

if __name__ == "__main__":
    main()
