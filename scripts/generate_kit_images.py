#!/usr/bin/env python3
"""Workshop v1.1 — Gemini Nano Banana 2 image generation phase.

Pipeline position: between self_audit (phase 5) and capture_screenshots
(now phase 7). Reads image-prompts.json produced by generate_kit, calls
Gemini once per entry, validates JPEGs, falls back to SVG placeholders
on failure, and rewrites picsum.photos URLs in the kit's HTML to point
at the local images.

Hard-fails (raises ImageGenError) on:
  - NANOBANANA_API_KEY missing/empty
  - image-prompts.json missing or unparseable
  - Pillow (PIL) not installed

Soft-fails (per-image fallback to SVG) on:
  - 429 / 5xx after retries
  - non-retryable HTTP 4xx
  - PIL decode failure
  - aspect-ratio drift > 5%
  - mean-pixel-value < 10/255 (all-black detection)
  - daily quota exhausted (skips remaining API calls)
  - initial connectivity check fails (falls back ALL images)

Calibrated from Patch B probe findings (5 calls, 2026-05-09):
  - avg latency 23.4s, max 31.0s → timeout 90s gives 3× margin
  - responseModalities=IMAGE is set but does NOT suppress thoughtSignature;
    we discard the field after parse to free memory
  - aspect ratios 1:1/4:3/3:4 verified working with ~0.4% drift
"""
from __future__ import annotations

import base64
import io
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageStat


# ─────────────────────────────────────────────────────────────────────
# Constants — calibrated from Patch B probe; change deliberately
# ─────────────────────────────────────────────────────────────────────

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemini-3.1-flash-image-preview:generateContent"
)
GEMINI_MODEL_INFO_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemini-3.1-flash-image-preview"
)
GEMINI_TIMEOUT_S = 90
RATE_LIMIT_PAUSE_S = 2.5
GEMINI_RETRY_BACKOFFS_S = (5, 15, 60)
CONNECTIVITY_TIMEOUT_S = 15

GENERATION_PROMPT_PREFIX = (
    "Editorial wellness photography for restrained luxury beauty clinic. "
    "Soft natural lighting, warm cinematic palette, contemporary lifestyle "
    "aesthetic. No clinical settings, no surgical equipment, no medical "
    "apparel — this is considered self-care, not medical procedure. "
    "Consistent matte film finish, subtle organic grain. No text, no logos, "
    "no watermarks."
)
# v1.1 prefix above is preserved as the safe default for callers that don't
# pass aesthetic_direction (CLI debug entry, future scripts). v1.2 routes
# the prefix through _resolve_image_prefix() so each aesthetic gets a
# matching photographic register; see scripts/aesthetic_configs.py.


def _resolve_image_prefix(aesthetic_direction: str | None) -> str:
    """Look up the per-aesthetic image_prefix from aesthetic_configs; fall
    back to GENERATION_PROMPT_PREFIX (v1.1 behavior) when no aesthetic is
    provided OR when aesthetic_configs cannot be imported (defensive — e.g.
    if this module is invoked from a context where scripts/ isn't on
    sys.path yet).
    """
    if not aesthetic_direction:
        return GENERATION_PROMPT_PREFIX
    try:
        scripts_dir = Path("/opt/scout-workshop/scripts")
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        from aesthetic_configs import get_config  # noqa: WPS433
    except Exception as e:
        log.warning(
            "could not import aesthetic_configs (%r); falling back to v1.1 prefix",
            e,
        )
        return GENERATION_PROMPT_PREFIX
    cfg = get_config(aesthetic_direction)
    prefix = cfg.get("image_prefix") or GENERATION_PROMPT_PREFIX
    log.info(
        "image_prefix resolved for aesthetic %r → %r (%d chars)",
        aesthetic_direction, cfg.get("name", "?"), len(prefix),
    )
    return prefix

# Pixel dimensions per aspect ratio. Used for SVG placeholder canvas sizing.
# Values approximate Gemini's actual outputs (probe data) so SVG fallbacks
# match the dimension footprint generated images would have occupied.
ASPECT_DIMENSIONS = {
    "1:1": (1024, 1024),
    "4:3": (1200, 900),
    "3:4": (900, 1200),
    "16:9": (1280, 720),
    "9:16": (720, 1280),
}
ALLOWED_ASPECTS = frozenset(ASPECT_DIMENSIONS)
REQUIRED_FIELDS = ("html_path", "alt_text", "generation_prompt", "aspect_ratio", "placement")

