"""Site audit for the Friday review: load every page in docs/ at desktop and phone sizes
from a local server and report JS errors, console errors, failed same-origin requests,
horizontal overflow and broken local images. External requests (Amazon images, fonts,
analytics) are blocked so only the site itself is tested.

    python scripts/site_audit.py            # prints "no problems" or one line per problem

Needs Playwright with Chromium (already installed for the scrapers). The redirect stubs
in docs/ navigate away mid-check and are reported as such; that is expected.
"""
import asyncio
import subprocess
import sys
import time
from pathlib import Path

from playwright.async_api import async_playwright

DOCS = Path(__file__).resolve().parent.parent / "docs"
PORT = 8766
BASE = f"http://127.0.0.1:{PORT}/"
VIEWS = {"desktop": dict(viewport={"width": 1366, "height": 900}),
         "phone": dict(viewport={"width": 412, "height": 915}, is_mobile=True, has_touch=True)}
CHECK = ("() => ({scrollW: document.documentElement.scrollWidth, W: document.documentElement.clientWidth,"
         " imgs: [...document.images].filter(i => i.src.startsWith(location.origin) && i.complete"
         " && i.naturalWidth === 0).map(i => i.getAttribute('src'))})")
REDIRECTS = {"impact-drivers.html"}


async def main():
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1", "-d", str(DOCS)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    problems, loads = [], 0
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            for view, opts in VIEWS.items():
                ctx = await browser.new_context(**opts)
                await ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(BASE) else r.abort())
                sem = asyncio.Semaphore(6)

                async def one(name):
                    nonlocal loads
                    async with sem:
                        pg = await ctx.new_page()
                        errs, fails = [], []
                        pg.on("pageerror", lambda e: errs.append(str(e)[:160]))
                        pg.on("console", lambda m: m.type == "error" and "Failed to load resource" not in m.text
                              and errs.append(m.text[:160]))
                        pg.on("requestfailed", lambda r: r.url.startswith(BASE) and fails.append(r.url[len(BASE):]))
                        pg.on("response", lambda r: r.url.startswith(BASE) and r.status >= 400
                              and fails.append(f"{r.status} {r.url[len(BASE):]}"))
                        try:
                            await pg.goto(BASE + name, wait_until="load", timeout=60000)
                            await pg.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                            await pg.wait_for_timeout(300)
                            info = await pg.evaluate(CHECK)
                        except Exception as e:
                            info = {"fatal": str(e)[:160]}
                        loads += 1
                        tag = f"{name} [{view}]"
                        if info.get("fatal") and name not in REDIRECTS:
                            problems.append(f"{tag} FATAL {info['fatal']}")
                        if info.get("scrollW", 0) > info.get("W", 0) + 1:
                            problems.append(f"{tag} OVERFLOW {info['scrollW']}>{info['W']}")
                        problems.extend(f"{tag} JS {e}" for e in errs)
                        problems.extend(f"{tag} REQ {f}" for f in fails)
                        problems.extend(f"{tag} IMG {i}" for i in info.get("imgs", []))
                        await pg.close()

                await asyncio.gather(*(one(f.name) for f in sorted(DOCS.glob("*.html"))))
                await ctx.close()
            await browser.close()
    finally:
        srv.terminate()
    print(f"{loads} page loads")
    print("\n".join(problems) if problems else "no problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
