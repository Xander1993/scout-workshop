"""Static asset-hygiene gate: scan EVERY page of a kit and fail it (fail-CLOSED)
if it ships any of the three placeholder defects that the generator kept leaking
into delivered kits:

  1. an unsubstituted template token (``{{BRAND}}`` etc.) left in the markup,
  2. a ``picsum.photos`` URL standing in for a real image,
  3. a PLACEHOLDER-text image — an inline ``<svg>`` or a referenced local image
     file whose visible content is the literal word "PLACEHOLDER" (the SVG/text
     fake-screenshots the kit used before real images were generated),
  4. a broken image — a local image reference that points at a file which does
     not exist on disk (the browser renders a broken-image icon). Checked across
     every channel the browser actually fetches: ``<img src>``, ``<img srcset>``,
     ``<source src>``/``<source srcset>``, and ``url(...)`` image refs in inline
     ``<style>`` blocks, ``style="..."`` attributes, and external stylesheets
     (the latter resolved relative to the CSS file's own directory). Non-image
     ``url()`` refs (e.g. ``@font-face`` ``.woff2``) are out of scope.

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
# responsive / CSS image references that the browser also fetches from disk
_SRCSET_RE = re.compile(r'srcset=["\']([^"\']+)["\']', re.I)
_SOURCE_SRC_RE = re.compile(r'<source\b[^>]*\ssrc=["\']([^"\']+)["\']', re.I)
_STYLE_BLOCK_RE = re.compile(r"<style\b[^>]*>([\s\S]*?)</style>", re.I)
_STYLE_ATTR_RE = re.compile(r'style=["\']([^"\']*)["\']', re.I)
_CSS_URL_RE = re.compile(r"url\(\s*['\"]?([^)'\"]+?)['\"]?\s*\)", re.I)

# image files whose content is text we can read for a PLACEHOLDER marker
_TEXT_IMG_SUFFIXES = {".svg"}
_REMOTE_PREFIXES = ("http://", "https://", "data:", "mailto:", "tel:", "//", "#")
# extensions a broken-image disk check applies to (CSS url()/srcset also carry
# non-image refs like @font-face .woff2, which are out of scope for this gate)
_IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".avif", ".gif", ".svg")


def _missing_local_image(ref: str, base_dir: Path):
    """Return the cleaned ref if it names a *local image file* absent from disk
    (resolved relative to ``base_dir``), else None. Remote/data refs and
    non-image refs (fonts, etc.) are ignored."""
    clean = ref.split("?")[0].split("#")[0].strip()
    if not clean or clean.lower().startswith(_REMOTE_PREFIXES):
        return None
    if not clean.lower().endswith(_IMG_EXTS):
        return None
    return clean if not (base_dir / clean).is_file() else None


def _srcset_candidates(srcset: str):
    """Yield each URL token from a srcset value ("a.png 1x, b.png 2x")."""
    for cand in srcset.split(","):
        cand = cand.strip()
        if cand:
            yield cand.split()[0]


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
        # responsive image refs: <img srcset>, <source src/srcset>
        for srcset in _SRCSET_RE.findall(html):
            for cand in _srcset_candidates(srcset):
                miss = _missing_local_image(cand, hf.parent)
                if miss:
                    violations.append(f"{name}: {miss} is a missing image file")
        for src in _SOURCE_SRC_RE.findall(html):
            miss = _missing_local_image(src, hf.parent)
            if miss:
                violations.append(f"{name}: {miss} is a missing image file")
        # inline CSS image refs: <style> blocks and style="" attributes
        inline_css = _STYLE_BLOCK_RE.findall(html) + _STYLE_ATTR_RE.findall(html)
        for block in inline_css:
            for url in _CSS_URL_RE.findall(block):
                miss = _missing_local_image(url, hf.parent)
                if miss:
                    violations.append(f"{name}: {miss} is a missing image file")
    # external stylesheets: background-image:url() etc., resolved relative to the
    # CSS file's own directory (independent of the html `pages` filter)
    for cf in sorted(kit_dir.rglob("*.css")):
        rel = cf.relative_to(kit_dir).as_posix()
        css = cf.read_text(encoding="utf-8", errors="ignore")
        for url in _CSS_URL_RE.findall(css):
            miss = _missing_local_image(url, cf.parent)
            if miss:
                violations.append(f"{rel}: {miss} is a missing image file")
    return {
        "ok": not violations,
        "violations": violations,
        "pages": [h.name for h in html_files],
    }