ALL_BLACK_THRESHOLD = 10.0  # mean pixel 0..255 must exceed this
ASPECT_TOLERANCE = 0.05     # 5% drift allowed

# Picsum URL pattern: extract seed from any picsum.photos/seed/{X}/{w}/{h} URL
PICSUM_URL_RE = re.compile(r"https://picsum\.photos/seed/([a-zA-Z0-9_-]+)/\d+/\d+")

log = logging.getLogger("workshop.image_gen")


class ImageGenError(RuntimeError):
    """Raised for hard failures (config, manifest, missing PIL).
    Per-image failures are handled internally with SVG fallback."""


# ─────────────────────────────────────────────────────────────────────
# Config / connectivity preflight
# ─────────────────────────────────────────────────────────────────────

def _load_api_key() -> str:
    """Load NANOBANANA_API_KEY via scout_lib.load_env (parses the same .env
    that workshop.py uses). Hard-fails if missing or empty."""
    try:
        scripts_dir = Path("/opt/scout-workshop/scripts")
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        import scout_lib as sl
        env = sl.load_env()
        key = (env.get("NANOBANANA_API_KEY") or "").strip()
    except Exception as e:
        raise ImageGenError(
            f"could not load .env to read NANOBANANA_API_KEY: {e!r}"
        ) from e
    if not key:
        raise ImageGenError(
            "NANOBANANA_API_KEY missing or empty in .env — image generation "
            "cannot proceed. Add the key and retry; do NOT silently fall back "
            "to all-placeholders."
        )
    return key


def check_connectivity(api_key: str) -> tuple[bool, str]:
    """Single short GET to verify endpoint is reachable AND the key is valid.
    Returns (ok, reason). Never raises."""
    try:
        r = requests.get(
            f"{GEMINI_MODEL_INFO_URL}?key={api_key}",
            timeout=CONNECTIVITY_TIMEOUT_S,
        )
        if r.status_code == 200:
            return True, "ok"
        return False, f"http {r.status_code}: {r.text[:200]}"
    except requests.exceptions.RequestException as e:
        return False, f"network error: {e!r}"


# ─────────────────────────────────────────────────────────────────────
# Manifest validation
# ─────────────────────────────────────────────────────────────────────

def _validate_manifest(
    manifest: Any, ipj_path: Path, run_dir: Path,
) -> dict[str, dict[str, Any]]:
    """Return manifest if valid; raise ImageGenError with raw saved on failure."""
    issues: list[str] = []
    if not isinstance(manifest, dict):
        issues.append(f"root not an object (type={type(manifest).__name__})")
    else:
        for key, entry in manifest.items():
            if not isinstance(entry, dict):
                issues.append(f"{key}: entry not an object")
                continue
            for f in REQUIRED_FIELDS:
                if f not in entry:
                    issues.append(f"{key}: missing field {f!r}")
            ar = entry.get("aspect_ratio")
            if ar is not None and ar not in ALLOWED_ASPECTS:
                issues.append(f"{key}: aspect_ratio {ar!r} not in {sorted(ALLOWED_ASPECTS)}")
    if issues:
        raw = run_dir / "raw_image_prompts.json"
        try:
            raw.write_text(ipj_path.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass
        head = "; ".join(issues[:5]) + (" …" if len(issues) > 5 else "")
        raise ImageGenError(
            f"image-prompts.json failed schema validation "
            f"({len(issues)} issues; raw at {raw}): {head}"
        )
    return manifest  # type: ignore[return-value]


# ─────────────────────────────────────────────────────────────────────
# One-call Gemini wrapper with retry on 429/5xx
# ─────────────────────────────────────────────────────────────────────

def _generate_one(prompt: str, aspect_ratio: str, api_key: str) -> bytes:
    """POST → base64 decode → JPEG bytes. Retries on 429/5xx per
    GEMINI_RETRY_BACKOFFS_S. Discards thoughtSignature immediately."""
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": aspect_ratio},
        },
    }
    last_err = "no attempts made"
    # First attempt has no backoff; subsequent retries use the spec'd backoffs
    schedule = [0, *GEMINI_RETRY_BACKOFFS_S]
    for attempt_idx, backoff in enumerate(schedule):
        if backoff > 0:
            log.info("retry %d/%d for aspect=%s after %ds backoff",
                     attempt_idx, len(schedule) - 1, aspect_ratio, backoff)
            time.sleep(backoff)
        try:
            r = requests.post(
                f"{GEMINI_URL}?key={api_key}",
                json=body,
                timeout=GEMINI_TIMEOUT_S,
            )
        except requests.exceptions.Timeout:
            last_err = f"timeout after {GEMINI_TIMEOUT_S}s (attempt {attempt_idx})"
            log.warning(last_err)
            continue
        except requests.exceptions.RequestException as e:
            last_err = f"network error (attempt {attempt_idx}): {e!r}"
            log.warning(last_err)
            continue

        if r.status_code == 200:
            try:
                data = r.json()
                part = data["candidates"][0]["content"]["parts"][0]
                # discard thoughtSignature immediately to free ~1 MB per call
                part.pop("thoughtSignature", None)
                b64 = part["inlineData"]["data"]
                return base64.b64decode(b64)
            except (KeyError, IndexError, ValueError, TypeError) as e:
                raise ImageGenError(
                    f"malformed 200 response: {e!r}; body[:300]={r.text[:300]}"
                ) from e

        if r.status_code in (429, 500, 502, 503, 504):
            last_err = f"http {r.status_code}: {r.text[:300]}"
            log.warning("retry-eligible attempt %d: %s", attempt_idx, last_err)
            continue

        # non-retryable 4xx
        raise ImageGenError(
            f"non-retryable http {r.status_code}: {r.text[:500]}"
        )

    raise ImageGenError(f"exhausted retries; last_err={last_err}")


