#!/usr/bin/env python3
"""Scout-Workshop ingestion daemon.

Polls the vault repo for reference notes that haven't been embedded yet,
embeds them multimodally, upserts into Qdrant, and updates the note's
frontmatter with the qdrant_point_id + embedded_at timestamp.

Designed to run every 10 minutes via the `scout-ingest.timer` systemd unit. Idempotent and safe to re-run.

Usage:
    python ingest_daemon.py            # one full pass, exit
    python ingest_daemon.py --once     # alias
    python ingest_daemon.py --dry-run  # report pending notes, do not write
    python ingest_daemon.py --watch    # loop with sleep (for systemd, optional)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scout_lib import (  # type: ignore
    VAULT_DIR, LOG_DIR,
    parse_note, write_note,
    find_unembedded_notes,
    frontmatter_to_payload,
    upsert_reference,
    embed_with_mode,  # returns (vector, mode); mode ∈ {text, multimodal, multimodal-fallback}
    vault_pull, vault_commit, vault_push,
    send_telegram, iso_now,
    qdrant_client, COLLECTION_NAME,
)

LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "ingest-daemon.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("ingest")


def build_embedding_text(fm: dict, body: str) -> str:
    """The text we feed to the multimodal embedding alongside the screenshot."""
    parts = [
        f"Title: {fm.get('title', '')}",
        f"Vertical: {fm.get('vertical', '')}",
        f"Reference type: {fm.get('reference_type', '')}",
        f"Color mood: {fm.get('color_mood', '')}",
        f"Typography: {fm.get('typography_style', '')}",
        f"Layout: {fm.get('layout_pattern', '')}",
        f"Techniques: {', '.join(fm.get('techniques', []) or [])}",
        "",
        body[:2000],  # cap body to keep embedding text under control
    ]
    return "\n".join(parts)


def resolve_screenshot_path(note_path: Path, fm: dict) -> Path | None:
    """Resolve the note's screenshot to an absolute filesystem path.

    Returns None if the file doesn't exist on disk — caller should fall back
    to text-only embedding in that case. Does NOT read or encode the file;
    the public scout_lib.embed_with_mode() handles file I/O and base64 internally
    per Day 1's design.
    """
    rel = fm.get("screenshot_path", "./screenshot.png")
    img_path = (note_path.parent / rel).resolve()
    return img_path if img_path.exists() else None


def process_one(note_path: Path, dry_run: bool) -> tuple[bool, str | None, str | None]:
    """Returns (success, point_id).

    Idempotency contract: this function NEVER re-embeds an existing point.
    Embedding is the expensive operation (OpenRouter credit + latency); the
    cursor-reset / vault-reclone / arbitrary-replay scenarios must all be
    safe. We achieve that by always checking Qdrant first as the source of
    truth on whether a point_id is indexed — never trusting any local
    cursor file or the note's own frontmatter alone.

    Three branches:
        A) Point exists, payload matches frontmatter   → no-op (just backfill local fm if needed)
        B) Point exists, payload drift from frontmatter → set_payload only (no re-embed)
        C) Point does not exist                         → full embed + upsert
    """
    fm, body = parse_note(note_path)
    point_id = fm.get("id")
    if not point_id:
        log.error("note %s missing id in frontmatter", note_path)
        return False, None, None

    # Qdrant is the source of truth on existence. Cheap call (~10ms localhost).
    existing = qdrant_client().retrieve(
        collection_name=COLLECTION_NAME, ids=[point_id],
        with_payload=True, with_vectors=False,
    )

    if existing:
        # Branch A or B — already indexed. Never re-embed.
        current_payload = frontmatter_to_payload(fm)
        existing_payload = existing[0].payload or {}

        if current_payload == existing_payload:
            log.info("already indexed, payload in sync: %s", point_id)
        else:
            # Branch B: payload drift. Update payload only, leave vector alone.
            log.info("already indexed, payload drift: %s — set_payload (no re-embed)", point_id)
            if not dry_run:
                qdrant_client().set_payload(
                    collection_name=COLLECTION_NAME,
                    payload=current_payload,
                    points=[point_id],
                )

        # Always backfill frontmatter so local note state matches Qdrant reality.
        if not dry_run and (
            fm.get("qdrant_point_id") != point_id or not fm.get("embedded_at")
        ):
            fm["qdrant_point_id"] = point_id
            fm["embedded_at"] = fm.get("embedded_at") or iso_now()
            write_note(note_path, fm, body)
        return True, point_id, "skipped-already-indexed"

    # Branch C: new point. Full embed + upsert path.
    text = build_embedding_text(fm, body)
    img_path = resolve_screenshot_path(note_path, fm)

    if dry_run:
        log.info("DRY: would embed %s (multimodal=%s)", point_id, img_path is not None)
        return True, point_id, None

    # embed_with_mode() returns (vector, mode) — mode is "text",
    # "multimodal", or "multimodal-fallback" (the last meaning we asked for
    # multimodal but the OpenRouter call rejected it and we silently fell
    # back to text-only). We log the mode so future debugging of "why is
    # this reference ranked oddly" has a breadcrumb.
    if img_path is not None:
        vector, mode = embed_with_mode(text, image_path=str(img_path))
        if mode == "multimodal-fallback":
            log.warning("multimodal embedding failed for %s — fell back to text-only", point_id)
        else:
            log.info("embedding mode for %s: %s", point_id, mode)
    else:
        log.warning("screenshot missing for %s — text-only embedding", note_path)
        vector, mode = embed_with_mode(text)

    payload = frontmatter_to_payload(fm)
    upsert_reference(point_id, vector, payload)

    fm["qdrant_point_id"] = point_id
    fm["embedded_at"] = iso_now()
    write_note(note_path, fm, body)

    log.info("embedded %s · %s (mode=%s)", point_id, fm.get("title", ""), mode)
    return True, point_id, mode


def run_once(dry_run: bool = False) -> dict:
    summary = {
        "pulled": False, "found": 0, "succeeded": 0, "failed": 0,
        "ids": [], "refused": False,
        "modes": {"multimodal": 0, "multimodal-fallback": 0, "text": 0},
    }

    if not dry_run:
        summary["pulled"] = vault_pull()

    pending = find_unembedded_notes()
    summary["found"] = len(pending)
    log.info("found %d pending notes", len(pending))

    # Soft and hard caps on per-pass volume. Catches Scout misbehavior or vault corruption
    # before the daemon embeds 100 garbage notes and burns through OpenRouter credit.
    HARD_REFUSE_THRESHOLD = 15
    SOFT_WARN_THRESHOLD = 10
    if len(pending) > HARD_REFUSE_THRESHOLD:
        msg = (
            f"🚨 Ingest daemon: {len(pending)} pending notes exceeds hard cap "
            f"({HARD_REFUSE_THRESHOLD}). Refusing this pass. Manual review required."
        )
        log.error(msg)
        if not dry_run:
            try:
                send_telegram(msg)
            except Exception:
                log.exception("telegram send failed")
        summary["refused"] = True
        return summary
    if len(pending) > SOFT_WARN_THRESHOLD:
        msg = (
            f"⚠ Ingest daemon: {len(pending)} pending notes (>{SOFT_WARN_THRESHOLD}). "
            f"Proceeding, but inspect Scout output if this persists."
        )
        log.warning(msg)
        if not dry_run:
            try:
                send_telegram(msg)
            except Exception:
                log.exception("telegram send failed")

    if pending:
        for path in pending:
            try:
                ok, pid, mode = process_one(path, dry_run=dry_run)
                if ok:
                    summary["succeeded"] += 1
                    if pid:
                        summary["ids"].append(pid)
                    if mode in ("multimodal", "multimodal-fallback", "text"):
                        summary["modes"][mode] += 1
                else:
                    summary["failed"] += 1
            except Exception:
                log.exception("failed to ingest %s", path)
                summary["failed"] += 1

        if not dry_run and summary["succeeded"] > 0:
            # commit all the frontmatter updates in one shot
            sha = vault_commit(
                f"ingest: embed {summary['succeeded']} reference(s)",
                list(VAULT_DIR.rglob("note.md")),
            )
            if sha:
                vault_push()
                log.info("vault commit pushed: %s", sha)

    if not dry_run:
        try:
            deliver_pending_digest(summary)
        except Exception:
            log.exception("deliver_pending_digest failed")

    return summary


def deliver_pending_digest(summary: dict) -> None:
    """Deliver Scout's pending digest file to Telegram, augmented with ingest stats.

    Idempotency: file is deleted from vault after successful Telegram POST.
    Re-runs of the daemon within the same window find no file and no-op.

    On failure: file is left in place; daemon-local failure counter at
    /opt/scout-workshop/state/digest-delivery-failures.json (gitignored)
    increments. After 3 consecutive failures on the same content (keyed
    by sha256), daemon stops retrying that digest to avoid Telegram spam
    during outages. A new digest (different content) resets the counter.

    Acknowledged v1.1 risk: if Telegram POST succeeds but the daemon
    crashes before deleting the file or pushing the marker commit, the
    next tick may resend. Window is sub-second; not addressing in v1.1.
    """
    digest_path = VAULT_DIR / "state" / "scout-digest-latest.md"
    if not digest_path.exists():
        return

    try:
        body = digest_path.read_text(encoding="utf-8").strip()
    except Exception:
        log.exception("could not read digest file %s", digest_path)
        return

    if not body:
        log.info("digest file empty, removing without sending")
        digest_path.unlink(missing_ok=True)
        return

    failures_path = Path("/opt/scout-workshop/state/digest-delivery-failures.json")
    content_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    failures: dict = {}
    if failures_path.exists():
        try:
            failures = json.loads(failures_path.read_text())
        except Exception:
            failures = {}
    if failures.get("sha256") == content_sha and failures.get("count", 0) >= 3:
        log.warning(
            "skipping digest delivery: %d consecutive failures on this content "
            "(sha=%s). Manual intervention needed.",
            failures["count"], content_sha[:12],
        )
        return

    modes = summary.get("modes", {}) or {}
    try:
        vault_total = qdrant_client().count(COLLECTION_NAME, exact=True).count
    except Exception:
        log.exception("could not count qdrant points; omitting from digest")
        vault_total = None

    aug_lines = [
        "",
        "─── Ingest (this pass) ───",
        f"Embedded: {summary.get('succeeded', 0)} reference(s)",
    ]
    mode_parts = [
        f"{m}={modes.get(m, 0)}"
        for m in ("multimodal", "multimodal-fallback", "text")
        if modes.get(m, 0)
    ]
    if mode_parts:
        aug_lines.append("Modes: " + ", ".join(mode_parts))
    if vault_total is not None:
        aug_lines.append(f"Vault total: {vault_total} points")

    augmented = body + "\n" + "\n".join(aug_lines)

    try:
        send_telegram(augmented)
    except Exception:
        log.exception("telegram send failed for digest")
        new_count = (
            failures.get("count", 0) + 1
            if failures.get("sha256") == content_sha
            else 1
        )
        failures_path.parent.mkdir(parents=True, exist_ok=True)
        failures_path.write_text(json.dumps({
            "sha256": content_sha,
            "count": new_count,
            "last_failure_iso": iso_now(),
        }, indent=2))
        return

    if failures_path.exists():
        try:
            failures_path.unlink()
        except Exception:
            pass

    digest_path.unlink(missing_ok=True)
    sha = vault_commit(
        f"ingest: telegram digest delivered {iso_now()}",
        [digest_path],
    )
    if sha:
        try:
            vault_push(max_attempts=3)
            log.info("digest delivered + vault marker pushed: %s", sha)
        except Exception:
            log.exception(
                "digest delivered to Telegram but vault push failed — "
                "next tick may resend if local main can't reach origin"
            )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--watch-interval", type=int, default=600)
    ap.add_argument("--telegram-on-success", action="store_true",
                    help="Send Telegram digest when references were embedded.")
    args = ap.parse_args()

    if args.watch:
        while True:
            try:
                run_once(dry_run=args.dry_run)
            except Exception:
                log.exception("watch loop top-level failure")
            time.sleep(args.watch_interval)
        return 0

    summary = run_once(dry_run=args.dry_run)
    if args.telegram_on_success and summary["succeeded"] > 0 and not args.dry_run:
        send_telegram(
            f"📥 Ingest: embedded {summary['succeeded']} reference(s) "
            f"({summary['failed']} failed). "
            f"Total this pass: {summary['found']}."
        )
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
