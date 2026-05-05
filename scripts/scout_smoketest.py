#!/usr/bin/env python3
"""Day 2 smoketest: prove every new code path works without an actual Scout run.

Steps:
1. Generate a synthetic reference note (title, frontmatter, fake screenshot)
   under STATE_DIR/_smoketest/ — outside the vault, so cleanup failure cannot
   leak artifacts into the daemon's production walk.
2. Confirm find_unembedded_notes(vault_root=SMOKE_ROOT) picks it up.
3. Run process_one() against it (real OpenRouter call, real Qdrant upsert).
4. Idempotency contract: mutate frontmatter, run process_one() again, assert
   that the Qdrant vector did NOT change (no re-embed) and the payload DID
   update (drift reconciled via set_payload).
5. Run a Cohere rerank smoke call.
6. Send a "Day 2 smoketest OK" Telegram message.
7. Clean up: rmtree the fake-vault root, delete the Qdrant point.

Cleanup runs on BOTH success and failure paths via try/finally — so a partial
run doesn't leave a phantom point in the scout_workshop collection.

Exits 0 on full pass, 2 on assertion failure, non-zero on unhandled error.

CLI:
    python scout_smoketest.py                            # full smoketest
    python scout_smoketest.py --validate-playbook PATH   # YAML+sections check only
"""
from __future__ import annotations

import argparse
import sys
import shutil
import time
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scout_lib import (  # type: ignore
    STATE_DIR, COLLECTION_NAME,
    write_note, find_unembedded_notes,
    qdrant_client, rerank,
    send_telegram, iso_now,
    stable_url_hash, stable_point_id, reference_slug,
)
from ingest_daemon import process_one  # type: ignore

import yaml

SMOKE_URL = "https://example.com/scout-smoketest"
# Fake-vault root: outside VAULT_DIR, inside the gitignored local state dir.
# Daemon's production find_unembedded_notes(VAULT_DIR) never walks here.
SMOKE_ROOT = STATE_DIR / "_smoketest"
SMOKE_REF_DIR = SMOKE_ROOT / "references" / "_smoketest_source"


def make_fake_screenshot(path: Path) -> None:
    img = Image.new("RGB", (1280, 800), color=(28, 27, 26))
    d = ImageDraw.Draw(img)
    d.rectangle([(40, 40), (640, 240)], fill=(217, 196, 165))
    d.text((80, 120), "SCOUT SMOKETEST", fill=(28, 27, 26))
    img.save(path, "PNG")


def build_synthetic_note() -> Path:
    slug = reference_slug(SMOKE_URL, "scout smoketest reference")
    note_dir = SMOKE_REF_DIR / slug
    note_dir.mkdir(parents=True, exist_ok=True)
    make_fake_screenshot(note_dir / "screenshot.png")

    point_id = stable_point_id(SMOKE_URL)  # UUID v5, the Qdrant point ID
    fm = {
        "id": point_id,
        "source": "smoketest",
        "source_url": SMOKE_URL,
        "scraped_at": iso_now(),
        "title": "Scout Smoketest Reference",
        "vertical": "general",
        "reference_type": "studio_site",
        "techniques": ["asymmetric grid", "warm earth palette", "editorial serif headlines"],
        "color_mood": "warm-earth",
        "typography_style": "editorial-serif",
        "layout_pattern": "hero-fold + alternating split",
        "palette_hex": ["#1c1b1a", "#d9c4a5", "#8a6f4f"],
        "qdrant_point_id": None,
        "embedded_at": None,
        "screenshot_path": "./screenshot.png",
    }
    body = (
        "Synthetic reference for the Day 2 smoketest. "
        "If this shows up in Qdrant, the ingestion path works.\n\n"
        "## Signals\n\n"
        "- earthy palette; restrained luxury feel\n"
        "- generous gutters; left-justified body\n"
    )
    note_path = note_dir / "note.md"
    write_note(note_path, fm, body)
    return note_path


def cleanup(point_id: str) -> None:
    """Best-effort cleanup. Called from finally — must not raise.

    smoketest lives under STATE_DIR (gitignored, never committed), so no
    git operations are needed. Just rmtree the fake-vault root and delete
    the Qdrant point.
    """
    errs = []
    if SMOKE_ROOT.exists():
        try:
            shutil.rmtree(SMOKE_ROOT)
        except Exception as e:
            errs.append(f"smoke root: {e}")
    try:
        qdrant_client().delete(
            collection_name=COLLECTION_NAME,
            points_selector=[point_id],
        )
    except Exception as e:
        errs.append(f"qdrant point: {e}")
    if errs:
        print(f"  ⚠ cleanup partial: {'; '.join(errs)}", file=sys.stderr)
    else:
        print("  ✓ cleanup done")


