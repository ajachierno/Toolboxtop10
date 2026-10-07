# ToolboxTop10 competitor review (2026-10-06)

Ten tool review sites, what they do that ToolboxTop10 doesn't, and what's worth copying.

## Sites looked at

| Site | How I saw it | What stands out |
|---|---|---|
| Family Handyman | Full page (best cordless drills) | Named author with trade background, linked editorial-process page, picks split by skill level (DIY / intermediate / pro), Amazon + Home Depot + Lowe's + Walmart buttons on every product, FAQ |
| This Old House Reviews | Full page (best cordless drills) | 3 scored metrics out of 5 (ergonomics, power, runtime) averaged into a final score, written methodology, update date under the headline, contact email for feedback |
| TechGearLab | Full page (best drill) | Published metric weights (drilling 30%, driving 25%, ease of use 25%, weight 15%, battery 5%), per-metric scores, sortable table with award badges, named testers with credentials, price-vs-performance commentary |
| GarageWorld360 | Full page (impact driver vs drill) | Small affiliate site, closest peer. Buyer-persona picks (weekend DIYer / contractor / remodeler), "when to use X vs Y" decision guide, table of contents, links out to Consumer Reports and Wikipedia |
| Tools in Action | Home page | Newsletter signup, YouTube on every review, forum, buying-guide hub, Prime Day deal roundups |
| ToolGuyd | Home page | Daily deal posts by retailer, brand-platform guides ("best cordless power tool brand"), USA-made section, active comments, newsletter, footer disclosure page |
| Pro Tool Reviews | Search results (site returns 403 to my fetcher) | Published test protocols per tool type (timed screw driving on 4K video, spade-bit boring), head-to-head shootouts, runs its own awards program |
| Consumer Reports | Search results (paywalled) | Dyno lab tests, plus brand-level predicted reliability and owner satisfaction from member surveys |
| Torque Test Channel | Search results | Leaderboard of 275+ tested impacts with a pick-and-compare chart tool, updated weekly |
| Project Farm | Search results | Measured head-to-heads (cut time, torque to failure, ratchet back-drag) on cheap vs name-brand tools |

Wirecutter, Popular Mechanics, HGTV and The Spruce block my fetcher, and the Bob Vila and BestReviews URLs I tried were 404s, so they aren't counted.

## What ToolboxTop10 already does well

Several of these sites lack things ToolboxTop10 already has: a "Tools to avoid" section, a visible data-captured date, a full spec comparison table, a "How we rank" section, FAQ schema, twin corded/cordless links, and a price and rating refresh every day. The plain-data approach is fine. Where it falls short is trust signals and buyer guidance.

## Recommended improvements, in priority order

### 1. Show each product's score breakdown
TechGearLab and This Old House both show per-metric scores and how much each one counts. `score_product()` in build.py already computes rating, reviews and feature scores with the weights in each category JSON. Render them as a small bar or table on each card ("Rating 9.1 · Popularity 8.4 · Features 7.0"), plus the weights in "How we rank". All of it comes from data the site already has, so there's no accuracy risk. Effort: small, build.py only.

### 2. About page, named byline and contact address
Every editorial competitor puts a named person on the page and links an editorial-process page. This Old House also gives a feedback email. ToolboxTop10 has no author, no About page and no contact. This is also the first item on the Home Depot reapply plan. Add `about.html` (who runs the site, how picks are made, that nothing is hands-on tested yet, affiliate disclosure), a byline under each title, and a corrections email. Effort: small. Adam needs to write or approve the bio.

### 3. "Best for" and "Skip if" lines on every product
Family Handyman splits picks by skill level, and GarageWorld360 splits them by buyer type. ToolboxTop10 has pros and cons, but nothing that tells a reader which pick fits them. Add a one-line `best_for` and `skip_if` field to each product, plus a short "Pick by job" table at the top of the category ("Hanging shelves → X, Deck building → Y"). Effort: medium, because 33 categories need the copy. The refresh and add-category skills can fill it in going forward.

