"""Amazon Creators API client: prices, availability and buy-box state by ASIN.

    python scripts/creators_api.py check                    # token + one test call
    python scripts/creators_api.py get B00ET5VMTU [B0...]   # print records as JSON
    python scripts/creators_api.py slugs <slug> [<slug>...] # every listing on those pages

Credentials come from a CSV downloaded from Associates Central (Creators API page), kept
outside the repo: %USERPROFILE%/.config/amazon-creators/toolboxtop10-credentials.csv
(columns Application, Application Id, Credential Id, Secret, Version). Override the path
with the CREATORS_API_CSV environment variable. Never print or commit the secret.

The API does NOT return star ratings or review counts, so this covers price,
availability and buy box only; ratings and reviews still come from scrape_amazon.py.
`slugs` writes records in scrape_amazon.py's shape (price, avail, buybox, notfound)
to scrape-results/<today>-api.json, leaving rating/reviews as None.
"""
import csv
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = Path(os.environ.get(
    "CREATORS_API_CSV",
    Path.home() / ".config" / "amazon-creators" / "toolboxtop10-credentials.csv"))
TOKEN_URLS = {"3.1": "https://api.amazon.com/auth/o2/token",
              "3.2": "https://api.amazon.co.uk/auth/o2/token",
              "3.3": "https://api.amazon.co.jp/auth/o2/token"}
API = "https://creatorsapi.amazon/catalog/v1/getItems"
MARKET = "www.amazon.com"
RESOURCES = ["itemInfo.title", "offersV2.listings.price", "offersV2.listings.availability",
             "offersV2.listings.isBuyBoxWinner", "offersV2.listings.condition",
             "offersV2.listings.merchantInfo"]


def creds():
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        row = next(csv.DictReader(f))
    return row["Credential Id"], row["Secret"], row.get("Version", "3.1").strip() or "3.1"


def partner_tag():
    return json.load(open(ROOT / "data" / "site.json", encoding="utf-8"))["affiliate_tag"]


def post(url, body, headers):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"raw": raw[:500].decode(errors="replace")}


_token = {"value": None, "exp": 0}


def token():
    if _token["value"] and time.time() < _token["exp"] - 60:
        return _token["value"]
    cid, sec, ver = creds()
    code, js = post(TOKEN_URLS.get(ver, TOKEN_URLS["3.1"]),
                    {"grant_type": "client_credentials", "client_id": cid,
                     "client_secret": sec, "scope": "creatorsapi::default"}, {})
    if code != 200 or "access_token" not in js:
        raise SystemExit(f"token request failed: HTTP {code} {json.dumps(js)[:300]}")
    _token.update(value=js["access_token"], exp=time.time() + int(js.get("expires_in", 3600)))
    return _token["value"]


def get_items(asins):
    """Returns ({asin: item}, errors) for up to 10 ASINs per call, retrying throttles."""
    out, errors = {}, []
    for i in range(0, len(asins), 10):
        batch = asins[i:i + 10]
        for attempt in range(5):
            code, js = post(API, {"itemIds": batch, "itemIdType": "ASIN", "marketplace": MARKET,
                                  "partnerTag": partner_tag(), "resources": RESOURCES},
                            {"Authorization": "Bearer " + token(), "x-marketplace": MARKET})
            if code == 429 or (code >= 500 and attempt < 4):
                time.sleep(2 ** attempt)
                continue
            break
        if code != 200:
            errors.append({"asins": batch, "http": code, "body": js})
            continue
        for it in (js.get("itemsResult") or {}).get("items") or []:
            out[it["asin"]] = it
        for e in js.get("errors") or []:
            errors.append(e)
        time.sleep(1)
    return out, errors


def record(asin, item):
    """Map one API item to scrape_amazon.py's record shape (no rating/reviews)."""
    now = dt.datetime.now().isoformat(timespec="seconds")
    if item is None:
        return {"title": None, "price": None, "rating": None, "reviews": None, "bought": None,
                "avail": "not returned by API", "buybox": False, "captcha": False,
                "notfound": True, "captured": now, "source": "creators_api"}
    listings = ((item.get("offersV2") or {}).get("listings")) or []
    best = next((l for l in listings if l.get("isBuyBoxWinner")), listings[0] if listings else None)
    price = None
    avail = "no offers"
    if best:
        money = ((best.get("price") or {}).get("money")) or {}
        amt = money.get("amount")
        price = f"${amt:,.2f}" if isinstance(amt, (int, float)) else money.get("displayAmount")
        av = best.get("availability") or {}
        avail = av.get("message") or av.get("type") or ""
    title = (((item.get("itemInfo") or {}).get("title")) or {}).get("displayValue")
    return {"title": title, "price": price, "rating": None, "reviews": None, "bought": None,
            "avail": avail, "buybox": bool(best and best.get("isBuyBoxWinner")),
            "captcha": False, "notfound": False, "captured": now, "source": "creators_api"}


def slug_asins(slugs):
    asins = []
    for s in slugs:
        d = json.load(open(ROOT / "data" / f"{s}.json", encoding="utf-8"))
        asins += [p["asin"] for p in d["products"] + d.get("avoid", [])]
    return list(dict.fromkeys(asins))


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "check":
        token()
        print("token ok")
        items, errs = get_items(["B00ET5VMTU"])
        print("items returned:", len(items))
        if errs:
            print("errors:", json.dumps(errs)[:600])
        for a, it in items.items():
            print(json.dumps(record(a, it)))
        return
    asins = args if cmd == "get" else slug_asins(args)
    items, errs = get_items(asins)
    recs = {a: record(a, items.get(a)) for a in asins}
    if cmd == "slugs":
        p = ROOT / "scrape-results" / f"{dt.date.today().isoformat()}-api.json"
        p.parent.mkdir(exist_ok=True)
        old = json.load(open(p, encoding="utf-8")) if p.exists() else {}
        old.update(recs)
        json.dump(old, open(p, "w", encoding="utf-8"), indent=1)
        print(f"{len(items)} of {len(asins)} returned -> {p}")
    else:
        print(json.dumps(recs, indent=1))
    if errs:
        print("errors:", json.dumps(errs)[:1500], file=sys.stderr)


if __name__ == "__main__":
    main()
