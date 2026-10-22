#!/usr/bin/env python3
"""Generate Pinterest pins (1000x1500 PNG) from the ranked category data, plus a
CSV for Pinterest's bulk upload (Settings > Import content > Upload .csv).

Pins are text graphics in the site's colors -- no Amazon product photos (the
Associates agreement doesn't allow re-hosting them) and no prices except on the
Black Friday cheat sheet, which is dated, because a pin keeps circulating for
months after the price moves.

Images are written to docs/pins/ so GitHub Pages serves them at a public URL,
which the bulk upload requires. Needs Pillow (the site build itself does not):

    pip install pillow
    python scripts/make_pins.py --start 2026-09-28 --per-day 5
    python scripts/make_pins.py --only sample      # one of each format, no CSV
"""
import argparse
import csv
import datetime
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import build  # noqa: E402  (reuses the site's loading, ranking and gift rules)

OUT = ROOT / "docs" / "pins"
CSV_DIR = ROOT / "marketing" / "pins"
FONTS = Path(__file__).parent / "fonts"
W, H = 1000, 1500
PAD = 64

BG, CARD, LINE = "#000000", "#14181f", "#282f3a"
INK, MUTED = "#eaeef4", "#9aa6b7"
BRAND, OVERALL, BUDGET, AVOID, STAR = "#ff9526", "#37c07d", "#5b9bff", "#e0483c", "#f5a623"

BOARDS = {
    "wireless": "Best Cordless Power Tools",
    "wired": "Best Corded Power Tools",
    "hand": "Hand Tool Essentials",
    "storage": "Tool Storage & Organization",
    "air": "Air Tools & Compressors",
    "measure": "Measuring & Layout Tools",
    "garage": "Garage & Auto Shop Tools",
    "yard": "Cordless Yard Tools",
    "gifts": "Tool Gift Ideas (Holiday 2026)",
}
GROUP_NOUN = {"wireless": "Cordless Tool", "wired": "Corded Tool", "hand": "Hand Tool", "storage": "Tool Storage",
              "air": "Air Tool", "measure": "Measuring Tool", "garage": "Garage & Car",
              "yard": "Yard Tool"}


def font(weight, size):
    return ImageFont.truetype(str(FONTS / f"inter-{weight}.ttf"), size)


def symbol_font(size):
    """Inter's latin subset has no arrows; DejaVu (on most Linux boxes) does."""
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return None


