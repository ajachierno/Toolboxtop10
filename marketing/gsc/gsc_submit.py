"""Tell Google Search Console about new toolboxtop10.com pages.

Usage:
    python gsc_submit.py corded-shop-vacuums.html [more pages or full URLs ...]
    python gsc_submit.py                # just resubmit the sitemap

Steps:
  1. Wait for each new URL to go live (GitHub Pages deploys a minute or two after a push)
     and for the live sitemap.xml to list it.
  2. Resubmit https://toolboxtop10.com/sitemap.xml to the sc-domain property.
  3. Run the URL Inspection API on each new URL so the log shows Google's current view.

Google has no API for the "Request indexing" button. The sitemap resubmit is the supported
way to get a new URL in front of Googlebot; the inspection result tells you if it has been seen.

Needs the service account to be a FULL user (not Restricted) on the property, because
submitting a sitemap is a write. Key file: GSC_KEY env var, else ~/.config/gsc/toolboxtop10-sa.json.
Appends each run to data/submissions.json (git-excluded).
"""
import datetime as dt
import json
import sys
import time
import urllib.parse

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from gsc_pull import API, KEY, OUT, pick_site
from healthcheck import BASE, INSPECT, UA, sitemap_urls

SITEMAP = BASE + "sitemap.xml"
SCOPES = ["https://www.googleapis.com/auth/webmasters"]
WAIT_SECONDS = 600


def session():
    if not KEY.exists():
        sys.exit(f"Key file not found: {KEY}")
    creds = service_account.Credentials.from_service_account_file(str(KEY), scopes=SCOPES)
    creds.refresh(Request())
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {creds.token}"
    return s


def full_url(arg):
    return arg if arg.startswith("http") else BASE + arg.lstrip("/")


def wait_until_live(urls):
    """Poll until every URL returns 200 and appears in the live sitemap."""
    deadline = time.time() + WAIT_SECONDS
    pending = set(urls)
    while pending and time.time() < deadline:
        try:
            listed = set(sitemap_urls())
        except requests.RequestException:
            listed = set()
        for u in list(pending):
            try:
                ok = requests.get(u, headers=UA, timeout=30).status_code == 200
            except requests.RequestException:
                ok = False
            if ok and u in listed:
                print(f"  live + in sitemap: {u}")
                pending.discard(u)
        if pending:
            time.sleep(20)
    return sorted(pending)


def submit_sitemap(s, site):
    base = f"{API}/sites/{urllib.parse.quote(site, safe='')}/sitemaps/{urllib.parse.quote(SITEMAP, safe='')}"
    r = s.put(base)
    if r.status_code == 403:
        return {"ok": False, "error": "403: the service account needs Full permission on the property "
                "(Search Console > Settings > Users and permissions)."}
    if r.status_code not in (200, 204):
        return {"ok": False, "error": f"{r.status_code}: {r.text[:300]}"}
    status = s.get(base).json()
    return {"ok": True, "lastSubmitted": status.get("lastSubmitted"),
            "lastDownloaded": status.get("lastDownloaded"),
            "submitted": sum(int(c.get("submitted", 0)) for c in status.get("contents", []))}


def inspect(s, site, url):
    r = s.post(INSPECT, json={"inspectionUrl": url, "siteUrl": site})
    if r.status_code != 200:
        return {"error": f"{r.status_code}: {r.text[:200]}"}
    idx = r.json()["inspectionResult"].get("indexStatusResult", {})
    return {k: idx.get(k) for k in ("verdict", "coverageState", "lastCrawlTime")}


def main(args):
    urls = [full_url(a) for a in args]
    s = session()
    site = pick_site(s)
    run = {"at": dt.datetime.now().isoformat(timespec="seconds"), "site": site, "urls": urls}

    not_live = wait_until_live(urls) if urls else []
    if not_live:
        print(f"  NOT live after {WAIT_SECONDS}s (submitting anyway): {not_live}")
    run["not_live"] = not_live

    run["sitemap"] = submit_sitemap(s, site)
    print(f"Sitemap resubmit: {run['sitemap']}")

    run["inspection"] = {u: inspect(s, site, u) for u in urls}
    for u, res in run["inspection"].items():
        print(f"  {res.get('coverageState') or res.get('error')}  {u}")

    OUT.mkdir(exist_ok=True)
    log = OUT / "submissions.json"
    history = json.loads(log.read_text(encoding="utf-8")) if log.exists() else []
    history.append(run)
    log.write_text(json.dumps(history, indent=2), encoding="utf-8")
    return 0 if run["sitemap"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