# ─────────────────────────────────────────────────────────────────────
# Image validation
# ─────────────────────────────────────────────────────────────────────

def _validate_image(jpeg_bytes: bytes, expected_aspect: str) -> tuple[bool, str]:
    """Return (ok, reason). Validates: PIL decode, aspect drift ≤5%, not-all-black."""
    try:
        img = Image.open(io.BytesIO(jpeg_bytes))
        img.load()
    except Exception as e:
        return False, f"PIL decode failed: {e!r}"
    w, h = img.size
    if w <= 0 or h <= 0:
        return False, f"invalid dimensions {w}×{h}"
    actual = w / h
    tw, th = (int(x) for x in expected_aspect.split(":"))
    target = tw / th
    drift = abs(actual - target) / target
    if drift > ASPECT_TOLERANCE:
        return False, (
            f"aspect drift {drift:.2%} > {ASPECT_TOLERANCE:.0%} "
            f"(got {w}×{h}={actual:.3f}, expected {expected_aspect}={target:.3f})"
        )
    rgb = img.convert("RGB")
    mean = sum(ImageStat.Stat(rgb).mean) / 3.0
    if mean < ALL_BLACK_THRESHOLD:
        return False, f"image too dark: mean pixel {mean:.1f}/255 < {ALL_BLACK_THRESHOLD}"
    return True, f"ok ({w}×{h}, mean={mean:.0f})"


# ─────────────────────────────────────────────────────────────────────
# SVG fallback placeholder
# ─────────────────────────────────────────────────────────────────────

_PALETTE_RE = re.compile(
    r"--color-(\w+).*?[`'\"]?(#[0-9A-Fa-f]{6})", re.IGNORECASE,
)


def _parse_palette_from_brief(brief_path: Path) -> dict[str, str]:
    """Best-effort extract of `--color-{name}: #XXXXXX` pairs from brief.md.
    Returns empty dict on file-missing or no matches; caller should fallback."""
    out: dict[str, str] = {}
    if not brief_path.exists():
        return out
    try:
        for line in brief_path.read_text(encoding="utf-8").splitlines():
            m = _PALETTE_RE.search(line)
            if m:
                out[m.group(1).lower()] = m.group(2)
    except Exception as e:
        log.warning("palette parse failed (using neutral fallback): %s", e)
    return out


def _xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
              .replace(">", "&gt;").replace('"', "&quot;"))


def _wrap_text(s: str, width: int = 60, max_lines: int = 6) -> list[str]:
    """Naive word-wrap. Truncates with ellipsis if exceeding max_lines."""
    words = s.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            if cur:
                lines.append(cur)
            cur = w
            if len(lines) >= max_lines - 1:
                lines.append(cur + " …")
                return lines
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines


