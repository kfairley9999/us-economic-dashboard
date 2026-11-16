"""Capture README screenshots of the dashboard with headless Chromium.

    python -m http.server 8765 --directory site &
    python scripts/screenshot.py --url http://localhost:8765/ --out docs

Requires ``pip install playwright`` and a Chromium (``playwright install
chromium``) or a system Chrome passed via ``--chrome``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

SHOTS = [
    # name, viewport, device scale, theme, full page
    ("mobile", {"width": 390, "height": 844}, 3, "dark", False),
    ("mobile-light", {"width": 390, "height": 844}, 3, "light", False),
    ("mobile-full", {"width": 390, "height": 844}, 2, "dark", True),
    ("desktop", {"width": 1440, "height": 900}, 2, "dark", False),
    ("desktop-light", {"width": 1440, "height": 900}, 2, "light", False),
    ("desktop-full", {"width": 1440, "height": 900}, 1, "light", True),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8765/")
    ap.add_argument("--out", type=Path, default=Path("docs"))
    ap.add_argument("--chrome", default=None, help="path to a Chrome/Chromium binary")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.chrome) if args.chrome else p.chromium.launch()
        for name, vp, dpr, theme, full in SHOTS:
            ctx = browser.new_context(
                viewport=vp,
                device_scale_factor=dpr,
                color_scheme=theme,
                is_mobile=vp["width"] < 600,
                has_touch=vp["width"] < 600,
            )
            page = ctx.new_page()
            page.on("console", lambda m: m.type == "error" and errors.append(m.text))
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(args.url, wait_until="networkidle")
            page.wait_for_selector(".kpi .kpi-value")
            if full:
                # build every lazily-created chart before a full-page capture
                page.evaluate(
                    "async () => { for (const el of document.querySelectorAll('.chart-card')) {"
                    " el.scrollIntoView(); await new Promise(r => setTimeout(r, 250)); }"
                    " window.scrollTo(0, 0); }"
                )
                page.wait_for_timeout(800)
            else:
                page.wait_for_timeout(700)
            page.screenshot(path=str(args.out / f"screenshot-{name}.png"), full_page=full)
            if name == "mobile":
                overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
                print(f"mobile horizontal overflow: {overflow}px")
            ctx.close()
        browser.close()
    print("console errors:", errors or "none")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
