#!/usr/bin/env python3
"""verify_bootstrap.py — Day 1 end-to-end foundation verification.

Runs six checks and writes a report to logs/day-1-bootstrap-report.md.
Exit code 0 if all pass, 1 if any fail.

Usage:
    /opt/scout-workshop/venv/bin/python scripts/verify_bootstrap.py
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import sys
import traceback
import uuid
from pathlib import Path

# Make scout_lib importable when run directly.
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import scout_lib as sl  # noqa: E402

ROOT = Path("/opt/scout-workshop")
LOGS = ROOT / "logs"
REPORT = LOGS / "day-1-bootstrap-report.md"
TEST_IMG = ROOT / "state" / "screenshots" / "test-embed.png"
TEST_SHOT = ROOT / "state" / "screenshots" / "test.png"

# Capture WARN+ messages from scout_lib so the report can include the
# underlying exception text from a multimodal-embedding fallback.
_captured_logs: list[str] = []


class _ListHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        _captured_logs.append(self.format(record))


_handler = _ListHandler()
_handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
_handler.setLevel(logging.WARNING)
_sw_logger = logging.getLogger("scout_workshop")
_sw_logger.addHandler(_handler)
_sw_logger.setLevel(logging.WARNING)
# Also stream to stderr so a human watching the run sees them in real time.
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def make_test_image() -> Path:
    """Generate a 128x128 red PNG for the multimodal embedding test."""
    from PIL import Image

    TEST_IMG.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (128, 128), color=(220, 60, 60)).save(TEST_IMG, "PNG")
    return TEST_IMG


def check_qdrant() -> tuple[bool, str]:
    try:
        client = sl.qdrant_client_init()
        info = client.get_collection(sl.COLLECTION)
        dim = info.config.params.vectors.size
        dist = info.config.params.vectors.distance.name
        if dim != sl.VECTOR_SIZE:
            return False, f"Wrong dim: {dim}"
        if dist.lower() != "cosine":
            return False, f"Wrong distance: {dist}"
        return True, f"dim={dim}, distance={dist}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def check_embedding_text() -> tuple[bool, str, list[float] | None]:
    try:
        vec = sl.embed("scout workshop foundation test")
        if len(vec) != sl.VECTOR_SIZE:
            return False, f"Wrong dim: {len(vec)}", None
        return True, f"len={len(vec)}, sample[:3]={vec[:3]}", vec
    except Exception as e:
        return False, f"{type(e).__name__}: {e}", None


def check_embedding_multimodal() -> tuple[bool, str, list[float] | None]:
    """Strict multimodal check.

    Calls embed_with_mode with a real test image and checks the returned mode.
    Treats "multimodal-fallback" as FAIL even though a usable vector came back —
    Day 1's job is to confirm the multimodal payload shape is correct against
    OpenRouter for google/gemini-embedding-2-preview. The fallback warning is
    emitted by scout_lib at WARN level and will appear in the captured logs.

    Returns:
        (passed, detail, vector). The vector is returned even on FAIL when a
        text-only fallback succeeded, so the round-trip check downstream can
        still exercise Qdrant.
    """
    try:
        img = make_test_image()
        vec, mode = sl.embed_with_mode("scout workshop foundation test", image_path=str(img))
        if len(vec) != sl.VECTOR_SIZE:
            return False, f"Wrong dim: {len(vec)}", None
        if mode != "multimodal":
            captured = [m for m in _captured_logs if "Multimodal embedding failed" in m]
            extra = f"\n\nCaptured warning: {captured[-1]}" if captured else ""
            return False, (
                f"Multimodal path FELL BACK to text-only (mode={mode!r}). "
                f"A usable text-only vector was returned, but the multimodal "
                f"payload shape was rejected by OpenRouter. Consult the TODO "
                f"comment in scout_lib._embed_multimodal() for the items to "
                f"verify against OpenRouter docs.{extra}"
            ), vec
        return True, (
            f"len={len(vec)}, mode={mode}, image={img.name}, "
            f"sample[:3]={vec[:3]}"
        ), vec
    except Exception as e:
        return False, f"{type(e).__name__}: {e}\n{traceback.format_exc()}", None


def check_qdrant_roundtrip(vec: list[float]) -> tuple[bool, str]:
    try:
        client = sl.qdrant_client_init()
        pid = str(uuid.uuid5(uuid.NAMESPACE_URL, "verify://bootstrap-roundtrip"))
        payload = {
            "reference_type": "technique",
            "vertical": "generic",
            "source_url": "verify://bootstrap-roundtrip",
            "scraped_at": utc_now(),
            "screenshot_path": "",
            "markdown_path": "",
            "distinctiveness_score": 0.0,
            "techniques": ["bootstrap-test"],
            "color_mood": "other",
            "typography_style": "other",
            "layout_pattern": "other",
            "language": "en",
            "notes_excerpt": "Day 1 round-trip probe",
        }
        sl.qdrant_insert(pid, vec, payload)
        hits = sl.qdrant_query(vec, limit=1)
        if not hits or str(hits[0].id) != pid:
            return False, f"Top hit was {hits[0].id if hits else 'none'}, expected {pid}"
        client.delete(collection_name=sl.COLLECTION, points_selector=[pid])
        return True, f"point_id={pid}, score={hits[0].score:.4f}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def check_telegram() -> tuple[bool, str]:
    try:
        sl.telegram_send(f"Day 1 foundation verified at {utc_now()}")
        return True, "Sent (visual confirmation required on phone)"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def check_firecrawl() -> tuple[bool, str]:
    try:
        result = sl.firecrawl_scrape("https://example.com")
        md_len = len(result.get("markdown", ""))
        title = result.get("metadata", {}).get("title", "")
        if md_len == 0:
            return False, "Empty markdown"
        if not title:
            return False, "Empty title"
        return True, f"markdown_len={md_len}, title={title!r}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def check_screenshot() -> tuple[bool, str]:
    try:
        path = sl.screenshot("https://example.com", output_path=str(TEST_SHOT))
        size = os.path.getsize(path)
        if size < 1024:
            return False, f"Too small: {size} bytes"
        return True, f"path={path}, size={size}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def main() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    started = utc_now()
    rows: list[tuple[str, bool, str]] = []

    # 1. Qdrant
    ok, detail = check_qdrant()
    rows.append(("Qdrant collection", ok, detail))

    # 2a. Embedding (text)
    ok, detail, _ = check_embedding_text()
    rows.append(("Embedding (text-only)", ok, detail))

    # 2b. Embedding (multimodal) — vector reused for round-trip below
    ok, detail, mm_vec = check_embedding_multimodal()
    rows.append(("Embedding (multimodal text+image)", ok, detail))

    # 3. Qdrant round-trip — only if multimodal embedding succeeded
    if mm_vec is not None:
        ok, detail = check_qdrant_roundtrip(mm_vec)
    else:
        ok, detail = False, "Skipped (no multimodal vector)"
    rows.append(("Qdrant insert + retrieve + delete", ok, detail))

    # 4. Telegram
    ok, detail = check_telegram()
    rows.append(("Telegram send", ok, detail))

    # 5. Firecrawl
    ok, detail = check_firecrawl()
    rows.append(("Firecrawl scrape (example.com)", ok, detail))

    # 6. Screenshot
    ok, detail = check_screenshot()
    rows.append(("Playwright screenshot (example.com)", ok, detail))

    finished = utc_now()
    all_pass = all(r[1] for r in rows)
    status = "PASSED" if all_pass else "FAILED"

    lines = [
        f"# Day 1 Bootstrap Verification — {status}",
        "",
        f"- Started:  {started}",
        f"- Finished: {finished}",
        f"- VPS:      srv1420550",
        f"- User:     {os.environ.get('USER', 'unknown')}",
        "",
        "| # | Check | Result | Detail |",
        "|---|---|---|---|",
    ]
    for i, (name, ok, detail) in enumerate(rows, 1):
        mark = "✓ PASS" if ok else "✗ FAIL"
        # Escape pipes in detail for table safety
        safe = detail.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {i} | {name} | {mark} | {safe} |")
    lines.append("")
    if all_pass:
        lines.append("All checks passed. Foundation is ready for Day 2 (Scout) and Day 3 (Workshop).")
    else:
        lines.append("One or more checks failed. Investigate before proceeding to Day 2.")
    lines.append("")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(REPORT.read_text(encoding="utf-8"))

    if all_pass:
        try:
            sl.telegram_send(
                f"Scout-Workshop Day 1 bootstrap complete ✓ "
                f"{len(rows)} checks passed at {finished}"
            )
        except Exception as e:
            print(f"WARNING: success telegram failed: {e}", file=sys.stderr)

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
