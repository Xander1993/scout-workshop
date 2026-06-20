"""Static asset-hygiene gate: scan EVERY page of a kit and fail it (fail-CLOSED)
if it ships any of the three placeholder defects that the generator kept leaking
into delivered kits:

  1. an unsubstituted template token (``{{BRAND}}`` etc.) left in the markup,
  2. a ``picsum.photos`` URL standing in for a real image,
  3. a PLACEHOLDER-text image — an inline ``<svg>`` or a referenced local image
     file whose visible content is the literal word "PLACEHOLDER" (the SVG/text
     fake-screenshots the kit used before real images were generated),
  4. a broken image — an ``<img>`` whose local ``src`` points at a file that
     does not exist on disk (the browser renders a broken-image icon).

This is a *static* complement to ``assets_gate.py`` (which executes the page for
JS-runtime defects). Where the runtime gate fails OPEN so a Playwright hiccup
can't flag a good kit, this gate is wired fail-CLOSED at the call site: a kit
that ships a placeholder image is broken and must never pass.
"""
from __future__ import annotations
import re
from pathlib import Path

_TOKEN_RE = re.compile(r"\{\{[^{}]+\}\}")
_PICSUM_RE = re.compile(r"picsum\.photos", re.I)
_PLACEHOLDER_RE = re.compile(r"\bPLACEHOLDER\b", re.I)
_INLINE_SVG_RE = re.compile(r"<svg\b[\s\S]*?</svg>", re.I)
_IMG_SRC_RE = re.compile(r'<img[^>]*\ssrc=["\']([^"\']+)["\']', re.I)

# image files whose content is text we can read for a PLACEHOLDER marker
_TEXT_IMG_SUFFIXES = {".svg"}
_REMOTE_PREFIXES = ("http://", "https://", "data:", "mailto:", "tel:", "//", "#")


def check_assets(kit_dir, pages=None) -> dict:
    """Return {ok, violations, pages}. ok is False if any page ships a token,
    a picsum URL, or a PLACEHOLDER-text image."""
    kit_dir = Path(kit_dir)
    html_files = sorted(p for p in kit_dir.glob("*.html"))
    if pages is not None:
        wanted = {p if p.endswith(".html") else f"{p}.html" for p in pages}
        html_files = [h for h in html_files if h.name in wanted]
    violations: list[str] = []
    for hf in html_files:
        html = hf.read_text(encoding="utf-8", errors="ignore")
        name = hf.name
        for tok in sorted(set(_TOKEN_RE.findall(html))):
            violations.append(f"{name}: unsubstituted template token {tok}")
        if _PICSUM_RE.search(html):
            violations.append(f"{name}: picsum.photos placeholder image URL")
        for svg in _INLINE_SVG_RE.findall(html):
            if _PLACEHOLDER_RE.search(svg):
                violations.append(f"{name}: inline SVG with PLACEHOLDER text")
                break
        for src in _IMG_SRC_RE.findall(html):
            clean = src.split("?")[0].split("#")[0]
            if clean.lower().startswith(_REMOTE_PREFIXES) or not clean:
                continue
            target = (hf.parent / clean)
            if not target.is_file():
                violations.append(f"{name}: {src} is a missing image file")
                continue
            if target.suffix.lower() in _TEXT_IMG_SUFFIXES:
                body = target.read_text(encoding="utf-8", errors="ignore")
                if _PLACEHOLDER_RE.search(body):
                    violations.append(f"{name}: {src} is a PLACEHOLDER image")
    return {
        "ok": not violations,
        "violations": violations,
        "pages": [h.name for h in html_files],
    }
