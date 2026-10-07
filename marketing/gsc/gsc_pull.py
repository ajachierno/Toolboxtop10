"""Pull Google Search Console data for toolboxtop10.com with a service account.

Usage:
    python gsc_pull.py            # list properties the key can see, then pull the last 90 days
    python gsc_pull.py --days 28

Key file: GSC_KEY env var, else ~/.config/gsc/toolboxtop10-sa.json. Keep it out of the repo.
Writes JSON + CSV into ./data/ next to this script (git-excluded).
"""
import argparse
import csv
import datetime as dt
import json
import os
import pathlib
import sys
import urllib.parse

import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
API = "https://searchconsole.googleapis.com/webmasters/v3"
KEY = pathlib.Path(os.environ.get("GSC_KEY", pathlib.Path.home() / ".config/gsc/toolboxtop10-sa.json"))
OUT = pathlib.Path(__file__).parent / "data"


def session():
    if not KEY.exists():
        sys.exit(f"Key file not found: {KEY}")
    creds = service_account.Credentials.from_service_account_file(str(KEY), scopes=SCOPES)
    creds.refresh(Request())
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {creds.token}"
    return s, creds.service_account_email


def pick_site(s):
    sites = s.get(f"{API}/sites").json().get("siteEntry", [])
    ours = [x["siteUrl"] for x in sites if "toolboxtop10.com" in x["siteUrl"]]
    for x in sites:
        print(f"  {x['siteUrl']}  ({x['permissionLevel']})")
    if not ours:
        sys.exit("No toolboxtop10.com property visible. Add the service account email as a user in Search Console.")
    # Prefer the domain property, it covers every URL variant.
    return next((u for u in ours if u.startswith("sc-domain:")), ours[0])


def query(s, site, start, end, dims):
    rows, start_row = [], 0
    url = f"{API}/sites/{urllib.parse.quote(site, safe='')}/searchAnalytics/query"
    while True:
        body = {"startDate": str(start), "endDate": str(end), "dimensions": dims,
                "rowLimit": 25000, "startRow": start_row, "dataState": "all"}
        r = s.post(url, json=body)
        r.raise_for_status()
        batch = r.json().get("rows", [])
        rows += batch
        if len(batch) < 25000:
            return rows
        start_row += 25000


def save(name, rows, dims):
    OUT.mkdir(exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    with open(OUT / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(dims + ["clicks", "impressions", "ctr", "position"])
        for r in rows:
            w.writerow(r["keys"] + [r["clicks"], r["impressions"], round(r["ctr"], 4), round(r["position"], 1)])
    print(f"  {name}: {len(rows)} rows")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    a = ap.parse_args()
    s, email = session()
    print(f"Service account: {email}\nProperties:")
    site = pick_site(s)
    end = dt.date.today()
    start = end - dt.timedelta(days=a.days)
    print(f"Pulling {site} {start} -> {end}")
    for name, dims in [("pages", ["page"]), ("queries", ["query"]),
                       ("query-page", ["query", "page"]), ("daily", ["date"])]:
        save(name, query(s, site, start, end, dims), dims)


if __name__ == "__main__":
    main()