def _run() -> None:
    """Inner runner. Raises on failure; cleanup is wrapped by main()."""
    print("== Day 2 smoketest ==")
    note_path = build_synthetic_note()
    print(f"  ✓ wrote synthetic note: {note_path}")

    pending = find_unembedded_notes(vault_root=SMOKE_ROOT)
    assert pending, "find_unembedded_notes did not pick up the smoke note"
    assert note_path in pending, f"smoke note not in pending list: {pending}"
    print(f"  ✓ find_unembedded_notes saw it ({len(pending)} total pending)")

    ok, pid = process_one(note_path, dry_run=False)
    assert ok and pid, f"process_one failed: ok={ok} pid={pid}"
    print(f"  ✓ process_one embedded + upserted: {pid}")
    assert pid == stable_point_id(SMOKE_URL), (
        f"point_id drift: process_one returned {pid}, "
        f"stable_point_id says {stable_point_id(SMOKE_URL)}"
    )

    time.sleep(0.5)  # tiny pause for eventual consistency
    res = qdrant_client().retrieve(
        collection_name=COLLECTION_NAME, ids=[pid],
        with_payload=True, with_vectors=True,
    )
    assert res, "Qdrant retrieve returned empty"
    print(f"  ✓ Qdrant retrieved: payload keys = {sorted(res[0].payload.keys())}")
    original_vector = res[0].vector

    # ---- Idempotency contract: second process_one must NOT re-embed ----
    from scout_lib import parse_note as _parse, write_note as _write
    fm2, body2 = _parse(note_path)
    fm2["techniques"] = list(fm2["techniques"]) + ["drift-test-marker"]
    fm2["qdrant_point_id"] = None  # pretend the daemon doesn't know it's indexed
    fm2["embedded_at"] = None
    _write(note_path, fm2, body2)

    ok2, pid2 = process_one(note_path, dry_run=False)
    assert ok2 and pid2 == pid, "second process_one returned different result"

    res2 = qdrant_client().retrieve(
        collection_name=COLLECTION_NAME, ids=[pid],
        with_payload=True, with_vectors=True,
    )
    assert res2, "Qdrant retrieve empty after second process_one"
    assert res2[0].vector == original_vector, (
        "VECTOR CHANGED after second process_one — re-embed happened, "
        "idempotency contract violated"
    )
    assert "drift-test-marker" in (res2[0].payload.get("techniques") or []), (
        "payload did NOT update — drift detection failed"
    )
    print("  ✓ idempotency: 2nd process_one set_payload (drift), did not re-embed")
    # ---- end idempotency check ----

    t0 = time.time()
    results = rerank(
        query="warm earthy salon landing page",
        candidates=[
            "A high-contrast tech SaaS landing page in cool blues.",
            "Editorial serif typography over a muted earth-tone palette.",
            "Minimal monochrome agency portfolio with grotesque type.",
        ],
        top_n=3,
    )
    assert results, "rerank returned empty"
    print(f"  ✓ rerank ok: top score={results[0].get('relevance_score'):.3f} in {time.time()-t0:.2f}s")

    send_telegram(f"✅ Day 2 smoketest OK · point_id={pid} · {iso_now()}")
    print("  ✓ Telegram sent")


def validate_playbook(path: Path) -> int:
    """Phase 2 check 6: confirm the playbook's YAML frontmatter parses and
    the required sections are present. Exits 0 on pass, non-zero on fail.
    """
    REQUIRED_SECTIONS = [
        "## 1. Bootstrap",
        "## 2. Discover",
        "## 3. Process",
        "## 4. Close out",
        "## 5. Telegram digest",
        "## 6. Error handling",
        "## 7. What this playbook does NOT do",
    ]
    REQUIRED_FRONTMATTER_KEYS = [
        "name", "version", "phase", "budget_tokens_per_run",
        "max_references_per_run", "firecrawl_cooldown_seconds",
    ]

    if not path.exists():
        print(f"FAIL: playbook not found at {path}", file=sys.stderr)
        return 1

    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        print("FAIL: playbook missing YAML frontmatter delimiter", file=sys.stderr)
        return 1

    try:
        _, fm_block, body = text.split("---\n", 2)
    except ValueError:
        print("FAIL: playbook frontmatter delimiter malformed", file=sys.stderr)
        return 1

    try:
        fm = yaml.safe_load(fm_block)
    except yaml.YAMLError as e:
        print(f"FAIL: frontmatter is not valid YAML: {e}", file=sys.stderr)
        return 1

    missing_keys = [k for k in REQUIRED_FRONTMATTER_KEYS if k not in fm]
    if missing_keys:
        print(f"FAIL: frontmatter missing keys: {missing_keys}", file=sys.stderr)
        return 1

    missing_sections = [s for s in REQUIRED_SECTIONS if s not in body]
    if missing_sections:
        print(f"FAIL: body missing sections: {missing_sections}", file=sys.stderr)
        return 1

    print(f"  ✓ frontmatter keys: {sorted(fm.keys())}")
    print(f"  ✓ all {len(REQUIRED_SECTIONS)} required sections present")
    print("PASS: playbook validates")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate-playbook", metavar="PATH",
                    help="Validate a playbook file's YAML frontmatter and required sections, then exit.")
    args = ap.parse_args()

    if args.validate_playbook:
        return validate_playbook(Path(args.validate_playbook))

    # Compute the point_id up front so cleanup can use it even if _run raises
    # before pid is bound. The function is deterministic so this is safe.
    point_id = stable_point_id(SMOKE_URL)
    rc = 0
    try:
        _run()
        print("\nALL PASS")
    except AssertionError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        rc = 2
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        rc = 3
    finally:
        cleanup(point_id)
    return rc


if __name__ == "__main__":
    sys.exit(main())
