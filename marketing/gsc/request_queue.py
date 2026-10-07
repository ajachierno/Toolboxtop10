"""Pick which toolboxtop10.com URLs need a "Request indexing" click in Search Console.

Google has no API for that button, so the toolboxtop10-request-indexing skill clicks it in
Chrome. This script does the bookkeeping:

    python request_queue.py inspect [url ...]   # index status for the given URLs (default: every
                                                # sitemap URL) -> data/index-status.json
    python request_queue.py queue [N]           # URLs most worth a request, best first (default: all)
                                                # -> data/request-queue.txt
    python request_queue.py requested url ...   # record a successful request (queue skips it for 7 days)

Order: not-yet-indexed URLs first (home page, then category pages, then everything else in
sitemap order), then indexed URLs whose sitemap lastmod is newer than Google's last crawl.
Data files live in data/ (git-excluded). Same service account as gsc_pull.py.
"""
import datetime as dt
import json
import sys
import xml.etree.ElementTree as ET

import requests

from gsc_pull import OUT, pick_site, session
from healthcheck import BASE, INSPECT, UA

STATUS = OUT / "index-status.json"
REQUESTED = OUT / "index-requested.json"
QUEUE = OUT / "request-queue.txt"


def sitemap():
    r = requests.get(BASE + "sitemap.xml", headers=UA, timeout=30)
    r.raise_for_status()
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    out = []
    for u in ET.fromstring(r.content).findall(".//s:url", ns):
        loc = u.find("s:loc", ns).text.strip()
        mod = u.find("s:lastmod", ns)
        out.append((loc, mod.text.strip()[:10] if mod is not None and mod.text else ""))
    return out


def load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def inspect(urls):
    s, _sa = session()
    site = pick_site(s)
    data = load(STATUS)
    targets = urls or [u for u, _m in sitemap()]
    for i, u in enumerate(targets, 1):
        r = s.post(INSPECT, json={"inspectionUrl": u, "siteUrl": site})
        if r.status_code != 200:
            print(f"  [{i}/{len(targets)}] error {r.status_code}  {u}")
            continue
        idx = r.json()["inspectionResult"].get("indexStatusResult", {})
        data[u] = {"state": idx.get("coverageState", "unknown"), "crawled": idx.get("lastCrawlTime"),
                   "checked": dt.datetime.utcnow().isoformat(timespec="seconds")}
        print(f"  [{i}/{len(targets)}] {data[u]['state']:40} {u}")
    OUT.mkdir(exist_ok=True)
    STATUS.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    counts = {}
    for u in targets:
        if u in data:
            counts[data[u]["state"]] = counts.get(data[u]["state"], 0) + 1
    print("Summary:", ", ".join(f"{v} {k}" for k, v in sorted(counts.items(), key=lambda x: -x[1])))


def queue(n=None):
    data = load(STATUS)
    if not data:
        sys.exit("No index data yet. Run: python request_queue.py inspect")
    asked = load(REQUESTED)
    week_ago = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    todo = []
    for pos, (u, mod) in enumerate(sitemap()):
        st = data.get(u, {}).get("state", "unknown")
        if st.startswith(("Submitted and indexed", "Indexed")):
            crawled = (data[u].get("crawled") or "")[:10]
            if not (mod and crawled and mod > crawled):
                continue
            changed, why = 1, f"changed {mod}, crawled {crawled}"
        else:
            changed, why = 0, st
        if asked.get(u, "") >= week_ago:
            continue
        rank = 0 if u.rstrip("/") + "/" == BASE else 1
        todo.append((changed, rank, pos, u, why))
    todo.sort()
    pick = todo[:n] if n else todo
    print(f"{len(todo)} URLs could use a request" + (f"; first {len(pick)}:" if n else ":"))
    for *_x, u, why in pick:
        print(f"  {u}   ({why})")
    OUT.mkdir(exist_ok=True)
    QUEUE.write_text("".join(f"{u}\n" for *_x, u, _w in pick), encoding="utf-8")


def requested(urls):
    asked = load(REQUESTED)
    for u in urls:
        asked[u] = dt.date.today().isoformat()
    OUT.mkdir(exist_ok=True)
    REQUESTED.write_text(json.dumps(asked, indent=1) + "\n", encoding="utf-8")
    print(f"Recorded {len(urls)} request(s).")


if __name__ == "__main__":
    cmd, args = (sys.argv[1] if len(sys.argv) > 1 else "queue"), sys.argv[2:]
    if cmd == "inspect":
        inspect(args or None)
    elif cmd == "queue":
        queue(int(args[0]) if args else None)
    elif cmd == "requested":
        requested(args)
    else:
        sys.exit(__doc__)
