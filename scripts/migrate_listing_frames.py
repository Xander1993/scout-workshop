"""One-time vault migration: re-tag awwwards listing-frame captures.

The 12 vault/references/awwwards/* notes capture awwwards.com's listing
frame, not the award sites. Re-tag reference_type -> listing_frame
(preserving the original) so Phase 1 anchor/readiness logic excludes them.

The ingest daemon never revisits embedded notes, so this script updates
Qdrant directly via set_payload (sync_qdrant=True). Idempotent.

    venv/bin/python scripts/migrate_listing_frames.py --dry-run
    venv/bin/python scripts/migrate_listing_frames.py --sync-qdrant
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scout_lib import parse_note, write_note, VAULT_DIR  # type: ignore


def retag(vault_root: Path, dry_run: bool = False, sync_qdrant: bool = False) -> int:
    awwwards = vault_root / "references" / "awwwards"
    if not awwwards.is_dir():
        return 0
    changed = 0
    for note in awwwards.rglob("note.md"):
        fm, body = parse_note(note)
        if fm.get("reference_type") == "listing_frame":
            continue
        fm["original_reference_type"] = fm.get("reference_type")
        fm["reference_type"] = "listing_frame"
        changed += 1
        if dry_run:
            continue
        write_note(note, fm, body)
        if sync_qdrant and fm.get("qdrant_point_id"):
            # Daemon won't backfill embedded notes — update Qdrant here.
            from scout_lib import qdrant_client, COLLECTION_NAME, frontmatter_to_payload  # type: ignore
            qdrant_client().set_payload(
                collection_name=COLLECTION_NAME,
                payload=frontmatter_to_payload(fm),
                points=[fm["qdrant_point_id"]],
            )
    return changed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sync-qdrant", action="store_true",
                    help="Also set_payload each note's Qdrant point (run on the VPS).")
    ap.add_argument("--vault", default=str(VAULT_DIR))
    args = ap.parse_args()
    n = retag(Path(args.vault), dry_run=args.dry_run, sync_qdrant=args.sync_qdrant)
    print(f"{'would retag' if args.dry_run else 'retagged'} {n} note(s)"
          f"{' + synced Qdrant' if args.sync_qdrant and not args.dry_run else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
