"""Model-free genericness proxy — deterministic template-vs-premium metrics.

Pulled forward from design §11 so the Phase 1a eyeball is backed by numbers
(and to seed the Phase 1b first-occurrence genericness gate). Parses a kit's
index.html + style.css; no rendering, no model call.
"""
from __future__ import annotations
import re
from pathlib import Path


def _read(kit_dir) -> tuple[str, str]:
    kd = Path(kit_dir)
    html = (kd / "index.html").read_text(encoding="utf-8") if (kd / "index.html").exists() else ""
    css_p = kd / "assets" / "css" / "style.css"
    css = css_p.read_text(encoding="utf-8") if css_p.exists() else ""
    return html, css


def score_kit(kit_dir) -> dict:
    html, css = _read(kit_dir)
    sections = re.findall(r"<section[^>]*>", html, re.I)
    n = len(sections) or 1
    bleed = sum(
        1 for s in sections
        if re.search(r'class="[^"]*(bleed|full|hero|plate|cover)', s, re.I)
        or "width:100vw" in s.replace(" ", "")
    )
    css_bleed = 1 if re.search(r"100vw", css) else 0
    bleed_ratio = round(min(1.0, (bleed + css_bleed) / n), 2)

    def _px(rem: str) -> float:
        return float(rem) * 16

    hero = 0.0
    m = re.search(r"clamp\([^)]*?,\s*[\d.]+\s*vw\s*,\s*([\d.]+)rem", css)
    if m:
        hero = _px(m.group(1))
    else:
        m2 = re.search(r"h1[^{]*\{[^}]*font-size:\s*([\d.]+)rem", css, re.I)
        if m2:
            hero = _px(m2.group(1))
    body = 16.0
    mb = re.search(r"body[^{]*\{[^}]*font-size:\s*([\d.]+)rem", css, re.I)
    if mb:
        body = _px(mb.group(1))
    hero_body_ratio = round(hero / body, 1) if body else 0.0

    tells: list[str] = []
    if re.search(r'class="[^"]*(trust|badge|avatar|testimonial)', html, re.I):
        tells.append("trust/badge block")
    cards = len(re.findall(r'class="[^"]*(card|service)', html, re.I))
    if cards >= 3:
        tells.append(f"{cards}-item card grid")
    if re.search(r'href="tel:', html, re.I):
        tells.append("click-to-call")
    if len(re.findall(r'class="[^"]*(\bcta\b|pill)', html, re.I)) >= 2:
        tells.append("repeated CTA/pill")

    verdict = ("premium-leaning"
               if (bleed_ratio >= 0.5 and hero_body_ratio >= 4 and len(tells) <= 1)
               else "template-leaning")
    return {
        "bleed_ratio": bleed_ratio,
        "hero_body_ratio": hero_body_ratio,
        "template_tells": tells,
        "verdict": verdict,
    }
