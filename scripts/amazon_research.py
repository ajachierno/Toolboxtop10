"""Research helper for replacing products: Amazon search results and listing details.

    python scripts/amazon_research.py search "cordless drill" [pages]
    python scripts/amazon_research.py detail B00ET5VMTU [B0... ...]

search: organic results in page order (sponsored rows marked), with price, rating,
review count and the "bought in past month" line.
detail: title, main image URL, brand/byline, price, rating, reviews, buy-box state,
feature bullets and every spec-table row on the listing.
Output is JSON on stdout. Uses a visible Chrome window (headless gets a CAPTCHA).
"""
import asyncio
import json
import sys
import urllib.parse

from playwright.async_api import async_playwright

SEARCH_JS = r"""()=>[...document.querySelectorAll('div[data-component-type="s-search-result"]')].map((e,i)=>{
const t=s=>{const x=e.querySelector(s);return x?x.textContent.trim().replace(/\s+/g,' '):null};
return {pos:i+1,asin:e.dataset.asin,title:t('h2'),
sponsored:!!e.querySelector('.puis-sponsored-label-text, [aria-label="View Sponsored information or leave ad feedback"]'),
price:t('.a-price .a-offscreen'),rating:t('.a-icon-alt'),
reviews:(e.querySelector('a[href*="#customerReviews"] span, [data-csa-c-content-id*="ratings-count"]')||{}).textContent||null,
bought:t('.a-row.a-size-base .a-color-secondary')}})"""

DETAIL_JS = r"""()=>{const t=s=>{const e=document.querySelector(s);return e?e.textContent.trim().replace(/\s+/g,' '):null};
const img=document.querySelector('#landingImage');
const rows={};document.querySelectorAll('#productDetails_techSpec_section_1 tr, #productDetails_detailBullets_sections1 tr, #productOverview_feature_div tr, #poExpander tr, #tech table tr, #productDetails_db_sections tr, table.a-keyvalue tr').forEach(r=>{
const c=r.querySelectorAll('th,td');if(c.length>=2)rows[c[0].textContent.trim().replace(/\s+/g,' ')]=c[c.length-1].textContent.trim().replace(/\s+/g,' ')});
return {title:t('#productTitle'),byline:t('#bylineInfo'),
image:img?(img.getAttribute('data-old-hires')||img.getAttribute('src')):null,
price:t('#corePrice_feature_div .a-offscreen')||t('#corePriceDisplay_desktop_feature_div .a-offscreen')||t('#apex_desktop .a-offscreen'),
rating:t('#acrPopover .a-icon-alt'),reviews:t('#acrCustomerReviewText'),
bought:t('#social-proofing-faceout-title-tk_bought'),
avail:(t('#availability span')||'').split('.')[0],buybox:!!document.querySelector('#add-to-cart-button'),
bestseller_rank:(Object.entries(rows).find(([k])=>/Best Sellers Rank/i.test(k))||[])[1]||null,
bullets:[...document.querySelectorAll('#feature-bullets li span.a-list-item')].map(e=>e.textContent.trim()).filter(Boolean),
specs:rows,in_box:[...document.querySelectorAll('#whatsInTheBoxDeck li, #witb-content-list li')].map(e=>e.textContent.trim().replace(/\s+/g,' ')),
details:(document.querySelector('#detailBullets_feature_div')||{}).innerText||null,
text:document.body.innerText,
captcha:!!document.querySelector('form[action*="validateCaptcha"]')}}"""


async def goto(pg, url, js):
    await pg.goto(url, wait_until="domcontentloaded", timeout=60000)
    if await pg.locator('form[action*="validateCaptcha"]').count():
        await pg.locator("button[type=submit], input[type=submit]").first.click()
        await pg.wait_for_load_state("domcontentloaded")
        await pg.goto(url, wait_until="domcontentloaded", timeout=60000)
    await pg.wait_for_timeout(1500)
    return await pg.evaluate(js)


async def main(mode, args):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, channel="chrome",
                                          args=["--disable-blink-features=AutomationControlled"])
        pg = await browser.new_page()
        out = {}
        if mode == "search":
            q, pages = args[0], int(args[1]) if len(args) > 1 else 2
            rows = []
            # A cold /s?k= URL gets "Something went wrong"; searching from the home page works.
            await goto(pg, "https://www.amazon.com/", "()=>document.title")
            await pg.fill("#twotabsearchtextbox", q)
            await pg.keyboard.press("Enter")
            await pg.wait_for_load_state("domcontentloaded")
            for n in range(1, pages + 1):
                if n > 1:
                    nxt = pg.locator("a.s-pagination-next")
                    if not await nxt.count():
                        break
                    await nxt.first.click()
                    await pg.wait_for_load_state("domcontentloaded")
                await pg.wait_for_timeout(2000)
                for r in await pg.evaluate(SEARCH_JS):
                    r["page"] = n
                    rows.append(r)
            out = rows
        else:
            for asin in args:
                await goto(pg, f"https://www.amazon.com/dp/{asin}", "()=>1")
                # Expand "See more product details" style sections before reading.
                await pg.mouse.wheel(0, 6000)
                await pg.wait_for_timeout(2500)
                out[asin] = await pg.evaluate(DETAIL_JS)
        await browser.close()
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2:]))
