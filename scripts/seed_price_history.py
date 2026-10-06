"""One-off: rebuild data/price-history.json from the git history of data/*.json.

Every committed version of a category file is a real Amazon capture, dated by its
data_captured field (or the commit date if the field was missing). WIP commits are
skipped because they held unverified draft data. For each ASIN we keep one price per
date, taking the last commit made for that date. build.py appends new captures from
then on, so this only needs running once.
"""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout


def main():
    history = {}
    site = json.loads((ROOT / "data/site.json").read_text(encoding="utf-8"))
    for c in site["categories"]:
        path = f"data/{c['slug']}.json"
        log = git("log", "--follow", "--reverse", "--date=short", "--format=%H %ad %s", "--", path)
        for line in log.splitlines():
            sha, date, subject = line.split(" ", 2)
            if subject.startswith("WIP"):
                continue
            try:
                cat = json.loads(git("show", f"{sha}:{path}"))
            except (subprocess.CalledProcessError, json.JSONDecodeError):
                continue  # file had another name at this commit, or was mid-edit
            when = cat.get("data_captured") or date
            for p in cat.get("products", []) + cat.get("avoid", []):
                if isinstance(p.get("price"), (int, float)) and p.get("asin"):
                    history.setdefault(p["asin"], {})[when] = p["price"]
    out = {a: sorted(d.items()) for a, d in sorted(history.items())}
    write(out)
    print(f"{len(out)} ASINs, {sum(len(v) for v in out.values())} price points")


def write(history):
    lines = [f"  {json.dumps(a)}: {json.dumps(v)}" for a, v in history.items()]
    (ROOT / "data/price-history.json").write_text("{\n" + ",\n".join(lines) + "\n}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
