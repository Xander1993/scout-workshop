"""Playwright DOM metrics for the awwwards quality gate.

Hero scale = the largest rendered DISPLAY-TEXT bounding box (any tag incl. SVG
wordmarks) over body font-size — robust to the SVG-wordmark technique that breaks
<h1>-based heuristics (the premium editorial kit has zero <h1>). bleed_ratio is
ADVISORY telemetry (it saturates ~1.0 in this design language). The real
deterministic signals are template_tells (rendered DOM) + vertical_void.
"""
from __future__ import annotations
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

_EVAL = r"""() => {
  const vw = window.innerWidth, vh = window.innerHeight;
  const secs = [...document.querySelectorAll('section')];
  const bleed = secs.filter(s => s.getBoundingClientRect().width >= 0.95*vw).length;
  const cand = [...document.querySelectorAll('h1,h2,svg,[class*="wordmark"],[class*="mark"]')];
  let hero = 0, heroUncapped = 0;
  for (const el of cand){ const h = el.getBoundingClientRect().height;
    if (h>heroUncapped) heroUncapped=h;          // no cap → powers the hero CEILING
    if (h>hero && h<=vh*1.6) hero=h; }           // capped → powers the hero FLOOR/ratio
  const body = parseFloat(getComputedStyle(document.body).fontSize) || 16;
  const blocks = [...document.querySelectorAll('p,h1,h2,h3,img,svg,figure,blockquote,li')]
    .map(e=>e.getBoundingClientRect()).filter(r=>r.height>4 && r.width>4).sort((a,b)=>a.top-b.top);
  // Pin-aware void: a pinned-hero scroll runway (the tall section the hero animates
  // over while position:fixed) is intentional scroll-distance, NOT dead space. Mark it
  // with [data-pin] (our convention) or GSAP's runtime-injected .pin-spacer, then
  // subtract each block-gap's overlap with those regions so the runway doesn't read as
  // a void. A genuinely empty section carries no marker → its gap is untouched.
  // The runway is the TALL spacer that creates scroll-distance; the [data-pin] marker
  // often sits on the inner position:sticky element (viewport-tall), so also credit its
  // sectioning parent (the spacer) — but NEVER body/main/html, which would void-blind
  // the whole page.
  const parentSel = 'section,[class*="pin"],[class*="hero"],[class*="plate"],[class*="spacer"],[class*="runway"]';
  const pinSet = new Set();
  for (const el of document.querySelectorAll('[data-pin],.pin-spacer')){
    pinSet.add(el);
    const p = el.parentElement;
    if (p && p.matches(parentSel)) pinSet.add(p);
  }
  const pinRects = [...pinSet].map(e=>e.getBoundingClientRect()).filter(r=>r.height>4);
  const pinOverlap = (top,bottom) => {
    let ov = 0;
    for (const r of pinRects){ const lo=Math.max(top,r.top), hi=Math.min(bottom,r.bottom); if (hi>lo) ov+=(hi-lo); }
    return ov;
  };
  // voidpx = the single LARGEST gap (broken/oversized section); voidsum = the SUM of
  // all gaps, which over page_h yields a PROPORTIONAL void ratio — a page can pass the
  // single-gap ceiling yet be mostly empty (many medium gaps); the ratio catches that.
  let voidpx = 0, voidsum = 0;
  for (let i=1;i<blocks.length;i++){
    const top = blocks[i-1].bottom, bottom = blocks[i].top;
    const eff = Math.max(0, (bottom - top) - pinOverlap(top, bottom));
    if (eff>voidpx) voidpx=eff;
    voidsum += eff;
  }
  const tells = [];
  if (document.querySelector('[class*="trust"],[class*="badge"],[class*="avatar"],[class*="testimonial"]')) tells.push('trust/badge');
  if (document.querySelectorAll('[class*="card"],[class*="service"]').length >= 3) tells.push('card-grid');
  if (document.querySelector('a[href^="tel:"]')) tells.push('click-to-call');
  if (document.querySelectorAll('a[class*="cta"],button[class*="cta"],a[class*="pill"],button[class*="pill"]').length >= 2) tells.push('repeated-cta');
  return {bleed: bleed, n: secs.length, hero_px: hero, hero_uncapped_px: heroUncapped,
          body_px: body, void_px: Math.round(voidpx), void_sum: Math.round(voidsum),
          vh: vh, page_h: document.body.scrollHeight, tells: tells};
}"""


# Default capture viewports for the gate: desktop + mobile. Density defects (voids,
# empty bands, headlines that overflow the screen) often surface on ONE viewport
# only, so the gate must judge both and take the worst case (see render_metrics_all).
VIEWPORTS = [(1440, 900), (390, 844)]


