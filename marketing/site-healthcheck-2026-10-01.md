# ToolboxTop10 site health check, 2026-10-01

Sources: Search Console API (search analytics, sitemaps, URL Inspection on all 64 sitemap URLs), a live crawl of toolboxtop10.com (68 URLs), and the built HTML in `docs/`. PageSpeed Insights could not run (the API's free daily quota was used up), so Core Web Vitals are not measured here. Re-run with `python marketing\gsc\healthcheck.py`; raw output is in `marketing\gsc\data\` (git-excluded).

## Summary

The technical basics are clean. Every sitemap URL returns 200, canonicals are correct and self-referencing, http and www both 301 to `https://toolboxtop10.com/`, robots.txt allows everything, there are no noindex tags, every affiliate link carries `rel="sponsored nofollow"`, and all JSON-LD parses. Search Console reports zero sitemap errors and zero warnings.

The problems are indexing and traffic, not breakage. 36 of 64 sitemap URLs are indexed (up from 26 on 2026-09-28). The 28 that aren't are mostly the thin "overall vs budget" compare pages and the gift/deal pages, which Google is choosing to skip. Ten clicks in 90 days.

## Indexing (URL Inspection, 64 sitemap URLs)

| State | 2026-09-28 | 2026-10-01 |
|---|---|---|
| Submitted and indexed | 26 | 36 |
| Discovered, not indexed | 18 | 14 |
| Crawled, not indexed | 6 | 7 |
| Unknown to Google | 12 | 7 |

Ten pages moved into the index in three days, including corded-impact-wrenches, screwdrivers, allen-keys, needle-nose-pliers, cordless-impact-wrenches, corded-heat-guns, both rotary hammer pages, and corded-miter-saws. Every category page is now indexed except three:

- **corded-table-saws**: crawled 2026-09-29, not indexed. Google fetched it and declined.
- **cordless-miter-saws** and **corded-shop-vacuums**: unknown to Google. Both were added 2026-09-29/30, so this is expected, but request indexing.

Not indexed by page type:

- **Compare pages (`*-overall-vs-budget.html`)**: 0 of 21 indexed. 19 have never been crawled. portable-tool-boxes-overall-vs-budget was crawled and rejected. These pages are about 700 words, mostly drawn from the parent category page, and get 1 to 9 internal links each (the weakest-linked pages on the site).
- **Gift and deal pages**: tool-gifts-under-50, tool-gifts-under-100, money-no-object-tool-gifts, black-friday-tool-deals and best-craftsman-tools were all crawled and rejected. The other three brand pages (DEWALT, Milwaukee, Makita) are indexed.

## Issues found, in priority order

1. **The sitemap in Search Console is stale.** Google last downloaded it on 2026-09-24 and counts 50 submitted URLs; the live sitemap has 64. It was last submitted 2026-08-11. The service account is read-only, so Adam has to resubmit it in Search Console (Sitemaps > sitemap.xml > resubmit).
2. **The old `impact-drivers.html` is still indexed and still getting impressions** (529 impressions at position 2.1 in the last 90 days). Google last crawled it on 2026-08-10, before the redirect stub went live on 2026-09-28, so it hasn't seen the redirect yet. Request indexing on this URL in Search Console so Google picks up the redirect and moves those impressions to cordless-impact-drivers.
3. **cordless-circular-saws was last crawled 2026-08-12.** Google recorded no canonical for it (the canonical tag was added later). It's indexed but stale; request indexing to refresh it.
4. **Compare pages are dead weight for search.** 21 pages, none indexed, 19 never crawled. Options: (a) noindex them and drop them from the sitemap, keeping them as on-site navigation; (b) make each one worth indexing (unique copy, specs head-to-head, more internal links); or (c) leave them alone. Recommend (a) for now. Google's crawl budget on a two-month-old domain is small, and 21 pages it won't index dilute the sitemap.
5. **Gift and deal pages are rejected.** Same call: noindex until Black Friday content is real, or rewrite them with original content. black-friday-tool-deals will matter in November, so that one deserves a rewrite before then rather than a noindex.
6. **Compare page titles are too long.** All 21 run 80 to 121 characters (Google shows roughly 60). Example: "Milwaukee 48-22-8426 vs Goplus 5-Drawer Tool Chest: Best Overall vs Best Budget Rolling Tool Chests & Cabinets (2026)". Brand pages and a few others run 71 to 89. Only matters if the compare pages stay indexable.
7. **Logo weight.** The logo was a 182 KB PNG above the fold on every page. (Correction: product images have no width/height attributes, but the CSS gives every one a fixed size, so they don't cause layout shift. Only the logo needed sizing.)
8. **og:image is the logo on every page.** Social shares and Pinterest pins all show the same picture. Use the Best Overall product image per category page.
9. **No Product or Review rich results.** Search Console only detects Breadcrumbs (33 pages). The ItemList and FAQPage markup parse fine, but Google doesn't show FAQ rich results for commercial sites anymore and ItemList alone doesn't earn a snippet. Don't add Product/AggregateRating markup using Amazon's star ratings: Google's review-snippet rules require the reviews to be your own.

## Not issues

- **Mobile usability "VERDICT_UNSPECIFIED"** on every URL: Google retired the mobile usability report in late 2023; the API field is just empty.
- **The sitemap "indexed: 0"** count: Search Console no longer fills that field in the API.
- **Positions 1 to 2 with zero clicks** ("impact driver" 191 impressions at 1.8, "dewalt drill", "tool chest", "tool cart"): these come from image or product grid placements, not blue-link rankings. Real organic positions are 10 to 50.

## Traffic (last 90 days)

7,151 impressions, 10 clicks. Impressions run 1,100 to 1,500 a week since late August with no clear trend. Average position improved from about 20 in mid-September to 8 to 10 in late September, then slipped to 15.7 on 2026-09-30. One day isn't a trend.

Top pages by impressions: corded-drills (1,754, 3 clicks, position 14.4), cordless-impact-drivers (1,143, 0 clicks, 13.1), rolling-tool-chests (1,044, 1 click), cordless-oscillating-tools (802, position 19.9), cordless-drills (670, 11.4), cordless-circular-saws (589, 14.9).

Real organic rankings sit on pages 2 to 5: "corded drills" 31.6, "corded oscillating tools" 34.9, "corded hammer drills" 39.6, "best cordless circular saw" 40.5. Only one query with 20+ impressions sits at positions 8 to 20: "dewalt corded drill" (43 impressions, 8.3).

## Compliance risks to check (not SEO)

- **Amazon prices and images.** The pages show prices captured days ago and hotlink Amazon product images. Amazon's Associates terms restrict how product content (prices, images) may be sourced and how fresh prices must be. The pages already date-stamp the price, but read the current Operating Agreement and Program Policies to confirm the setup is allowed. If it isn't, the fix is to drop exact prices or move to Amazon's product API once the account qualifies.

## Actions

Adam (in Search Console, about 10 minutes):

1. Resubmit `sitemap.xml`.
2. Request indexing for impact-drivers.html, cordless-circular-saws.html, corded-table-saws.html, cordless-miter-saws.html and corded-shop-vacuums.html.

Claude (code changes, each needs Adam's go before pushing):

3. Noindex the compare pages and remove them from the sitemap (or decide to rebuild them).
4. Noindex the gift pages and best-craftsman-tools; rewrite black-friday-tool-deals before November.
5. Add width/height to images, convert the logo to a small WebP, and set a per-page og:image.
6. Re-run this check in about two weeks and compare against `marketing\gsc\data\inspection.json`.

## Done 2026-10-01 (commit 21bfafa, live)

Compare pages, the three gift guides and best-craftsman-tools are now `noindex, follow` and out of the sitemap (64 -> 40 URLs), each controlled by a `noindex` flag in compare.json / seasonal.json / brands.json. Category, compare, gift and brand pages use their top pick's image for og:image. The header logo is a 13 KB WebP with width/height. Black Friday stays indexed and still needs its rewrite before November.
