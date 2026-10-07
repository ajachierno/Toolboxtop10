# ToolboxTop10 search ranking plan

_Written 2026-09-28. Goal: move toolboxtop10.com up in Google and Bing organic results._
_Companion to `marketing-plan.md` (2026-09-24), which covers traffic from all channels. This one is only about search position._

## Where the site stands today

Checked against the repo and the built `docs/` folder on 2026-09-28.

What's already in place:

- 33 category pages plus 20 "Overall vs Budget" pages, 4 brand pages, 3 gift pages and a Black Friday page. 62 URLs in the sitemap.
- Canonical tags, robots meta, Open Graph, and JSON-LD (BreadcrumbList, ItemList, FAQPage) on every page.
- IndexNow key hosted and a ping script (`scripts/indexnow_ping.py`), so Bing and Yandex hear about changes quickly.
- Cloudflare Web Analytics running. Pinterest domain claimed. Mobile layout live since 2026-09-26.
- Prices and rankings refreshed on a daily rotation, with a visible "data captured" date.

What's missing or weak:

1. ~~No Google Search Console.~~ Corrected 2026-09-28: Search Console is verified on the domain property by DNS, which is why the HTML tag is blank. See "Search Console findings" below.
2. The domain is 7 weeks old (first commit 2026-08-09). New domains usually take months to rank for anything competitive. This sets the timeline for everything below.
3. The content is built from Amazon data only. Google's reviews guidance asks for evidence of first-hand use (original photos, measurements, test results) and penalizes pages that summarize what's already on the retailer. Right now the site has no first-hand evidence on any page. This is the single biggest ranking risk.
4. No About, methodology, or contact page. Nothing tells Google or a reader who ranks these tools or how.
5. Weak internal linking. Corded and cordless versions of the same tool don't link to each other (checked `corded-jigsaws.html`: no link to `cordless-jigsaws.html`). No "related tools" block.
6. 13 categories have no Overall vs Budget page yet, including the 6 newest (heat guns, both rotary hammer pages, table saws, miter saws, tool bags).
7. Every page uses the site logo as its share image. Minor for rankings, noticeable for click-through from social and Discover.

## Search Console findings (2026-09-28)

Pulled through the API (`marketing/gsc/gsc_pull.py`, service account `gsc-reader`, restricted access). Search Console turned out to be set up already on the domain property, so point 1 above is wrong.