def _ink_coverage(png_bytes: bytes) -> float:
    """Fraction of full-page-screenshot pixels that carry ink (differ from the page
    background). The dominant quantized colour is taken as the background, so this is
    robust on dense pages too; a near-blank cream page scores ~0. Pure-Python/numpy,
    no per-pixel unique scan (a coarse 15-bit histogram finds the background fast)."""
    import io
    from PIL import Image
    import numpy as np
    arr = np.asarray(Image.open(io.BytesIO(png_bytes)).convert("RGB"))
    q = (arr >> 3).astype(np.uint32)  # 5 bits/channel → 15-bit colour key
    packed = (q[..., 0] << 10) | (q[..., 1] << 5) | q[..., 2]
    dom = int(np.bincount(packed.ravel(), minlength=32768).argmax())
    bg = np.array([((dom >> 10) & 31) << 3, ((dom >> 5) & 31) << 3, (dom & 31) << 3],
                  dtype=np.int16)
    dist = np.abs(arr.astype(np.int16) - bg).sum(axis=2)
    return round(float((dist > 40).mean()), 4)


def render_metrics(kit_dir, page_file: str = "index.html", port: int = 8201,
                   viewport: tuple[int, int] = (1440, 900),
                   nav_timeout_ms: int = 20000) -> dict:
    kit_dir = Path(kit_dir)
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=str(kit_dir), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        with sync_playwright() as pw:
            b = pw.chromium.launch(headless=True)
            try:
                pg = b.new_context(
                    viewport={"width": viewport[0], "height": viewport[1]}).new_page()
                # A decorative external asset that is unreachable (e.g. picsum.photos
                # with no route from the host) hangs the "load" event forever; the DOM
                # is fully rendered regardless, so tolerate the timeout and measure the
                # page rather than aborting the whole gate.
                try:
                    pg.goto(root + page_file, wait_until="load", timeout=nav_timeout_ms)
                except PlaywrightTimeoutError:
                    pass
                pg.wait_for_timeout(1500)
                raw = pg.evaluate(_EVAL)
                # Cancel any still-pending fetch (an unreachable external asset that
                # never completes) before screenshotting; otherwise screenshot's
                # implicit font/stability wait hangs on it. Everything the page needs
                # has already loaded by the post-"load" settle, so this is a no-op for
                # healthy pages and only frees a blackholed request.
                pg.evaluate("() => window.stop()")
                shot = pg.screenshot(full_page=True)
            finally:
                b.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
    body = raw["body_px"] or 16
    vh = raw["vh"] or viewport[1] or 900
    page_h = raw["page_h"] or 1
    return {
        "viewport": list(viewport),
        "page_file": page_file,
        "bleed_ratio": round(raw["bleed"] / raw["n"], 2) if raw["n"] else 0.0,  # advisory
        "hero_px": round(raw["hero_px"], 1),
        "body_px": body,
        "hero_scale_ratio": round(raw["hero_px"] / body, 1) if body else 0.0,
        # hero CEILING: uncapped hero height in viewport units. A display element taller
        # than the viewport is fine (full-bleed photo heroes measure ~1.4vh); one several
        # screens tall is a broken/overflowing wordmark. One-sided floor had no ceiling.
        "hero_vh_ratio": round(raw["hero_uncapped_px"] / vh, 2) if vh else 0.0,
        "max_vertical_void_px": raw["void_px"],
        "void_ratio": round(raw["void_sum"] / page_h, 3),
        "ink_coverage": _ink_coverage(shot),
        "page_height_px": raw["page_h"],
        "template_tells": raw["tells"],
    }


def render_metrics_all(kit_dir, port: int = 8201) -> dict:
    """Gate-facing metrics over EVERY page at EVERY viewport, reduced to the worst case.

    Genericness/hero-floor/tells stay anchored to index.html @ desktop (their original,
    calibrated semantics). The density signals — single-gap void, proportional void
    ratio, ink coverage, hero-overflow — are taken worst-case across the whole kit so a
    sparse mobile layout or an empty secondary page can no longer hide from the gate.
    """
    kit_dir = Path(kit_dir)
    pages = sorted(p.name for p in kit_dir.glob("*.html")) or ["index.html"]
    base_page = "index.html" if "index.html" in pages else pages[0]
    base = None
    worst = {"max_vertical_void_px": 0, "void_ratio": 0.0,
             "ink_coverage": 1.0, "hero_vh_ratio": 0.0}
    pnum = port
    for page in pages:
        for vp in VIEWPORTS:
            m = render_metrics(kit_dir, page_file=page, port=pnum, viewport=vp)
            pnum += 1
            if base is None and page == base_page and vp == (1440, 900):
                base = dict(m)
            worst["max_vertical_void_px"] = max(worst["max_vertical_void_px"], m["max_vertical_void_px"])
            worst["void_ratio"] = max(worst["void_ratio"], m["void_ratio"])
            worst["ink_coverage"] = min(worst["ink_coverage"], m["ink_coverage"])
            worst["hero_vh_ratio"] = max(worst["hero_vh_ratio"], m["hero_vh_ratio"])
    if base is None:  # base_page never hit desktop (only non-index pages) → use first run
        base = render_metrics(kit_dir, page_file=base_page, port=pnum)
    base.update(worst)
    base["pages_measured"] = pages
    return base