### 4. Pick by battery platform
ToolboxTop10 doesn't answer the most common question cordless buyers ask: "I already own DeWalt 20V batteries, which one should I get?" ToolGuyd builds whole guides around it. The data already has bare-tool vs kit and brand. Add a "Already on a battery platform?" block on cordless pages listing the best bare tool per platform (DeWalt 20V, Milwaukee M18, Makita 18V, Ryobi ONE+, Craftsman V20). Show a platform only if a ranked product exists for it. Effort: small to medium.

### 5. Sortable, filterable comparison table
TechGearLab's table sorts by column, and Torque Test Channel lets you pick tools to compare. Add a few lines of vanilla JS so the existing `#compare` table sorts by price, rating or weight, with filter chips for kit/bare and brand. With JS off, the static table still renders. Effort: small.

### 6. Price history ("lowest price we've seen")
ToolGuyd's whole deals section exists because readers want to know whether a price is good. The refresh job already checks prices daily but throws the old ones away. Start logging every captured price (date, ASIN, price) to `data/price-history.json`. After a few rotations, show "Lowest we've recorded: $X on [date]" next to the price. All of it is real data we collected, which keeps the FTC side clean and makes the Black Friday page credible. Effort: small to start. The payoff grows over time, so start soon.

### 7. A "What changed" note on every page
This Old House puts an update date under the headline, and Wirecutter is known for update notes. ToolboxTop10 shows a data date but never says what moved. The refresh skill already knows which products it swapped and why ("DWD112 removed: no Amazon buy box"). Have it write a dated `changelog` entry into the category JSON and render the last three. Readers trust a list more when it visibly changes, and it gives Google a freshness signal. Effort: small.

### 8. Email capture for price drops and deals
Tools in Action and ToolGuyd both lead with newsletter signup. ToolboxTop10 has nowhere to keep a visitor who doesn't buy today. Start with one signup form (Buttondown or MailerLite free tier) and a monthly "picks that dropped in price" email built from the item 6 data. Black Friday is seven weeks away, so this is the time to start collecting addresses. Effort: medium. Needs Adam to pick a provider and sign off, since it collects personal data and the privacy page has to mention it.

### 9. Cite independent test data where it exists
Project Farm, Torque Test Channel, Pro Tool Reviews and Consumer Reports publish measured results ToolboxTop10 can't produce yet. Where one of the ranked models has been tested by them, add a short "Independent tests" line: "Project Farm measured this at X in a 10-saw cutting test," linked to the source. This adds evidence the site can't produce itself, without claiming hands-on testing. Effort: medium, done per category during refresh runs. Rule: quote only numbers that appear in the source, and always link it.

### 10. More retailers (once approved)
Family Handyman shows four retailer buttons per product. This depends on the Home Depot reapply (items 2 and 8 help there). Walmart and Lowe's run through Impact too. Build the second-button support in build.py now (optional per-product `retailers` field), so turning on a new program only means editing data. Effort: small for the code. Approvals are the real bottleneck.

## Already in the SEO plan (confirmed by competitors, not new)

- "X vs Y" decision guides (GarageWorld360's best page is exactly this). Planned as "corded vs cordless" guides.
- Tools-to-avoid hub. No competitor has one, which still makes it the most linkable idea.
- Hands-on testing in the $50/month plan. Every top site leads with testing. Pro Tool Reviews publishes per-tool protocols worth copying when that starts.

## Skipped on purpose

- Comments and a forum (Tools in Action, ToolGuyd). The site doesn't get enough traffic for it, and comments attract spam that would need moderating.
- An awards program (Pro Tool Reviews). That only works with an established brand.
- Brand-reliability survey scores (Consumer Reports). There's no honest way to get that data.

## Suggested order

1, 5 and 7 are build.py changes that can ship together in one session. 6 should start right away so history builds up before Black Friday. Then 2 (needs Adam's bio), 4, 3, then 8 and 9. 10 waits on affiliate approvals.
