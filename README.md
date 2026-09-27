# ToolboxTop10

Static affiliate review site for tools and DIY gear. Side-by-side ranked top-10 lists
(Best Overall + Best Budget), pros/cons, comparison tables, and a "tools to avoid" section.
Data is pulled from Amazon and scored on a transparent 100-point scale.

Live site: https://toolboxtop10.com

## How it works

- `data/site.json` — global config (brand, tagline, affiliate tag, custom domain, category list).
- `data/<category>.json` — one file per category (products, specs, avoid list, buyer's guide, ranking weights).
- `build.py` — zero-dependency Python generator. Reads the JSON, scores/ranks each product,
  and writes the static site into `docs/` (plus `CNAME` and `.nojekyll` for GitHub Pages).

## Build

```
python build.py
```

Output lands in `docs/`, which GitHub Pages serves. Never hand-edit `docs/` — edit the
JSON or `build.py` and rebuild.

## Deploy

GitHub Pages serves from the `main` branch, `/docs` folder. Custom domain `toolboxtop10.com`
is set via the `CNAME` file (generated from `data/site.json` -> `custom_domain`).

## Adding the affiliate tag

Set `affiliate_tag` in `data/site.json` to your Amazon Associates tracking ID, then rebuild.
Every "buy" link becomes `https://www.amazon.com/dp/<ASIN>?tag=<TAG>&linkCode=ll1`.