def wrap(draw, text, fnt, width, max_lines):
    """Greedy word wrap by pixel width; ellipsis on the last line if it overflows."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=fnt) <= width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and draw.textlength(last + "…", font=fnt) > width:
            last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
        lines[-1] = last.rstrip(",.;:—- ") + "…"
    return lines


def text_block(draw, xy, text, fnt, fill, width, max_lines, gap=1.18):
    x, y = xy
    lines = wrap(draw, text, fnt, width, max_lines)
    step = int(fnt.size * gap)
    for ln in lines:
        draw.text((x, y), ln, font=fnt, fill=fill)
        y += step
    return y


def star(draw, cx, cy, r, fill):
    import math
    pts = []
    for i in range(10):
        rad = r if i % 2 == 0 else r * 0.45
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    draw.polygon(pts, fill=fill)


def rating_line(draw, x, y, p, size=30):
    star(draw, x + size * 0.5, y + size * 0.55, size * 0.52, STAR)
    f = font(700, size)
    draw.text((x + size * 1.25, y), f"{p['rating']}", font=f, fill=INK)
    tx = x + size * 1.25 + draw.textlength(f"{p['rating']}", font=f) + 14
    draw.text((tx, y + 2), f"{p['reviews_count']:,} reviews", font=font(400, size - 4), fill=MUTED)


def pill(draw, x, y, text, fill, fnt, ink="#ffffff", padx=18, pady=8):
    tw = draw.textlength(text, font=fnt)
    h = fnt.size + pady * 2
    draw.rounded_rectangle((x, y, x + tw + padx * 2, y + h), radius=h // 2, fill=fill)
    draw.text((x + padx, y + pady - 2), text, font=fnt, fill=ink)
    return x + tw + padx * 2


def canvas():
    img = Image.new("RGB", (W, H), BG)
    logo = Image.open(ROOT / "docs" / "assets" / "logo.png").convert("RGB")
    lw = 330
    logo = logo.resize((lw, int(logo.height * lw / logo.width)), Image.LANCZOS)
    img.paste(logo, ((W - lw) // 2, 44))
    return img, ImageDraw.Draw(img)


def header(draw, kicker, title, color=BRAND, y=200):
    kf = font(700, 30)
    draw.text(((W - draw.textlength(kicker, font=kf)) // 2, y), kicker, font=kf, fill=color)
    tf = font(900, 76)
    y += 56
    for ln in wrap(draw, title, tf, W - PAD * 2, 3):
        draw.text(((W - draw.textlength(ln, font=tf)) // 2, y), ln, font=tf, fill=INK)
        y += 86
    return y + 24


def footer(draw, cta, color=BRAND):
    cf, af = font(900, 38), symbol_font(38)
    ink = "#231400" if color == BRAND else "#ffffff"
    arrow = " →" if af else ""
    bw = draw.textlength(cta, font=cf) + (draw.textlength(arrow, font=af) if af else 0) + 80
    x0, y0 = (W - bw) // 2, H - 190
    draw.rounded_rectangle((x0, y0, x0 + bw, y0 + 84), radius=18, fill=color)
    draw.text((x0 + 40, y0 + 20), cta, font=cf, fill=ink)
    if af:
        draw.text((x0 + 40 + draw.textlength(cta, font=cf), y0 + 18), arrow, font=af, fill=ink)
    uf = font(700, 30)
    u = "toolboxtop10.com"
    draw.text(((W - draw.textlength(u, font=uf)) // 2, H - 80), u, font=uf, fill=MUTED)


def product_rows(draw, y, items, bottom):
    """items: [(label, label_color, p)] stacked cards filling y..bottom."""
    n = len(items)
    gap = 18
    h = (bottom - y - gap * (n - 1)) // n
    big = h >= 230
    for i, (label, color, p) in enumerate(items):
        top = y + i * (h + gap)
        draw.rounded_rectangle((PAD, top, W - PAD, top + h), radius=22, fill=CARD)
        draw.rounded_rectangle((PAD, top, PAD + 10, top + h), radius=5, fill=color)
        x = PAD + 40
        cy = top + (26 if big else 18)
        pill(draw, x, cy, label, color, font(900, 24 if big else 21))
        cy += 52 if big else 44
        cy = text_block(draw, (x, cy), p["name"], font(700, 38 if big else 32), INK,
                        W - PAD * 2 - 80, 2 if big else 1)
        rating_line(draw, x, cy + 6, p, 30 if big else 26)
        sf = font(900, 30 if big else 26)
        s = f"Score {p['score']}"
        draw.text((W - PAD - 36 - draw.textlength(s, font=sf), top + (30 if big else 20)), s, font=sf, fill=BRAND)
    return y + n * h + (n - 1) * gap


# ----------------------------------------------------------------------- formats
def pin_top3(site, cat, overall, budget, year):
    ranked = sorted(cat["products"], key=lambda p: p["rank"])
    picks, seen = [], set()
    picks.append(("Best Overall", OVERALL, overall))
    seen.add(overall["asin"])
    if budget:
        seen.add(budget["asin"])
    top = next((p for p in ranked if p["asin"] not in seen), None)
    if top:
        picks.append((f"Ranked #{top['rank']} of 10", BRAND, top))
    if budget:
        picks.append(("Best Budget", BUDGET, budget))
    name = build.cat_name(cat)
    img, d = canvas()
    y = header(d, "RANKED FROM REAL AMAZON REVIEWS", f"The 3 Best {name} ({year})")
    product_rows(d, y, picks, H - 230)
    footer(d, "See all 10 + the one to avoid")
    title = f"The Best {name} ({year}): Top 3 Ranked From Real Reviews"
    desc = (f"Which {name.lower()} are actually worth buying? We scored 10 on star rating, "
            f"number of reviews and the features that matter. Best Overall: {overall['brand']} "
            f"{overall['model']}. Best Budget: {budget['brand']} {budget['model']}. "
            f"See the full top 10, specs, pros and cons — plus the one to avoid.")
    kw = [f"best {name.lower()}", f"{name.lower()} {year}", f"{name.lower()} review",
          f"{name.lower()} for beginners", "diy tools", "tool reviews"]
    return img, title, desc, f"{cat['slug']}.html", kw


def pin_avoid(site, cat, overall, budget, year):
    a = cat["avoid"][0]
    name = build.cat_name(cat)
    img, d = canvas()
    y = header(d, name.upper(), "Don't Buy This One.", AVOID)
    d.rounded_rectangle((PAD, y, W - PAD, H - 230), radius=22, fill=CARD, outline=AVOID, width=4)
    x, cy, tw = PAD + 44, y + 36, W - PAD * 2 - 88
    pill(d, x, cy, "AVOID", AVOID, font(900, 26))
    cy += 70
    cy = text_block(d, (x, cy), a["name"], font(900, 44), INK, tw, 2)
    rating_line(d, x, cy + 8, a, 28)
    cy += 70
    d.text((x, cy), "WHY WE'D SKIP IT", font=font(700, 26), fill=AVOID)
    cy += 46
    reasons = [a.get("flag", "")] + [r.split(". ")[0].rstrip(".") for r in a["reasons"]]
    reasons = [r for r in dict.fromkeys(reasons) if r][:3]
    rf = font(400, 32)
    for r in reasons:
        if cy > H - 520:
            break
        d.ellipse((x, cy + 12, x + 12, cy + 24), fill=AVOID)
        cy = text_block(d, (x + 30, cy), r, rf, INK, tw - 30, 3) + 14
    cy = max(cy + 10, H - 470)
    d.line((x, cy, W - PAD - 44, cy), fill=LINE, width=2)
    cy += 26
    d.text((x, cy), "BUY THIS INSTEAD", font=font(700, 26), fill=OVERALL)
    cy += 44
    cy = text_block(d, (x, cy), overall["name"], font(700, 36), INK, tw, 2)
    rating_line(d, x, cy + 6, overall, 28)
    footer(d, "See the full top 10")
    title = f"{name} to Avoid: Don't Buy the {a['brand']} {a['model']}"
    desc = (f"Before you buy {name.lower()} on Amazon, skip this one: the {a['name']}. "
            f"{a['verdict']} What to buy instead: the {overall['brand']} {overall['model']}, "
            f"our Best Overall. See all 10 ranked from real reviews.")
    kw = [f"{name.lower()} to avoid", f"best {name.lower()}", "tools to avoid",
          "amazon tool buying guide", "diy tools"]
    return img, title, desc, f"{cat['slug']}.html#avoid", kw


def pin_gifts(site, group, picks, cfg):
    hi = cfg["max_price"]
    band = f"Under ${hi}" if not cfg["min_price"] else f"${int(cfg['min_price'])}–${hi}"
    noun = GROUP_NOUN[group]
    img, d = canvas()
    y = header(d, "HOLIDAY GIFT GUIDE 2026", f"{noun} Gifts {band}")
    items = [(build.cat_name(cat), BRAND, p) for cat, p in picks[:5]]
    product_rows(d, y, items, H - 230)
    footer(d, "See every gift pick")
    title = f"Best {noun} Gifts {band} (2026)"
    desc = (f"{noun} gift ideas {band.lower()}, picked by score from real Amazon reviews — "
            f"for dads, husbands, DIYers and new homeowners. "
            + "; ".join(f"{build.cat_name(c)}: {p['brand']} {p['model']}" for c, p in picks[:5])
            + (". Air tools need an air compressor." if group == "air" else ". Ready to use out of the box."))
    kw = [f"tool gifts {band.lower()}", "gifts for dad", "gifts for him", "diy gift ideas",
          "christmas gifts for men", f"{noun.lower()} gifts"]
    return img, title, desc, f"{cfg['slug']}.html", kw


POPULAR = ["cordless-drills", "cordless-impact-drivers", "cordless-circular-saws",
           "cordless-reciprocating-saws", "cordless-oscillating-tools",
           "cordless-random-orbital-sanders", "cordless-impact-wrenches",
           "socket-sets", "rolling-tool-chests", "cordless-angle-grinders"]


def _day(iso):
    d = datetime.date.fromisoformat(iso)
    return f"{d:%b} {d.day}, {d.year}"


def _captured(rows):
    """'Oct 2026' or 'Sept-Oct 2026': when the prices on a holiday pin were read off Amazon."""
    ds = sorted(datetime.date.fromisoformat(str(c["data_captured"])) for c, _o in rows)
    a, b = ds[0], ds[-1]
    return f"{a:%b %Y}" if (a.year, a.month) == (b.year, b.month) else f"{a:%b}-{b:%b %Y}"


def pin_holiday_cheatsheet(site, rows, cfg):
    """Dated price-to-beat sheet for one holiday deal page. Prices are allowed here (and only
    here) because the pin names the month they were captured."""
    deal, first = cfg["deal_name"], cfg["key_dates"][0]
    img, d = canvas()
    y = header(d, f"{deal.upper()} · {_day(first['date']).upper()}", "Tool Price Cheat Sheet")
    d.text((PAD, y), "Our #1 pick and its regular price. Beat it or skip it.",
           font=font(400, 30), fill=MUTED)
    y += 64
    rf, pf, cf = font(700, 30), font(900, 32), font(400, 22)
    row_h = 84
    for cat, o in rows[:10]:
        d.rounded_rectangle((PAD, y, W - PAD, y + row_h - 10), radius=14, fill=CARD)
        d.text((PAD + 28, y + 8), build.cat_name(cat).upper(), font=cf, fill=MUTED)
        name = wrap(d, f"{o['brand']} {o['model']}", rf, W - PAD * 2 - 240, 1)[0]
        d.text((PAD + 28, y + 36), name, font=rf, fill=INK)
        pr = build.money(o["price"])
        d.text((W - PAD - 28 - d.textlength(pr, font=pf), y + 22), pr, font=pf, fill=BRAND)
        y += row_h
    d.text((PAD, y + 6), f"Regular Amazon prices captured {_captured(rows)}. Prices change.",
           font=font(400, 24), fill=MUTED)
    footer(d, "Full price-to-beat list")
    when = "; ".join(f"{k['label']} is {_day(k['date'])}" for k in cfg["key_dates"])
    title = f"{deal} {cfg['year']} Tool Deals: Price Cheat Sheet"
    desc = (f"Is that {deal} tool deal real? Our top-ranked cordless drills, impact drivers, "
            f"saws, sanders and more with the regular price we recorded. Beat it or skip it. {when}.")
    kw = [f"{deal.lower()} tool deals", f"{deal.lower()} {cfg['year']}", "power tool deals",
          "tool sale", "gifts for dad"]
    return img, title, desc, f"{cfg['slug']}.html", kw


def pin_holiday_picks(site, rows, cfg):
    """Top-rated picks for a holiday page: the four highest-scoring Best Overall picks among
    the popular categories. No prices, so it stays accurate after the sale."""
    deal = cfg["deal_name"]
    picks = sorted(rows, key=lambda r: -r[1]["score"])[:4]
    img, d = canvas()
    y = header(d, f"{deal.upper()} {cfg['year']}", "Top-Rated Tools Worth Watching")
    product_rows(d, y, [(build.cat_name(c), OVERALL, o) for c, o in picks], H - 230)
    footer(d, f"See every {deal} pick")
    title = f"{deal} {cfg['year']}: Top-Rated Tools to Watch for Deals"
    desc = (f"The tools worth buying this {deal}, ranked from real Amazon ratings and reviews: "
            + "; ".join(f"{build.cat_name(c)}: {o['brand']} {o['model']}" for c, o in picks)
            + ". See Best Overall and Best Budget in every category, with the price to beat.")
    kw = [f"{deal.lower()} tool deals", f"best tools {cfg['year']}", "power tools",
          "gifts for dad", "diy tools"]
    return img, title, desc, f"{cfg['slug']}.html", kw


def holiday_pins(site, cats, today=None):
    """[(id, board, publish datetime, hide date, pin)] for every holiday page whose link
    window hasn't closed. The cheat sheet posts the morning the page goes live (link_from,
    14:00 UTC), the picks pin that evening (22:00 UTC)."""
    today = today or datetime.date.today()
    rows = [(cat, o) for _g, cat, o, _b in cats if cat["slug"] in POPULAR]
    rows.sort(key=lambda r: POPULAR.index(r[0]["slug"]))
    out = []
    for cfg in build.holiday_configs():
        until = datetime.date.fromisoformat(cfg["link_until"]) if cfg.get("link_until") else None
        if until and until <= today:
            continue
        start = datetime.date.fromisoformat(cfg["link_from"])
        for kind, fn, hour in (("cheatsheet", pin_holiday_cheatsheet, 14), ("picks", pin_holiday_picks, 22)):
            out.append((f"holiday-{cfg['slug']}-{kind}", BOARDS["gifts"],
                        datetime.datetime.combine(start, datetime.time(hour)), cfg.get("link_until") or "",
                        fn(site, rows, cfg)))
    return out


# ------------------------------------------------------------------------ driver
def collect():
    site = build.load("site.json")
    year = str(site["updated"])[:4]
    by_group = {}
    cats = []
    for c in site["categories"]:
        cat = build.load(f"{c['slug']}.json")
        ranked, overall, budget, _premium = build.rank_products(cat)
        cats.append((c.get("power"), cat, overall, budget))
        by_group.setdefault(c.get("power"), []).append((cat, overall, budget))
    return site, year, cats, by_group


def all_pins(site, year, cats, by_group):
    """[(id, board, (img, title, desc, path, kw))] in posting order: gifts first (the season
    is now), then top-3 and avoid pins interleaved. Holiday deal pins are separate
    (holiday_pins, --holidays) because they post on a fixed date."""
    pins = []
    for cfg in build.SEASONAL.get("gifts", []):
        if not cfg.get("enabled") or cfg.get("kind") == "premium":  # price-band gift pins only
            continue
        for group in GROUP_NOUN:
            picks = [(cat, build.gift_pick(cat, cfg["min_price"], cfg["max_price"]))
                     for cat, _o, _b in by_group.get(group, [])]
            picks = sorted([(c, p) for c, p in picks if p], key=lambda cp: -cp[1]["score"])
            if len(picks) >= 2:
                pins.append((f"gifts-{cfg['max_price']}-{group}", BOARDS["gifts"],
                             pin_gifts(site, group, picks, cfg)))
    top3 = [(f"top3-{cat['slug']}", BOARDS[g], pin_top3(site, cat, o, b, year)) for g, cat, o, b in cats]
    avoid = [(f"avoid-{cat['slug']}", BOARDS[g], pin_avoid(site, cat, o, b, year))
             for g, cat, o, b in cats if cat.get("avoid")]
    for i in range(max(len(top3), len(avoid))):
        pins += top3[i:i + 1] + avoid[i:i + 1]
    return pins


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=str(datetime.date.today() + datetime.timedelta(days=1)))
    ap.add_argument("--per-day", type=int, default=5)
    ap.add_argument("--only", choices=["sample"], help="write one pin of each format, no CSV")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--new-only", action="store_true",
                    help="skip pins whose PNG already exists (they were posted in an earlier batch)")
    ap.add_argument("--holidays", action="store_true",
                    help="only the holiday deal pins: rewrite their PNGs and merge them into "
                         "marketing/pins/holiday-queue.csv with fixed publish dates (topup.py posts "
                         "them on the day each page goes live)")
    ap.add_argument("--max-rows", type=int, default=90,
                    help="rows per CSV; Pinterest caps scheduled pins at 100 per account")
    args = ap.parse_args()
    site, year, cats, by_group = collect()
    if args.holidays:
        return write_holidays(site, cats, Path(args.out))
    pins = all_pins(site, year, cats, by_group)
    if args.new_only:
        pins = [p for p in pins if not (Path(args.out) / f"{p[0]}.png").exists()]
    if args.only == "sample":
        want = ["gifts-50-wired", "top3-cordless-drills", "avoid-cordless-drills"]
        pins = [p for p in pins if p[0] in want]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    base = f"https://{site['custom_domain']}"
    rows = []
    start = datetime.date.fromisoformat(args.start)
    hours = [14, 16, 18, 20, 22, 23, 15, 17, 19, 21][:args.per_day]  # UTC = US daytime/evening
    for i, (pid, board, (img, title, desc, path, kw)) in enumerate(pins):
        # Flat colors: a 256-color palette is visually identical and ~60% smaller.
        img.quantize(256, dither=Image.Dither.NONE).save(out / f"{pid}.png", optimize=True)
        day, slot = divmod(i, args.per_day)
        when = datetime.datetime.combine(start + datetime.timedelta(days=day), datetime.time(hours[slot]))
        rows.append(pin_row(base, pid, board, when, (img, title, desc, path, kw)))
    print(f"wrote {len(pins)} pin(s) to {out}")
    if args.only != "sample":
        CSV_DIR.mkdir(parents=True, exist_ok=True)
        for n in range(0, len(rows), args.max_rows):
            part = rows[n:n + args.max_rows]
            path = CSV_DIR / f"batch-{part[0]['Publish date'][:10]}.csv"
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(part[0]))
                w.writeheader()
                w.writerows(part)
            print(f"wrote {path} ({len(part)} rows, {part[0]['Publish date']} .. {part[-1]['Publish date']})")


def pin_row(base, pid, board, when, pin):
    img, title, desc, path, kw = pin
    # Pinterest rejects two pins with the same link, so every pin gets its own utm_content.
    # The query goes before any #fragment.
    page_path, _, frag = path.partition("#")
    link = f"{base}/{page_path}?utm_source=pinterest&utm_medium=social&utm_content={pid}" + (f"#{frag}" if frag else "")
    return {"Title": title[:100], "Media URL": f"{base}/pins/{pid}.png", "Pinterest board": board,
            "Thumbnail": "", "Description": build.meta_desc(desc, 499), "Link": link,
            "Publish date": when.strftime("%Y-%m-%dT%H:%M:%S"), "Keywords": ", ".join(kw)}


def write_holidays(site, cats, out):
    """Holiday pins always get rewritten so their prices match the latest data. Rows already
    uploaded (holiday-sent.csv) are left alone; everything else in holiday-queue.csv is
    replaced. 'Hide date' is the page's link_until: topup.py drops a pin it can no longer
    post before then. It's stripped from the CSV Pinterest sees."""
    out.mkdir(parents=True, exist_ok=True)
    base = f"https://{site['custom_domain']}"
    qf, sf = CSV_DIR / "holiday-queue.csv", CSV_DIR / "holiday-sent.csv"
    sent = {r["Media URL"] for r in csv.DictReader(open(sf, encoding="utf-8"))} if sf.exists() else set()
    old = list(csv.DictReader(open(qf, encoding="utf-8"))) if qf.exists() else []
    rows, n = [], 0
    for pid, board, when, hide, pin in holiday_pins(site, cats):
        row = pin_row(base, pid, board, when, pin)
        if row["Media URL"] in sent:
            continue
        pin[0].quantize(256, dither=Image.Dither.NONE).save(out / f"{pid}.png", optimize=True)
        rows.append({**row, "Hide date": hide})
        n += 1
    keep = [r for r in old if r["Media URL"] not in {x["Media URL"] for x in rows}
            and r["Media URL"] not in sent and r.get("Hide date", "9999") > str(datetime.date.today())]
    rows = sorted(keep + rows, key=lambda r: r["Publish date"])
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    with qf.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["Title", "Media URL", "Pinterest board", "Thumbnail",
                           "Description", "Link", "Publish date", "Keywords", "Hide date"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {n} holiday pin(s) to {out}; {qf} now holds {len(rows)}")
    for r in rows:
        print(f"  {r['Publish date']}  {r['Media URL'].rsplit('/', 1)[-1]}")


if __name__ == "__main__":
    main()
