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
  let hero = 0;
  for (const el of cand){ const h = el.getBoundingClientRect().height; if (h>hero && h<=vh*1.6) hero=h; }
  const body = parseFloat(getComputedStyle(document.body).fontSize) || 16;
  const blocks = [...document.querySelectorAll('p,h1,h2,h3,img,svg,figure,blockquote,li')]
    .map(e=>e.getBoundingClientRect()).filter(r=>r.height>4 && r.width>4).sort((a,b)=>a.top-b.top);
  let voidpx = 0;
  for (let i=1;i<blocks.length;i++){ const g = blocks[i].top - blocks[i-1].bottom; if (g>voidpx) voidpx=g; }
  const tells = [];
  if (document.querySelector('[class*="trust"],[class*="badge"],[class*="avatar"],[class*="testimonial"]')) tells.push('trust/badge');
  if (document.querySelectorAll('[class*="card"],[class*="service"]').length >= 3) tells.push('card-grid');
  if (document.querySelector('a[href^="tel:"]')) tells.push('click-to-call');
  if (document.querySelectorAll('a[class*="cta"],button[class*="cta"],a[class*="pill"],button[class*="pill"]').length >= 2) tells.push('repeated-cta');
  return {bleed: bleed, n: secs.length, hero_px: hero, body_px: body,
          void_px: Math.round(voidpx), page_h: document.body.scrollHeight, tells: tells};
}"""


def render_metrics(kit_dir, page_file: str = "index.html", port: int = 8201) -> dict:
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
        with sync_playwright() as pw:
            b = pw.chromium.launch(headless=True)
            try:
                pg = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
                pg.goto(root + page_file, wait_until="load", timeout=20000)
                pg.wait_for_timeout(1500)
                raw = pg.evaluate(_EVAL)
            finally:
                b.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
    body = raw["body_px"] or 16
    return {
        "bleed_ratio": round(raw["bleed"] / raw["n"], 2) if raw["n"] else 0.0,  # advisory
        "hero_px": round(raw["hero_px"], 1),
        "body_px": body,
        "hero_scale_ratio": round(raw["hero_px"] / body, 1) if body else 0.0,
        "max_vertical_void_px": raw["void_px"],
        "page_height_px": raw["page_h"],
        "template_tells": raw["tells"],
    }