def make_placeholder_svg(
    image_id: str, entry: dict[str, Any], palette: dict[str, str],
) -> str:
    """Render an SVG placeholder: gradient bg, hatched corner, PLACEHOLDER tag,
    prompt text in middle. Visually distinct from generated images."""
    aspect_ratio = entry.get("aspect_ratio", "4:3")
    if aspect_ratio not in ASPECT_DIMENSIONS:
        aspect_ratio = "4:3"
    w, h = ASPECT_DIMENSIONS[aspect_ratio]

    bg1 = palette.get("surface") or "#E0DCD4"
    bg2 = palette.get("bg") or "#F5EDE2"
    accent = palette.get("accent") or "#888888"
    fg = palette.get("fg") or "#3A3A3A"

    prompt_text = (entry.get("generation_prompt") or "")[:400]
    text_lines = _wrap_text(prompt_text, width=58, max_lines=6)
    line_height = max(18, int(h * 0.025))
    block_h = line_height * len(text_lines)
    text_y0 = (h - block_h) // 2 + line_height

    text_lines_svg = "\n".join(
        f'  <text x="50%" y="{text_y0 + i * line_height}" '
        f'font-family="Georgia, serif" font-size="{int(line_height * 0.78)}" '
        f'fill="{fg}" text-anchor="middle" opacity="0.7">'
        f'{_xml_escape(line)}</text>'
        for i, line in enumerate(text_lines)
    )

    stripe_w = w // 4
    stripe_h = h // 4

    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid slice">
  <defs>
    <linearGradient id="bg-{_xml_escape(image_id)}" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{bg1}"/>
      <stop offset="100%" stop-color="{bg2}"/>
    </linearGradient>
    <pattern id="hatch-{_xml_escape(image_id)}" patternUnits="userSpaceOnUse" width="14" height="14" patternTransform="rotate(45)">
      <line x1="0" y1="0" x2="0" y2="14" stroke="{accent}" stroke-width="3" opacity="0.5"/>
    </pattern>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg-{_xml_escape(image_id)})"/>
  <rect x="{w - stripe_w}" y="0" width="{stripe_w}" height="{stripe_h}" fill="url(#hatch-{_xml_escape(image_id)})"/>
  <text x="32" y="48" font-family="Georgia, serif" font-size="18" font-weight="600" fill="{accent}" letter-spacing="2">PLACEHOLDER</text>
  <text x="32" y="74" font-family="Georgia, serif" font-size="12" fill="{fg}" opacity="0.5">id: {_xml_escape(image_id)} · {aspect_ratio}</text>
{text_lines_svg}
</svg>
"""
    return svg


# ─────────────────────────────────────────────────────────────────────
# URL replacement in HTML
# ─────────────────────────────────────────────────────────────────────

def _replace_picsum_in_html(
    kit_dir: Path, image_id_to_path: dict[str, str],
) -> dict[str, int]:
    """For each HTML page, replace picsum URLs whose seed matches a known
    image-id. Returns {filename: replacements_made}."""
    counts: dict[str, int] = {}
    for fname in ("index.html", "services.html", "contacts.html"):
        f = kit_dir / fname
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8")
        replaced = [0]
        def _sub(m: re.Match) -> str:
            seed = m.group(1)
            target = image_id_to_path.get(seed)
            if target:
                replaced[0] += 1
                return target
            return m.group(0)
        new_text = PICSUM_URL_RE.sub(_sub, text)
        if new_text != text:
            f.write_text(new_text, encoding="utf-8")
        counts[fname] = replaced[0]
    return counts


def _count_remaining_picsum(kit_dir: Path) -> int:
    total = 0
    for fname in ("index.html", "services.html", "contacts.html"):
        f = kit_dir / fname
        if f.exists():
            total += len(PICSUM_URL_RE.findall(f.read_text(encoding="utf-8")))
    return total


# ─────────────────────────────────────────────────────────────────────
# Audit post-processing
# ─────────────────────────────────────────────────────────────────────

def strip_picsum_audit_concerns(audit_md_path: Path) -> int:
    """Remove lines mentioning picsum.photos under '## Lighthouse concerns'
    AND under '## Warnings'. Both sections may carry stale picsum complaints
    that the auditor wrote against the pre-replacement HTML; once image-gen
    has run successfully, those complaints no longer reflect reality.

    Conservative: leave file unchanged on any anomaly. Returns total count
    removed across both sections."""
    if not audit_md_path.exists():
        return 0
    STRIP_SECTIONS = ("## Lighthouse concerns", "## Warnings")
    try:
        text = audit_md_path.read_text(encoding="utf-8")
        lines = text.split("\n")
        out: list[str] = []
        in_strip_section = False
        removed = 0
        for line in lines:
            stripped = line.lstrip()
            if any(stripped.startswith(h) for h in STRIP_SECTIONS):
                in_strip_section = True
                out.append(line)
                continue
            if in_strip_section and stripped.startswith("## "):
                in_strip_section = False
            if in_strip_section and "picsum.photos" in line:
                removed += 1
                continue
            out.append(line)
        if removed > 0:
            audit_md_path.write_text("\n".join(out), encoding="utf-8")
        return removed
    except Exception as e:
        log.warning("audit strip failed (leaving unchanged): %s", e)
        return 0


# ─────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────

def generate_kit_images(
    kit_dir: Path, run_dir: Path,
    aesthetic_direction: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Generate or fall-back-placehold every image referenced by the kit's
    image-prompts.json. Rewrites picsum URLs in HTML to local paths.

    `aesthetic_direction` (v1.2) selects the per-aesthetic image prefix from
    scripts/aesthetic_configs.py — replaces the v1.1 hardcoded warm-cream
    GENERATION_PROMPT_PREFIX. When None (e.g. from the CLI debug entry), falls
    back to GENERATION_PROMPT_PREFIX so legacy invocations keep working.

    Returns {image_id: {"status": "success"|"fallback"|"failed",
                         "path": "...", "error": "..."}}.

    Raises ImageGenError on hard config failures (no key, no manifest, no PIL).
    Per-image errors are caught and result in SVG fallback.
    """
    # PIL was already imported at module top; this is just a defensive recheck.
    try:
        import PIL  # noqa: F401
    except ImportError as e:  # pragma: no cover
        raise ImageGenError(f"Pillow not installed: {e!r}; pip install Pillow") from e

    ipj_path = kit_dir / "image-prompts.json"
    if not ipj_path.exists() or ipj_path.stat().st_size == 0:
        raise ImageGenError(f"image-prompts.json missing or empty at {ipj_path}")
    try:
        manifest_raw = json.loads(ipj_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raw = run_dir / "raw_image_prompts.json"
        try:
            raw.write_text(ipj_path.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass
        raise ImageGenError(
            f"image-prompts.json parse failed: {e}; raw at {raw}"
        ) from e
    manifest = _validate_manifest(manifest_raw, ipj_path, run_dir)

    api_key = _load_api_key()  # raises if missing

    # Resolve per-aesthetic prefix once for this kit. All images in the kit
    # share the same photographic register; the per-image differentiation is
    # in the manifest's generation_prompt field.
    image_prefix = _resolve_image_prefix(aesthetic_direction)

    images_dir = kit_dir / "assets" / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    palette = _parse_palette_from_brief(run_dir / "brief.md")
    log.info("palette parsed from brief.md: %s", palette or "(none — using neutral)")

    api_ok, api_reason = check_connectivity(api_key)
    if not api_ok:
        log.error("Gemini connectivity preflight failed: %s — falling back ALL %d images",
                  api_reason, len(manifest))

    daily_quota_exceeded = False
    consecutive_429 = 0

    statuses: dict[str, dict[str, Any]] = {}
    image_id_to_path: dict[str, str] = {}

    for image_id, entry in manifest.items():
        out_jpg = images_dir / f"{image_id}.jpg"
        out_svg = images_dir / f"{image_id}.svg"
        aspect = entry.get("aspect_ratio", "4:3")
        full_prompt = image_prefix + " " + entry["generation_prompt"]

        # short-circuit: no API → straight to SVG
        if not api_ok or daily_quota_exceeded:
            reason = "api_unavailable" if not api_ok else "daily_quota_exceeded"
            try:
                out_svg.write_text(
                    make_placeholder_svg(image_id, entry, palette),
                    encoding="utf-8",
                )
                image_id_to_path[image_id] = f"assets/images/{image_id}.svg"
                statuses[image_id] = {
                    "status": "fallback", "path": str(out_svg), "error": reason,
                }
            except Exception as e:
                statuses[image_id] = {
                    "status": "failed", "path": None,
                    "error": f"svg-write failed: {e!r}",
                }
            continue

        # call Gemini
        try:
            jpeg_bytes = _generate_one(full_prompt, aspect, api_key)
        except ImageGenError as e:
            err_str = str(e)
            log.warning("image %s API call failed: %s", image_id, err_str)
            # 429 + quota indicators trigger global fallback
            if "429" in err_str:
                consecutive_429 += 1
                lower = err_str.lower()
                if any(kw in lower for kw in ("daily", "quota", "resource_exhausted")):
                    daily_quota_exceeded = True
                    log.error("daily quota indicators in 429 — flipping to fallback-all")
                elif consecutive_429 >= 3:
                    daily_quota_exceeded = True
                    log.error("3+ consecutive 429s — flipping to fallback-all defensively")
            try:
                out_svg.write_text(
                    make_placeholder_svg(image_id, entry, palette),
                    encoding="utf-8",
                )
                image_id_to_path[image_id] = f"assets/images/{image_id}.svg"
                statuses[image_id] = {
                    "status": "fallback", "path": str(out_svg),
                    "error": err_str[:300],
                }
            except Exception as svg_err:
                statuses[image_id] = {
                    "status": "failed", "path": None,
                    "error": f"api+svg both failed: api={err_str[:200]} svg={svg_err!r}",
                }
            time.sleep(RATE_LIMIT_PAUSE_S)
            continue

        # API call succeeded — reset 429 counter and validate
        consecutive_429 = 0
        ok, reason = _validate_image(jpeg_bytes, aspect)
        if not ok:
            log.warning("image %s validation failed: %s — falling back", image_id, reason)
            try:
                out_svg.write_text(
                    make_placeholder_svg(image_id, entry, palette),
                    encoding="utf-8",
                )
                image_id_to_path[image_id] = f"assets/images/{image_id}.svg"
                statuses[image_id] = {
                    "status": "fallback", "path": str(out_svg),
                    "error": f"validation: {reason}",
                }
            except Exception as svg_err:
                statuses[image_id] = {
                    "status": "failed", "path": None,
                    "error": f"validation+svg both failed: validation={reason}, svg={svg_err!r}",
                }
            time.sleep(RATE_LIMIT_PAUSE_S)
            continue

        # write JPEG
        try:
            out_jpg.write_bytes(jpeg_bytes)
            image_id_to_path[image_id] = f"assets/images/{image_id}.jpg"
            statuses[image_id] = {
                "status": "success", "path": str(out_jpg), "error": None,
            }
            log.info("image %s ok: %s", image_id, reason)
        except Exception as e:
            log.warning("image %s jpeg write failed: %s — falling back", image_id, e)
            try:
                out_svg.write_text(
                    make_placeholder_svg(image_id, entry, palette),
                    encoding="utf-8",
                )
                image_id_to_path[image_id] = f"assets/images/{image_id}.svg"
                statuses[image_id] = {
                    "status": "fallback", "path": str(out_svg),
                    "error": f"jpeg-write failed: {e!r}",
                }
            except Exception as svg_err:
                statuses[image_id] = {
                    "status": "failed", "path": None,
                    "error": f"jpeg+svg both failed: {e!r} / {svg_err!r}",
                }

        time.sleep(RATE_LIMIT_PAUSE_S)

    # rewrite picsum URLs in HTML
    counts = _replace_picsum_in_html(kit_dir, image_id_to_path)
    log.info("URL replacements per file: %s", counts)
    leftover = _count_remaining_picsum(kit_dir)
    if leftover > 0:
        log.warning("%d picsum URL(s) remain in HTML after replacement", leftover)
    else:
        log.info("0 picsum URLs remaining in HTML — replacement complete")

    return statuses


# ─────────────────────────────────────────────────────────────────────
# CLI entry (for debugging only — not used by workshop.py)
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":  # pragma: no cover
    import argparse
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--kit-dir", required=True, type=Path)
    p.add_argument("--run-dir", required=True, type=Path)
    p.add_argument(
        "--aesthetic", default=None,
        help="aesthetic_direction (e.g. modern-minimal, modern-minimal-v2). "
             "Selects the per-aesthetic image prefix from aesthetic_configs.py. "
             "Omit to fall back to the v1.1 hardcoded prefix.",
    )
    args = p.parse_args()
    out = generate_kit_images(args.kit_dir, args.run_dir,
                              aesthetic_direction=args.aesthetic)
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "path"}
                      for k, v in out.items()}, indent=2))
