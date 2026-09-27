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
    "gifts": "Tool Gift Ideas (Holiday 2026)",
}
GROUP_NOUN = {"wireless": "Cordless Tool", "wired": "Corded Tool", "hand": "Hand Tool", "storage": "Tool Storage"}


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
            + ". Ready to use out of the box.")
    kw = [f"tool gifts {band.lower()}", "gifts for dad", "gifts for him", "diy gift ideas",
          "christmas gifts for men", f"{noun.lower()} gifts"]
    return img, title, desc, f"{cfg['slug']}.html", kw


def pin_black_friday(site, rows, cfg):
    img, d = canvas()
    y = header(d, "BLACK FRIDAY · NOV 27, 2026", "Tool Price Cheat Sheet")
    d.text((PAD, y), "Our #1 pick — and its regular price. Beat it or skip it.",
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
    d.text((PAD, y + 6), "Regular Amazon prices captured Sept 2026. Prices change.",
           font=font(400, 24), fill=MUTED)
    footer(d, "Full price-to-beat list")
    title = "Black Friday 2026 Tool Deals: Price Cheat Sheet"
    desc = ("Is that Black Friday tool deal real? Our top-ranked cordless drills, impact drivers, "
            "saws, sanders and more with the regular price we recorded — beat it or skip it. "
            "Black Friday is Nov 27, 2026; Cyber Monday is Nov 30.")
    kw = ["black friday tool deals", "black friday 2026", "cyber monday tool deals",
          "power tool deals", "gifts for dad"]
    return img, title, desc, f"{cfg['slug']}.html", kw


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
    """[(id, board, (img, title, desc, path, kw))] in posting order: gifts and
    Black Friday first (the season is now), then top-3 and avoid pins interleaved."""
    pins = []
    for cfg in build.SEASONAL.get("gifts", []):
        if not cfg.get("enabled"):
            continue
        for group in ("wireless", "wired", "hand", "storage"):
            picks = [(cat, build.gift_pick(cat, cfg["min_price"], cfg["max_price"]))
                     for cat, _o, _b in by_group.get(group, [])]
            picks = sorted([(c, p) for c, p in picks if p], key=lambda cp: -cp[1]["score"])
            if len(picks) >= 2:
                pins.append((f"gifts-{cfg['max_price']}-{group}", BOARDS["gifts"],
                             pin_gifts(site, group, picks, cfg)))
    bf = build.SEASONAL.get("black_friday")
    if bf and bf.get("enabled"):
        popular = ["cordless-drills", "cordless-impact-drivers", "cordless-circular-saws",
                   "cordless-reciprocating-saws", "cordless-oscillating-tools",
                   "cordless-random-orbital-sanders", "cordless-impact-wrenches",
                   "socket-sets", "rolling-tool-chests", "cordless-angle-grinders"]
        rows = [(cat, o) for g, cat, o, _b in cats if cat["slug"] in popular]
        rows.sort(key=lambda r: popular.index(r[0]["slug"]))
        pins.append(("black-friday-cheat-sheet", BOARDS["gifts"], pin_black_friday(site, rows, bf)))
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
    args = ap.parse_args()
    site, year, cats, by_group = collect()
    pins = all_pins(site, year, cats, by_group)
    if args.only == "sample":
        want = ["gifts-50-wired", "black-friday-cheat-sheet", "top3-cordless-drills", "avoid-cordless-drills"]
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
        rows.append({"Title": title[:100], "Media URL": f"{base}/pins/{pid}.png", "Pinterest board": board,
                     "Thumbnail": "", "Description": build.meta_desc(desc, 499), "Link": f"{base}/{path}",
                     "Publish date": when.strftime("%Y-%m-%dT%H:%M:%S"), "Keywords": ", ".join(kw)})
    print(f"wrote {len(pins)} pin(s) to {out}")
    if args.only != "sample":
        CSV_DIR.mkdir(parents=True, exist_ok=True)
        path = CSV_DIR / f"batch-{args.start}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {path} ({len(rows)} rows, {rows[0]['Publish date']} .. {rows[-1]['Publish date']})")


if __name__ == "__main__":
    main()
