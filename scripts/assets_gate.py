"""Runtime assets gate: load the kit in a real browser and FAIL it if any
referenced JS library never executed.

Motivation: kits routinely shipped with a perfect craft score but dead motion —
the generator hallucinated SRI `integrity` hashes (browser blocks the script) or
pinned non-existent CDN versions (404 → MIME refusal), so gsap/ScrollTrigger/
Lenis/SplitType were all `undefined` and the signature scroll mechanic never ran.
The DOM-metrics gate can't see this (the page still has markup); only executing
the page does. This gate executes it and checks both that no external script/style
failed to load AND that each referenced animation library's global is defined.
"""
from __future__ import annotations
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# substring in a <script src> → the global the library must expose once it runs
_LIB_GLOBALS = {
    "gsap": "gsap",
    "scrolltrigger": "ScrollTrigger",
    "lenis": "Lenis",
    "split-type": "SplitType",
    "splittype": "SplitType",
    "three": "THREE",
    "lottie": "lottie",
    "barba": "barba",
    "swiper": "Swiper",
}

# console-error fingerprints that mean a resource was blocked/failed to load
_LOAD_ERROR_MARKS = (
    "integrity", "refused to execute", "failed to load resource",
    "mime type", "net::err", "was blocked", "valid digest",
)


def _frame_delta(a: bytes, b: bytes) -> float:
    """Fraction of pixels that changed between two screenshots (per-pixel RGB sum
    diff > 24 of a possible 765). 0.0 for an identical frame; rises with any on-page
    movement. Lazy PIL/numpy import (same stack render_metrics uses)."""
    import io
    from PIL import Image
    import numpy as np
    ia = np.asarray(Image.open(io.BytesIO(a)).convert("RGB")).astype(np.int16)
    ib = np.asarray(Image.open(io.BytesIO(b)).convert("RGB")).astype(np.int16)
    if ia.shape != ib.shape:  # layout reflow between frames is itself motion
        return 1.0
    return round(float((np.abs(ia - ib).sum(axis=2) > 24).mean()), 4)


def _expected_globals(html: str) -> dict:
    """Map each referenced library to the global it must define (deduped)."""
    import re
    out = {}
    for src in re.findall(r'<script[^>]*\ssrc=["\']([^"\']+)["\']', html, re.I):
        low = src.lower()
        for needle, glob in _LIB_GLOBALS.items():
            if needle in low:
                out[glob] = src
    return out


def check_runtime(kit_dir, page_file: str = "index.html", port: int = 8202,
                  settle_ms: int = 4000) -> dict:
    """Returns {ok, failed_resources, undefined_libs, console_errors}.

    ok is False if any external script/stylesheet failed to load OR any referenced
    library global is undefined after the page settles.
    """
    kit_dir = Path(kit_dir)
    html = (kit_dir / page_file).read_text(encoding="utf-8", errors="ignore")
    expected = _expected_globals(html)

    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=str(kit_dir), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    failed_resources: list[str] = []
    console_errors: list[str] = []
    libs: dict = {}
    scroll: dict = {}
    frame_a: bytes | None = None
    frame_b: bytes | None = None
    try:
        root = f"http://127.0.0.1:{port}/"
        for _ in range(50):
            try:
                with urllib.request.urlopen(root + page_file, timeout=0.5) as r:
                    if r.status == 200:
                        break
            except Exception:
                time.sleep(0.1)
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch(headless=True)
            try:
                pg = b.new_context(viewport={"width": 1440, "height": 900}).new_page()

                def _on_console(m):
                    if m.type == "error":
                        t = m.text[:200]
                        console_errors.append(t)
                        if any(k in t.lower() for k in _LOAD_ERROR_MARKS):
                            failed_resources.append(t)

                def _on_failed(r):
                    if r.resource_type in ("script", "stylesheet"):
                        failed_resources.append(f"{r.url.split('/')[-1]} ({r.resource_type} request failed)")

                def _on_response(r):
                    if r.request.resource_type in ("script", "stylesheet") and r.status >= 400:
                        failed_resources.append(f"{r.url.split('/')[-1]} (HTTP {r.status})")

                pg.on("console", _on_console)
                pg.on("requestfailed", _on_failed)
                pg.on("response", _on_response)
                pg.goto(root + page_file, wait_until="load", timeout=20000)
                # At-rest motion probe: capture a frame right after load, settle, then
                # capture again WITHOUT scrolling or interacting. A page that animates on
                # load (the kinetic-experimental signature) differs between the two frames;
                # a static page is byte-identical. Gated kit-type-specifically downstream.
                frame_a = pg.screenshot()
                pg.wait_for_timeout(settle_ms)
                frame_b = pg.screenshot()
                libs = pg.evaluate(
                    "(globs) => Object.fromEntries(globs.map(g => [g, typeof window[g] !== 'undefined']))",
                    list(expected.keys()))
                # Scroll-reachability: real content height vs. the document's
                # scrollable height. Catches the "Lenis loaded without its CSS"
                # trap where height:100% pins <body> to one viewport so the page
                # can't scroll even though library globals are all defined.
                scroll = pg.evaluate(
                    """() => {
                        const de = document.documentElement;
                        const kids = [...document.body.children];
                        const contentBottom = kids.length
                            ? Math.max(...kids.map(el => el.getBoundingClientRect().bottom + window.scrollY))
                            : 0;
                        return {
                            scrollHeight: de.scrollHeight,
                            innerHeight: window.innerHeight,
                            contentBottom: Math.round(contentBottom),
                        };
                    }""")
            finally:
                b.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

    undefined_libs = sorted(g for g, ok in libs.items() if not ok)
    # dedupe while preserving order
    seen = set()
    failed_resources = [x for x in failed_resources if not (x in seen or seen.add(x))]
    # Scroll trap: content clearly exceeds one viewport, yet the document height
    # is pinned to ~the viewport, so it cannot scroll. >200px of content below
    # the fold with <=50px of scroll range is unambiguous.
    scroll_broken = bool(
        scroll
        and scroll["contentBottom"] > scroll["innerHeight"] + 200
        and scroll["scrollHeight"] <= scroll["innerHeight"] + 50
    )
    ok = not failed_resources and not undefined_libs and not scroll_broken
    # At-rest motion verdict (kit-type-agnostic here; the gate applies it only to
    # kinetic-experimental). None when the probe could not run (browser error) so the
    # caller fails OPEN rather than flag a good kit on a probe hiccup.
    motion_delta = None
    at_rest_motion = None
    if frame_a is not None and frame_b is not None:
        motion_delta = _frame_delta(frame_a, frame_b)
        at_rest_motion = motion_delta > 0.001
    return {
        "ok": ok,
        "failed_resources": failed_resources,
        "undefined_libs": undefined_libs,
        "scroll_broken": scroll_broken,
        "scroll_metrics": scroll,
        "expected_libs": expected,
        "at_rest_motion": at_rest_motion,
        "motion_delta": motion_delta,
        "console_errors": console_errors[:10],
    }
