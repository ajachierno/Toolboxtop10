"""Site health check for toolboxtop10.com: Search Console (sitemaps + URL inspection) plus a live crawl.

Usage:
    python healthcheck.py              # inspection + crawl
    python healthcheck.py --no-inspect # crawl + sitemaps only (inspection quota is 2,000/day)

Writes data/sitemaps.json, data/inspection.json, data/crawl.json (git-excluded).
"""
import argparse
import collections
import json
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET

import requests

from gsc_pull import API, OUT, pick_site, session

BASE = "https://toolboxtop10.com/"
INSPECT = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
UA = {"User-Agent": "Mozilla/5.0 (compatible; toolboxtop10-healthcheck)"}


def sitemap_urls():
    r = requests.get(BASE + "sitemap.xml", headers=UA, timeout=30)
    r.raise_for_status()
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    return [e.text.strip() for e in ET.fromstring(r.content).findall(".//s:loc", ns)]


def gsc_sitemaps(s, site):
    r = s.get(f"{API}/sites/{urllib.parse.quote(site, safe='')}/sitemaps")
    r.raise_for_status()
    return r.json().get("sitemap", [])


def inspect(s, site, urls):
    out = {}
    for i, u in enumerate(urls, 1):
        r = s.post(INSPECT, json={"inspectionUrl": u, "siteUrl": site})
        if r.status_code != 200:
            out[u] = {"error": r.status_code, "body": r.text[:300]}
            continue
        res = r.json()["inspectionResult"]
        idx = res.get("indexStatusResult", {})
        idx["richResults"] = res.get("richResultsResult")
        idx["mobile"] = res.get("mobileUsabilityResult")
        out[u] = idx
        print(f"  [{i}/{len(urls)}] {idx.get('coverageState')}  {u}")
    return out


A_HREF = re.compile(r'<a\b[^>]*\bhref="([^"]+)"', re.I)
IMG = re.compile(r'<img\b[^>]*>', re.I)


def meta(html, pat):
    m = re.search(pat, html, re.I | re.S)
    return m.group(1).strip() if m else None


def crawl(seed_urls):
    seen, queue, pages, external = set(), list(seed_urls), {}, collections.Counter()
    while queue:
        u = queue.pop(0).split("#")[0]
        if u in seen:
            continue
        seen.add(u)
        try:
            r = requests.get(u, headers=UA, timeout=30, allow_redirects=False)
        except requests.RequestException as e:
            pages[u] = {"status": f"ERR {e}"}
            continue
        p = {"status": r.status_code, "location": r.headers.get("location"), "bytes": len(r.content)}
        pages[u] = p
        if r.status_code in (301, 302, 307, 308) and p["location"]:
            queue.append(urllib.parse.urljoin(u, p["location"]))
            continue
        if r.status_code != 200 or "text/html" not in r.headers.get("content-type", ""):
            continue
        h = r.text
        p["title"] = meta(h, r"<title>(.*?)</title>")
        p["description"] = meta(h, r'<meta name="description" content="([^"]*)"')
        p["canonical"] = meta(h, r'<link rel="canonical" href="([^"]*)"')
        p["robots"] = meta(h, r'<meta name="robots" content="([^"]*)"')
        p["refresh"] = meta(h, r'<meta http-equiv="refresh" content="([^"]*)"')
        p["h1"] = len(re.findall(r"<h1\b", h, re.I))
        p["jsonld"] = []
        for blk in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S):
            try:
                d = json.loads(blk)
                p["jsonld"].append(d.get("@type") if isinstance(d, dict) else "list")
            except ValueError as e:
                p["jsonld"].append(f"INVALID: {e}")
        p["img_no_alt"] = sum(1 for t in IMG.findall(h) if not re.search(r'\balt="[^"]+"', t))
        p["words"] = len(re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)\b.*?</\1>", " ", h, flags=re.S)).split())
        links = set()
        for href in A_HREF.findall(h):
            full = urllib.parse.urljoin(u, href).split("#")[0]
            if full.startswith(BASE) or full.startswith("http://toolboxtop10.com"):
                links.add(full)
                if full not in seen:
                    queue.append(full)
            elif full.startswith("http"):
                external[urllib.parse.urlparse(full).netloc] += 1
        p["internal_links"] = sorted(links)
    return pages, external


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-inspect", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    urls = sitemap_urls()
    print(f"Sitemap: {len(urls)} URLs")
    s, _ = session()
    site = pick_site(s)
    (OUT / "sitemaps.json").write_text(json.dumps(gsc_sitemaps(s, site), indent=1), encoding="utf-8")
    if not a.no_inspect:
        (OUT / "inspection.json").write_text(json.dumps(inspect(s, site, urls), indent=1), encoding="utf-8")
    pages, external = crawl([BASE] + urls + [BASE + "robots.txt", BASE + "impact-drivers.html",
                                               "http://toolboxtop10.com/", "https://www.toolboxtop10.com/"])
    (OUT / "crawl.json").write_text(json.dumps({"pages": pages, "external": external}, indent=1), encoding="utf-8")
    print(f"Crawled {len(pages)} URLs")


if __name__ == "__main__":
    sys.exit(main())
