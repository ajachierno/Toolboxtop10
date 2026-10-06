"""Capture live price, rating, review count, monthly sales and availability for every
product and avoid pick on the site (or a given list of category slugs).

Runs a visible Chrome window through Playwright, because Amazon blocks headless
browsers. Results go to scrape-results/<YYYY-MM-DD>.json (git-ignored). The file is
saved after every listing, so an interrupted run resumes where it stopped.

    python scripts/scrape_amazon.py                 # every category
    python scripts/scrape_amazon.py cordless-drills # just these slugs

Apply the results with scripts/apply_scrape.py.
"""
import asyncio
import datetime
import json
import random
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT_DIR = ROOT / "scrape-results"
TABS = 2
PER_RUN = 40

JS = r"""()=>{const t=s=>{const e=document.querySelector(s);return e?e.textContent.trim().replace(/\s+/g,' '):null};
return {title:t('#productTitle'),
price:t('#corePrice_feature_div .a-offscreen')||t('#corePriceDisplay_desktop_feature_div .a-offscreen')||t('#apex_desktop .a-offscreen')||t('#apex-pricetopay-accessibility-label')||t('#tp_price_block_total_price_ww .a-offscreen'),
rating:t('#acrPopover .a-icon-alt'),reviews:t('#acrCustomerReviewText'),
bought:t('#social-proofing-faceout-title-tk_bought'),
avail:(t('#availability span')||t('#outOfStock')||''),
buybox:!!document.querySelector('#add-to-cart-button'),
captcha:!!document.querySelector('form[action*="validateCaptcha"]'),
notfound:/Page Not Found/i.test(document.title)}}"""

AOD_JS = r"""()=>{const o=[...document.querySelectorAll('#aod-pinned-offer, #aod-offer')];
return o.map(e=>{const p=e.querySelector('.a-price .a-offscreen');return p?p.textContent.trim():null}).filter(Boolean)}"""


def targets(slugs):
    site = json.loads((DATA / "site.json").read_text(encoding="utf-8"))
    out = []
    for c in site["categories"]:
        if slugs and c["slug"] not in slugs:
            continue
        cat = json.loads((DATA / f"{c['slug']}.json").read_text(encoding="utf-8"))
        for p in cat["products"] + cat.get("avoid", []):
            out.append(p["asin"])
    return list(dict.fromkeys(out))


PRICE_SEL = ("#corePrice_feature_div .a-offscreen, #apex-pricetopay-accessibility-label, "
             "#tp_price_block_total_price_ww .a-offscreen, #outOfStock, #availability")


async def load(pg, url, js):
    await pg.goto(url, wait_until="domcontentloaded", timeout=60000)
    try:  # the price block is filled in by script after DOMContentLoaded
        await pg.wait_for_selector(PRICE_SEL, state="attached", timeout=8000)
    except Exception:
        pass
    r = await pg.evaluate(js)
    if isinstance(r, dict) and r.get("captcha"):
        btn = pg.locator("button[type=submit], input[type=submit]")
        if await btn.count():
            await btn.first.click()
            await pg.wait_for_load_state("domcontentloaded")
            await pg.goto(url, wait_until="domcontentloaded", timeout=60000)
            try:
                await pg.wait_for_selector(PRICE_SEL, state="attached", timeout=8000)
            except Exception:
                pass
            r = await pg.evaluate(js)
    if isinstance(r, dict) and r.get("buybox") and not r.get("price"):
        await pg.wait_for_timeout(3000)  # one more look before giving up
        r = await pg.evaluate(js)
    return r


async def main(slugs):
    OUT_DIR.mkdir(exist_ok=True)
    out_file = OUT_DIR / f"{datetime.date.today().isoformat()}.json"
    results = json.loads(out_file.read_text(encoding="utf-8")) if out_file.exists() else {}
    todo = [a for a in targets(slugs) if a not in results or results[a].get("error")
            or (results[a].get("buybox") and not results[a].get("price"))]
    print(f"{len(todo)} listings to capture -> {out_file}")
    # Amazon starts hiding prices after ~60 pages in one browser session, so each run
    # captures at most PER_RUN listings in a fresh browser. Re-run until nothing is left.
    todo = todo[:PER_RUN]
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, channel="chrome",
                                          args=["--disable-blink-features=AutomationControlled"])
        ctx = await browser.new_context()
        # Skip images, media and fonts: the page text is all we read.
        await ctx.route("**/*", lambda route: route.abort()
                        if route.request.resource_type in ("image", "media", "font") else route.continue_())
        queue = asyncio.Queue()
        for item in enumerate(todo, 1):
            queue.put_nowait(item)

        async def worker():
            pg = await ctx.new_page()
            while not queue.empty():
                i, asin = queue.get_nowait()
                await capture(pg, i, asin)

        async def capture(pg, i, asin):
            try:
                r = await load(pg, f"https://www.amazon.com/dp/{asin}", JS)
                if r.get("captcha"):
                    r["error"] = "captcha"
                elif not r["buybox"] and not r["notfound"]:
                    # No featured offer: record what the other sellers charge.
                    await pg.goto(f"https://www.amazon.com/dp/{asin}?aod=1", wait_until="domcontentloaded")
                    await pg.wait_for_timeout(2500)
                    r["other_offers"] = await pg.evaluate(AOD_JS)
            except Exception as e:  # keep going; the run can be resumed
                r = {"error": str(e)[:200]}
            r["captured"] = datetime.datetime.now().isoformat(timespec="seconds")
            results[asin] = r
            out_file.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"[{i}/{len(todo)}] {asin} {r.get('price')} {r.get('rating')} {r.get('reviews')} "
                  f"buybox={r.get('buybox')} {r.get('error', '')}", flush=True)
            await asyncio.sleep(random.uniform(1.0, 2.5))

        await asyncio.gather(*(worker() for _ in range(TABS)))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main(set(sys.argv[1:])))
