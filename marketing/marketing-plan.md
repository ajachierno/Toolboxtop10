# ToolboxTop10 — Agent-Executed Traffic Plan (DRAFT v2)

_Drafted 2026-09-24. Horizon: 9 months (Oct 2026 – Jun 2027). Goal: maximize site visits._
_Executor: Claude, running as a scheduled daily task. The owner does a one-time setup and nothing else._

v1 assumed a person would do the marketing. It has been replaced. This version covers only
what an agent can do legitimately and without anyone's help.

---

## 0. Starting point and constraints

- **Traffic today:** about 0. There's no analytics yet, so every number below is an estimate until about day 30.
- **Site:** 28 category pages on GitHub Pages, served from `main` → `docs/`. Technical SEO is
  already solid (canonical tags, sitemap, JSON-LD for ItemList, Breadcrumb, and FAQ).
- **A separate daily process already adds and refreshes categories.** This plan does **not**
  add categories or edit existing `data/<category>.json` files, so the two don't collide
  (see §6).
- **Amazon pays about 3% on tools**, which is roughly $0.03–0.10 earned per visitor. Any
  paid click that costs more than about $0.10 loses money directly. Paid spend is therefore
  small, capped, and limited to the cheapest channel (Pinterest).
- **What the agent won't do:**
  - Post on Reddit, Facebook groups, or Quora. Bot posting breaks their rules, and Reddit
    bans domains permanently.
  - Create accounts in the owner's name.
  - Contact journalists or bloggers as the owner.
  - Put affiliate links in email. Amazon's rules forbid it.
  - Buy backlinks.

## 1. One-time owner setup (about 30–45 minutes total)