- 6,490 impressions and 8 clicks since 2026-08-09, almost all US. 1,444 distinct queries.
- Only 26 of the 62 sitemap URLs are indexed. 18 are "Discovered, currently not indexed" (Google knows about them and hasn't bothered to crawl them), 12 are unknown to Google, and 6 are "Crawled, currently not indexed" (Google read them and chose not to index them).
- Category pages not indexed: corded-impact-wrenches, corded-reciprocating-saws, screwdrivers, allen-keys, needle-nose-pliers (discovered), plus the six newest pages (unknown).
- Only 2 of the 20 Overall vs Budget pages are indexed.
- Crawled but rejected: tool-gifts-under-50, tool-gifts-under-100, money-no-object-tool-gifts, black-friday-tool-deals, best-craftsman-tools, portable-tool-boxes-overall-vs-budget. These pages re-list picks that already appear on the category pages. Google appears to see them as duplicates.
- Queries showing position 1 to 2 with no clicks (for example "impact driver", 191 impressions at 1.8) are almost certainly a SERP feature showing many sites, not a normal organic listing. Real organic positions are on pages 3 to 5: "corded drills" 32, "corded oscillating tools" 36, "best cordless circular saw" 41, "cordless impact drivers" 52.
- Closest to page 1: "dewalt drill" 4.4 and "dewalt corded drill" 8.5, both on corded-drills.html.
- `impact-drivers.html` (the old URL, renamed to cordless-impact-drivers.html) is still indexed and ranking, but the live URL returns a 404. The two URLs split the signals for the same queries.

### What this changes in the plan

1. Stop adding thin pages for now. Google is already declining to crawl or index a third of the site, so another 100 generated pages would make it worse. Hold new Overall vs Budget batches and new gift or brand pages until the current ones are indexed. The daily add-category job can keep going, since category pages are the ones being indexed, but a slower pace (every 2 to 3 days) gives Google time to catch up.
2. Redirect `impact-drivers.html` to `cordless-impact-drivers.html`. GitHub Pages has no server redirects, so this is a stub page with a canonical link and an instant meta refresh, which Google treats as a redirect.
3. Link the unindexed category pages from the indexed pages that get impressions (home, corded-drills, cordless-impact-drivers, rolling-tool-chests). "Discovered, not indexed" on a new site usually means Google doesn't see the pages as important yet, and internal links from pages it already values are the free fix.
4. Adam requests indexing by hand in Search Console (URL Inspection, then Request indexing) for the 11 unindexed category pages. The API can't do this, and Google limits it to a handful a day.
5. Either make the gift, Black Friday and brand pages add something the category pages don't (price history, a "why this one for a gift" angle, a buying calendar) or noindex them until they do. The Black Friday page should get fixed rather than hidden because its search season is November.
6. Push corded-drills.html first. It gets the most impressions (1,671) and has the two queries closest to page 1.

## Where it can realistically rank

Head terms like "best cordless drill" are held by Wirecutter, Popular Mechanics, Pro Tool Reviews and similar sites with years of links and hands-on testing. A 7-week-old site won't displace them in 2026. Don't aim there first.

The winnable queries are specific and low-competition:

- Model-vs-model: "DEWALT DWS780 vs Metabo HPT C10FCG2"
- Price-capped: "best corded rotary hammer under 100"
- Intent questions: "what size miter saw do I need", "corded vs cordless jigsaw"
- Avoid-style: "is [brand] [model] any good"

Each of these is small on its own. Ranking for a few hundred of them builds the site's overall standing, which is what eventually lets the category pages compete for the bigger terms.

## The three plans

| | Free | $50/month | Best value (~$20/month) |
|---|---|---|---|
| Monthly cost | $0 | $50 | About $20 |
| What the money buys | Nothing | About $35 of tools to test hands-on (one budget power tool every other month, or two hand tools a month) plus about $15 of keyword and SERP data credits | One hand tool a month, bought to test and photograph |
| Technical fixes (Search Console, internal links, trust pages, missing comparison pages) | Yes | Yes | Yes |
| Long-tail page engine (vs pages, price-capped pages, question guides) | Yes, targeted from Search Console queries once they appear (4 to 8 weeks) | Yes, targeted from keyword data from week 1 | Yes, targeted from Search Console queries |
| First-hand evidence on pages | Only tools Adam already owns | 1 to 2 tested products a month | 1 tested product a month |
| Link building | Adam, personally, about 1 hour a week | Same | Same |
| Rank tracking | Search Console (free, 2 to 3 day lag) | Search Console plus daily SERP checks on the top 50 target queries | Search Console |
| Adam's time | 1 to 2 hours a week | 2 to 3 hours a week (testing takes time) | 1.5 to 2.5 hours a week |
| Claude's part | All technical and content work, weekly Search Console review | Same, plus keyword research and SERP monitoring | Same as Free, plus writing up each test |
| Main risk | Pages look like every other Amazon roundup, so rankings stall after the easy long-tail wins | Keyword data is nice but mostly duplicates what Search Console gives for free once traffic starts | Slower build-up of tested products than $50 |
| Expected result (estimate, not a promise) | Long-tail impressions in 1 to 2 months, first page-1 positions on vs and price-capped queries in 3 to 6 months, then a plateau | Same curve, reached a few weeks sooner, with a higher ceiling | Close to the $50 ceiling at 40% of the cost |

The timing estimates are my judgment based on typical new-domain behavior. There's no baseline to project from until Search Console is running.

## Free plan

### Week 1: fix the foundations

Adam (about 20 minutes):

1. Add toolboxtop10.com to Google Search Console. The domain property (DNS TXT record at the registrar) is the better option because it covers every URL variant. If that's a hassle, use the URL-prefix property with the HTML tag and paste the value into `google_site_verification` in `data/tracking.json`.
2. Import the site into Bing Webmaster Tools from Search Console (one click).
3. Give Claude read access to Search Console so the weekly review can run unattended: create a Google Cloud service account, then add its email as a restricted user on the property. Claude can walk through this.
4. Sign up for Ahrefs Webmaster Tools (free for verified sites). It reports backlinks and technical issues that Search Console doesn't.

Claude:

1. Submit the sitemap in both consoles and run IndexNow for every URL.
2. Add the 13 missing categories to `data/compare.json` so every category has an Overall vs Budget page.
3. Cross-link every corded and cordless pair, and add a "Related tools" block to each category page (same tool family, then same power group).
4. Build an About page, a methodology page ("How we rank"), and a contact page. The methodology page explains the scoring weights and the avoid-pick rule, using the real weights from each category's JSON. Adam decides whether the About page uses his name. A named person behind the rankings helps with Google's trust signals, but it's his call.
5. Make the "(2026)" in page titles follow the current year automatically, so January doesn't leave stale titles.
6. Generate a 1200x630 share image per page (title plus the #1 pick) to replace the logo.

### Weeks 2 to 8: the long-tail engine

Claude builds pages in weekly batches, each added to the sitemap and pinged through IndexNow:

- Best Overall vs Money No Object pages for categories where both exist.
- "Best [tool] under $X" pages, only where at least 3 ranked products qualify.
- "Corded vs cordless [tool]" guides for each of the 9 pairs, linking both category pages.
- Question guides that answer one real question in the first paragraph and link to the category page ("What size miter saw do I need", "SDS-Plus vs SDS-Max").
- A "Tools to avoid" hub collecting all 33 avoid picks with their reasons. Nobody else publishes this, which makes it the page most likely to earn links.

Batches stay small (10 to 15 pages a week) and each page has to answer something the category page doesn't. Mass-producing near-duplicate pages is exactly what Google's spam policies call scaled content abuse.

### First-hand evidence, free version

Adam photographs any tool he already owns that appears on the site: in hand, in use, the result of a cut or drill. Claude adds a short "We own this one" note to that product with the photos. Even five products with real photos separate the site from pure Amazon roundups.

### Links (Adam, about 1 hour a week)

Links can't be automated honestly, and bot posting gets domains banned on Reddit. What works for a small site:

- Answer tool questions on r/Tools, r/DIY and r/HomeImprovement as yourself. Link only when the page answers the question better than a comment could, and follow each subreddit's self-promotion rules.
- Reply to journalist requests on quote platforms such as Qwoted and Featured.com (check they're still running and still free). Tool and home-improvement writers ask for quotes regularly.
- Share the avoid hub and any hands-on tests on woodworking and garage forums where members already post tool comparisons.
- Never buy links, swap links in bulk, or use link networks. One manual penalty would set a new domain back months.

### Every week after week 8

Claude pulls the last 28 days from Search Console and acts on it:

- Pages with impressions but a click rate under 2%: rewrite the title and meta description, then check again in 3 weeks.
- Queries sitting in positions 8 to 20: strengthen the matching page (FAQ entry, internal links from 2 or 3 related pages, a comparison page if the query names two models).
- Queries the site ranks for with no dedicated page: build one if it's worth a page.
- Pages reported as "Crawled, currently not indexed" after 60 days: improve them or merge them into a stronger page.
- Send Adam a short weekly report: impressions, clicks, average position, pages that moved, what changed.

## $50/month plan

Everything in Free, plus:

- About $35 a month on test tools. Buy the budget pick or the avoid pick where possible, since those are the claims readers are most suspicious of. Claude writes a test plan per tool before it's bought (for example: tape measure accuracy against a steel rule at 10 and 25 feet, jigsaw cut squareness on 2x4). Adam runs it and photographs it. Claude writes it up and puts the photos and measured results on the category page. Tools can be kept, given away, or sold afterward. Don't buy tools to test and then return them.
- About $15 a month of prepaid keyword and SERP data from a pay-as-you-go API such as DataForSEO (check the current minimum top-up before committing). Claude uses it in month 1 to size every "best [tool]" query and a few hundred vs and price-capped variants, then checks the top 50 target queries weekly for pages where forums, Reddit or Amazon sit in the top 5. Those are the winnable spots, and they get built first.

## Best value plan (~$20/month)

Everything in Free, plus one hand tool a month (tape measures, pliers, screwdrivers, hammers and allen keys all sit around $15 to $25) bought, tested and photographed the same way as in the $50 plan.

This is the plan I'd pick. The site's main weakness is that it has no first-hand evidence, and money is the only way to fix that for tools Adam doesn't already own. The first $20 buys exactly that. The extra $30 in the $50 plan mostly buys keyword data, and Search Console will supply most of the same information for free once impressions start coming in. More tested tools help, but the jump from zero tested products to twelve a year matters much more than the jump from twelve to twenty.

Move up to $50 later if Search Console shows the tested pages pulling ahead of the untested ones.

## First 90 days

| When | Adam | Claude |
|---|---|---|
| Week 1 | Search Console, Bing, service account, Ahrefs Webmaster Tools (about 20 min). Pick the plan. | Sitemap, IndexNow, 13 comparison pages, internal links, trust pages, share images, title year fix |
| Weeks 2 to 4 | Photograph owned tools. Start the weekly hour of link work. Buy the first test tool (paid plans). | Corded vs cordless guides, avoid hub, first question guides. Test plan for the first tool. |
| Weeks 5 to 8 | Run and photograph the first test. Keep up link work. | Write up the test. Price-capped pages. First Search Console read if data is in. |
| Weeks 9 to 13 | Second test. Link work. | Weekly Search Console loop starts: title rewrites, position 8 to 20 pushes, new pages from real queries. Month-3 report comparing tested vs untested pages. |

## How this fits with the daily category jobs

The scheduled add-category and refresh runs keep adding and updating `data/<slug>.json`. This plan doesn't edit those files. It changes `build.py` (links, trust pages, share images, title year), `data/compare.json`, `data/tracking.json`, and adds new page types. The `build.py` changes go in first so the daily jobs pick them up automatically.

## Decisions for Adam

1. Which plan: Free, $50, or best value at about $20.
2. Does the About page use your name, or stay as "the ToolboxTop10 team"?
3. Which listed tools do you already own and can photograph?
4. Push straight to `main` like the daily jobs, or PRs for the `build.py` changes?
