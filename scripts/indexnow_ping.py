#!/usr/bin/env python3
"""Tell IndexNow engines (Bing, Yandex, Seznam, Naver) which URLs changed.

Compares two sitemap.xml files and submits only URLs that are new or whose
<lastmod> moved, so unchanged pages are never re-pinged.

  python scripts/indexnow_ping.py OLD_SITEMAP NEW_SITEMAP   # changed URLs only
  python scripts/indexnow_ping.py --all NEW_SITEMAP         # every URL (first run)
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENDPOINT = "https://api.indexnow.org/indexnow"


def entries(path):
    text = Path(path).read_text(encoding="utf-8") if path and Path(path).exists() else ""
    return dict(re.findall(r"<loc>([^<]+)</loc><lastmod>([^<]+)</lastmod>", text))


def main(argv):
    if argv[:1] == ["--all"]:
        urls = list(entries(argv[1]))
    else:
        old, new = entries(argv[0]), entries(argv[1])
        urls = [u for u, mod in new.items() if old.get(u) != mod]
    if not urls:
        print("IndexNow: nothing changed, no ping sent")
        return 0
    site = json.loads((ROOT / "data" / "site.json").read_text(encoding="utf-8"))
    key = json.loads((ROOT / "data" / "tracking.json").read_text(encoding="utf-8")).get("indexnow_key")
    if not key:
        print("IndexNow: no indexnow_key in data/tracking.json, skipping")
        return 0
    host = site["custom_domain"]
    body = json.dumps({"host": host, "key": key,
                       "keyLocation": f"https://{host}/{key}.txt", "urlList": urls}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        print(f"IndexNow: HTTP {resp.status} for {len(urls)} URL(s)")
        for u in urls:
            print("  " + u)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