| # | Step | Needed for | Time |
|---|---|---|---|
| 1 | Create free Cloudflare Web Analytics (or GA4) and send the site token | All tiers, for measurement | 5 min |
| 2 | Google Search Console: Claude adds a verification meta tag, then you click Verify. Also add Bing Webmaster (it imports from Google Search Console in one click) | All tiers | 10 min |
| 3 | Pinterest: create a business account, claim toolboxtop10.com (Claude adds the tag), create a developer app, and store the access token as an environment secret `PINTEREST_TOKEN` | All tiers (optional on Free, but it's the biggest single lever) | 15–20 min, plus Pinterest's app approval (can take days) |
| 4 | Pinterest Ads: add a card and set an **account spending limit of $50** (or $75 on the $100 tier). The platform enforces the cap, so the price stays fixed | $50 and $100 | 5 min |
| 5 | DataForSEO: prepay $25/month and store the API login as secret `DATAFORSEO_AUTH` | $100 only | 5 min |

Any step you skip just removes the tasks that depend on it. Nothing else breaks.

---

## 2. FREE plan — $0/month

### Month 1 (Oct): foundations and the pre–Black Friday push
**Week 1**
- Add an analytics snippet and Search Console/Bing verification tags to the `build.py` page template.
- **IndexNow:** host the key file at `docs/<key>.txt`, then ping Bing and Yandex with every
  new or changed URL after each build. New categories from the daily process get indexed
  within hours instead of weeks.
- **Per-page preview images:** generate a 1200×630 image for each page at build time
  showing the page title, the #1 pick, and its score. This replaces the logo on every
  page and gets more clicks when links are shared.
- **Internal links:** link each corded/cordless pair both ways (e.g. cordless ↔ corded
  jigsaws) and add a "Related tools" block to every category page.

**Weeks 2–4: the comparison page engine (new `build_compare.py`, reads existing JSON, never edits it)**
- **"X vs Y" pages:** Best Overall vs Best Budget, and Best Overall vs Money No Object, in
  every category (about 56 pages). Each one has a spec table, score breakdown, "who should
  buy which", and FAQ schema.
- **"Best ___ under $50 / $100 / $200" pages**, only where at least 3 products qualify (about 40 pages).
- **"Corded vs cordless ___" guides** for the 7 paired categories.
- **Brand pages** ("Best DEWALT tools we rank", "Best Milwaukee…") for brands appearing in 3 or more categories.
- **Seasonal hub pages:** "Best tool gifts under $50 / $100" and "Black Friday tool picks",
  live **by Nov 1** (peak search season).
- About 120 new pages total, all added to the sitemap and pinged through IndexNow.

**Every day**
- Detect any categories added or refreshed by the other process, then regenerate their
  comparison pages, preview images, and links.
- **Pinterest** (if setup step 3 is done): generate 5–10 tall pins a day (1000×1500) from
  the real data with Python/Pillow. Formats:
  - "Top 3 under $60"
  - "Tools to AVOID"
  - "Overall vs Budget"
  - "Corded vs Cordless"

  Each pin gets keyword-rich titles and descriptions, links to the matching page, and goes
  onto boards organized by tool type.

### Months 2–3 (Nov–Dec): holiday peak
- Refresh the gift and Black Friday pages every week with current prices. Each refresh is a
  commit, which also shows Google the pages are current.
- Add a "Price checked [date]" label to every page's #1 pick.
- Pinterest: shift the pin mix toward gifts, since holiday DIY/gift pins peak in Nov–Dec.
- **Email capture:** a static form (Buttondown free tier, owner-created, or a simple
  form service) offering "New rankings + price drops, monthly". The emails would never
  contain affiliate links.

### Months 4–9 (Jan–Jun): compounding and pruning
- **Monthly analytics review** (Search Console and analytics, once access is given):
  - Pages with impressions but a low click rate get a rewritten title and meta description.
  - Pages ranking in positions 8–20 get a stronger FAQ, more internal links, and one related comparison page.
  - Pages with no impressions after 90 days get merged or removed from the sitemap.
- **Pinterest:**
  - Every pin topic that saves well gets 3 new designs, because Pinterest rewards fresh pins.
  - Pin formats that underperform get dropped.
- **Seasonal content:**
  - Father's Day gift pages go live by May 1.
  - Spring project pages ("tools for building a deck or garden beds") go live by Mar 1.
- **Weekly report to the owner** covering visits by channel, top pages, new pages, and what changed.

## 3. $50/month plan

**Free plan, plus Pinterest Ads, $50/month fixed (the account limit enforces it).**

- **Week 1 of each month:** pick the 3 organic pins with the highest click rate from the
  last 30 days and promote them through the Pinterest Ads API.
  - Targeting: the home improvement / DIY / tools interests plus the page's keywords.
  - Daily budget: ~$1.60, so the month never goes over.
- **Every week:** pause any ad costing more than $0.30 a click after 7 days, and move its
  budget to the next-best organic pin.
- **Nov–Dec:** shift about 70% of the budget to gift pages (highest intent, highest conversion).
- Why it's worth doing:
  - At a $0.15–0.30 click cost that's about 170–330 extra visits a month.
  - Promoted pins also collect saves, and saved pins keep sending traffic after the ad ends.
- **Best value per dollar of the paid tiers.**

## 4. $100/month plan

**The $50 plan, with two changes:**

| Line | Fixed $/mo | What Claude does with it |
|---|---|---|
| Pinterest Ads | $75 | Same process as the $50 plan, but promoting the top 5 pins instead of 3 |
| DataForSEO (keyword and search-results data, prepaid) | $25 | See below |
| **Total** | **$100** | |

What the agent does with the search data:
- **Month 1:** pull search volume and difficulty for every category's "best ___" query and
  about 500 comparison and "under $X" variations. Build comparison pages for **the searches
  people actually make**, not every possible pair.
- **Monthly:**
  - Check where the top 50 pages rank.
  - Look for weak competition on page 1 (forums, Amazon, or Reddit in the top 5). That
    means the query is winnable, so build it next.
- **Send the owner a ranked list of categories to add** to the other daily process. This is
  a suggestion only, since this plan doesn't add categories itself.
- The extra $50 has lower returns than the first $50, but the search data keeps improving
  every page built after it.

## 5. Projected monthly visits (from a baseline of about 0)

| Month | Free (no Pinterest) | Free + Pinterest | $50 | $100 |
|---|---|---|---|---|
| 1 (Oct) | 20 | 50 | 250 | 400 |
| 2 (Nov) | 50 | 150 | 400 | 600 |
| 3 (Dec) | 80 | 250 | 500 | 750 |
| 4 (Jan) | 130 | 400 | 700 | 950 |
| 5 (Feb) | 200 | 600 | 950 | 1,250 |
| 6 (Mar) | 300 | 900 | 1,300 | 1,700 |
| 7 (Apr) | 430 | 1,200 | 1,700 | 2,150 |
| 8 (May) | 600 | 1,550 | 2,100 | 2,650 |
| 9 (Jun) | **800** | **2,000** | **2,600** | **3,200** |
| Month-9 range | 200–2,000 | 600–4,500 | 1,000–5,500 | 1,300–6,500 |
| 9-month spend | $0 | $0 | $450 | $900 |
| Extra month-9 visits per $ vs. Free + Pinterest | — | — | ~12 per $ | ~12 per $, but more of it is paid clicks |

Why the curves look like this:
- The Free plan is slow until about month 5, because Google holds back new domains.
- Pinterest ramps up over 2–3 months.
- Paid traffic shows up from day 1 but stops when spend stops.
- Around month 9, the $100 tier's search data starts to matter more than its extra ad spend.
- Low end of each range: Pinterest API approval stalls, or Google is slow to trust the
  site. High end: several comparison pages reach the top 3 for real searches.
- **Revenue check:** at $0.03–0.10 per visit, month 9 earns about $25–80 (Free, no
  Pinterest) up to $95–320 (the $100 tier).

**Recommendation:** Free + Pinterest setup (step 3) is the biggest gain. $50 is the best
paid value. Only choose $100 if you want the traffic sooner and can accept a lower return
on the second $50.

## 6. How this runs alongside the existing daily process

- **Scope split:**
  - This plan owns `build.py` template changes (analytics, preview images, links, IndexNow),
    new `build_compare.py`, new `data/compare/*.json`, generated `docs/compare/*`, the
    `pins/` output, and `marketing/`.
  - This plan never touches `data/<category>.json` or `data/site.json` category entries.
- **Schedule:** run at a fixed time well away from the other process. Before building,
  always pull the latest `main`, so it builds on top of that day's new category.
- **Publishing:** default is a daily PR for the first 2 weeks. After that, push straight to
  `main` only if the owner approves (§7 Q2).
- **`build.py` changes are one-time, small, and made first,** so the other process picks
  them up automatically after that.

## 7. Decisions still open

1. Which tier: Free, $50, or $100?
2. Publishing: PRs for review, or auto-push to `main`?
3. Will you do Pinterest setup (step 3)?
4. What drives the existing daily process (another scheduled task, a script, you by hand)?
   Knowing that lets the schedule be set to avoid collisions.
5. Is this repo public? If it is, this plan is visible on GitHub.
