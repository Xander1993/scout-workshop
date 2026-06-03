# Workshop v1.5 — Phase 0 (Corpus Re-Sourcing + Shared Schema) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Revision 2** — rewritten after a 4-agent audit. Fixes: the false "daemon set_payloads the drift" mechanism (the daemon only processes *unembedded* notes), a LIVE ingest crash the plan would have perpetuated, a Task 6 shell-escaping bug, and missing implementation isolation. See the Rollback/Safety section.

**Goal:** Make Scout capture real award-winning sites (not awwwards.com listing frames) full-page, tag every reference with a shared structural schema (`hero_archetype` / `section_topology` / `motion_signature` / `signature_idea`), flow those fields into the Qdrant payload + the embedding + the vault index, exclude the 12 existing listing-frame captures (in the vault **and** in Qdrant), and stop the live ingest daemon from crashing — so Phase 1's gates and retrieval have a diverse, structurally-labelled corpus.

**Architecture:** Scout is an LLM following `skills/scout-playbook.md` (fetched from GitHub `main`); the ingest daemon embeds notes into Qdrant via `scout_lib`; Workshop reads the vault via `build_vault_index`. Phase 0 edits the playbook prompt, adds one shared-schema module consumed by `scout_lib`/`ingest_daemon`/`workshop.py`, hardens the embedding text, fixes anchor slug→id resolution, and ships a Qdrant-syncing vault migration. The corpus re-harvest is operational (Scout runs daily once the playbook lands on `main`).

**Tech Stack:** Python 3.12 (venv at `/opt/scout-workshop/venv`), pytest, PyYAML, Qdrant, Firecrawl (via the playbook), two git repos (`scout-workshop` code + `scout-workshop-vault` data), systemd timers.

---

## Critical operational facts (verified against the live host)

1. **The working tree `/opt/scout-workshop` IS the live deployment.** `scout.timer` (daily 06:00), `scout-ingest.timer` (`OnUnitActiveSec=10min`), and `workshop.timer` (Sun 01:00) run code directly from `scripts/*.py` in the working tree. Editing those files in-place changes live behavior on the next tick. → **Task 0 isolates implementation in a git worktree and masks the timers.**
2. **The ingest daemon only ever processes *unembedded* notes.** `run_once` iterates `find_unembedded_notes()`, which selects notes where `not fm.get("qdrant_point_id")` (scout_lib.py:758). Already-embedded notes are never revisited, so editing their frontmatter does **NOT** update their Qdrant payload. Adding fields to `PAYLOAD_FIELDS` does **NOT** backfill existing points. (This corrects Rev 1's false "set_payload drift backfill" claim.)
3. **`scout-ingest.service` is currently FAILING every tick.** A malformed `techniques:` item in `vault/references/madeinwordpress/72b63ecb-landia/note.md` (`- show-don't-tell: ...` — unquoted colon parses as a YAML dict) makes `build_embedding_text`'s `', '.join(...)` raise `TypeError`. Ingestion is dead until Task 3 lands. Re-harvest depends on this fix.
4. **Scout reads its playbook from GitHub `main`** (`raw.githubusercontent.com/.../main/skills/scout-playbook.md`). Playbook edits take effect only after merge to `main` (Task 9).
5. **The vault is a separate repo** (`scout-workshop-vault` at `/opt/scout-workshop/vault`); the daemon pulls/commits/pushes it every tick. Migrations must not race it → Task 9 masks the ingest timer.
6. **The daemon refuses >15 pending notes/pass** (`HARD_REFUSE_THRESHOLD`). Scout's 5-refs/run cap keeps re-harvest under it.

## File structure

- Create: `scripts/structural_schema.py`, `scripts/migrate_listing_frames.py`
- Create tests: `tests/test_structural_schema.py`, `test_payload_schema.py`, `test_embedding_text.py`, `test_vault_index_slug.py`, `test_playbook_lint.py`, `test_listing_frame_migration.py`, `test_enum_parity.py`
- Modify: `scripts/scout_lib.py:765-768` (`PAYLOAD_FIELDS`); `scripts/ingest_daemon.py:52-65` (`build_embedding_text`) + `process_one` (wire `validate_structural`); `scripts/workshop.py:243-249` (`build_vault_index`); `skills/scout-playbook.md` (§2a/§3a/§3b/§3c/§2d)

---

## Task 0: Isolate implementation & freeze the live system

**No code changes ship to the live tree until Task 9. Implement Tasks 1-8 in a worktree.**

- [ ] **Step 1: Record the pre-existing dirty WIP (do not clobber it)**

The live tree has uncommitted WIP (`scripts/scout.py` logging refactor, `dashboard/static/*`). Stash it with a label so a clean worktree base exists, then restore it to the live tree:

```bash
cd /opt/scout-workshop
git stash push -u -m "pre-v1.5 WIP (scout.py logging + dashboard)" scripts/scout.py dashboard/static/index.html dashboard/static/main.js dashboard/static/style.css
git stash apply   # keep WIP in the live tree; stash entry remains as a backup
```

- [ ] **Step 2: Mask the timers for the implementation window**

```bash
sudo systemctl mask scout-ingest.timer scout.timer workshop.timer
systemctl is-enabled scout-ingest.timer   # expect: masked
```
This stops the 10-minute ingest crash-loop and prevents any timer from running half-edited code. (Unmasked in Task 9.)

- [ ] **Step 3: Park the live tree on a stable branch, then create the worktree**

The live tree is currently checked out on `awwwards-v1.5`; a worktree cannot share that branch. Move the live tree to `main` (stable, pre-Phase-0 — timers are masked, so nothing runs), which also frees `awwwards-v1.5` for the worktree:

```bash
cd /opt/scout-workshop
git checkout main                       # live tree -> stable main; WIP follows the checkout
git worktree add /opt/scout-workshop-wt awwwards-v1.5
cd /opt/scout-workshop-wt && echo "worktree ready on $(git branch --show-current)"
```
Implement Tasks 1-8 in `/opt/scout-workshop-wt`. Run tests with the live venv: `/opt/scout-workshop/venv/bin/pytest`. The vault (`/opt/scout-workshop/vault`) is a separate repo and is NOT duplicated — Task 9's migration targets it directly.

> All `pytest`/edit commands in Tasks 1-8 run inside `/opt/scout-workshop-wt`. Substitute that for `/opt/scout-workshop` in the commands below. Commits land on `awwwards-v1.5` (shared between the worktree and the live tree's branch ref, but the live tree's *checkout* is untouched while masked).

---

## Task 1: Shared structural-schema module

**Files:** Create `scripts/structural_schema.py`; Test `tests/test_structural_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_structural_schema.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import structural_schema as ss

def test_enums_present_and_typed():
    assert "monumental_wordmark" in ss.HERO_ARCHETYPES
    assert "product_canvas_pinned" in ss.HERO_ARCHETYPES
    assert "full_bleed_plate" in ss.SECTION_TYPES
    assert "scroll_pin" in ss.MOTION_SIGNATURES
    assert ss.STRUCTURAL_FIELDS == ("hero_archetype", "section_topology", "motion_signature", "signature_idea")

def test_validate_accepts_good_and_flags_bad():
    good = {"hero_archetype": "monumental_wordmark",
            "section_topology": ["full_bleed_plate", "manifesto"],
            "motion_signature": ["scroll_pin", "lenis_smooth"],
            "signature_idea": "wordmark dissolves into the photo on scroll"}
    assert ss.validate_structural(good) == []
    bad = {"hero_archetype": "banana", "section_topology": "not-a-list",
           "motion_signature": ["scroll_pin"], "signature_idea": ""}
    errs = ss.validate_structural(bad)
    assert any("hero_archetype" in e for e in errs)
    assert any("section_topology" in e for e in errs)
    assert any("signature_idea" in e for e in errs)
```

- [ ] **Step 2: Run to verify it fails**

Run: `/opt/scout-workshop/venv/bin/pytest tests/test_structural_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: structural_schema`.

- [ ] **Step 3: Implement**

```python
# scripts/structural_schema.py
"""Single source of truth for v1.5 structural reference/kit schema.

Consumed by scout_lib (Qdrant payload), ingest_daemon (embedding text +
runtime validation), workshop.py (retrieval/diversity), and the scout
playbook (which the LLM follows when writing notes).

PHASE-1 OBLIGATION: SECTION_TYPES must be reconciled with the Gate-A
section_manifest ALLOWED_TYPES when that gate is built. They are NOT in
lockstep today (Gate-A is not yet on disk). tests/test_enum_parity.py
guards drift between THIS module and the playbook only.
"""
from __future__ import annotations

HERO_ARCHETYPES = (
    "monumental_wordmark", "full_bleed_photo_hero", "split_editorial",
    "kinetic_type", "product_canvas_pinned", "immersive_canvas",
)
SECTION_TYPES = (
    "full_bleed_plate", "work_grid", "manifesto", "spec_table",
    "scroll_chapter", "studio_statement", "product_hero",
    "monumental_wordmark", "trust_signals", "case_grid", "callout", "stats_row",
)
MOTION_SIGNATURES = (
    "splittype_stagger", "scroll_pin", "lenis_smooth",
    "parallax", "webgl_canvas", "none",
)
STRUCTURAL_FIELDS = ("hero_archetype", "section_topology", "motion_signature", "signature_idea")


def validate_structural(fm: dict) -> list[str]:
    """Return human-readable problems with a note's structural fields.

    Empty list == valid. Missing fields are NOT errors (legacy notes lack
    them); this validates the SHAPE of fields that ARE present, so callers
    can warn on malformed scout output without rejecting legacy notes.
    """
    errs: list[str] = []
    ha = fm.get("hero_archetype")
    if ha is not None and ha not in HERO_ARCHETYPES:
        errs.append(f"hero_archetype {ha!r} not in {HERO_ARCHETYPES}")
    st = fm.get("section_topology")
    if st is not None:
        if not isinstance(st, list):
            errs.append("section_topology must be a list")
        elif [s for s in st if s not in SECTION_TYPES]:
            errs.append(f"section_topology has unknown types: {[s for s in st if s not in SECTION_TYPES]}")
    ms = fm.get("motion_signature")
    if ms is not None:
        if not isinstance(ms, list):
            errs.append("motion_signature must be a list")
        elif [m for m in ms if m not in MOTION_SIGNATURES]:
            errs.append(f"motion_signature has unknown tags: {[m for m in ms if m not in MOTION_SIGNATURES]}")
    si = fm.get("signature_idea")
    if si is not None and (not isinstance(si, str) or not si.strip()):
        errs.append("signature_idea must be a non-empty string when present")
    return errs
```

- [ ] **Step 4: Run to verify it passes**

Run: `/opt/scout-workshop/venv/bin/pytest tests/test_structural_schema.py -v` → PASS (2).

- [ ] **Step 5: Commit**

```bash
git -C /opt/scout-workshop-wt add scripts/structural_schema.py tests/test_structural_schema.py
git -C /opt/scout-workshop-wt commit -m "feat(schema): shared structural enum module + validator"
```

---

## Task 2: Flow structural fields into the Qdrant payload

**Files:** Modify `scripts/scout_lib.py:765-768`; Test `tests/test_payload_schema.py`

> Note: this makes *newly-embedded* (re-harvested) notes carry the fields in their Qdrant payload. It does NOT backfill the ~30 legacy points (the daemon never revisits embedded notes — see Critical Fact #2). That is acceptable: the awwwards pool is being rebuilt, and the listing-frame points are payload-synced explicitly in Task 5.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_payload_schema.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import scout_lib

def test_payload_includes_structural_fields_when_present():
    fm = {"id": "x", "title": "T", "hero_archetype": "monumental_wordmark",
          "section_topology": ["full_bleed_plate"], "motion_signature": ["scroll_pin"],
          "signature_idea": "the idea"}
    p = scout_lib.frontmatter_to_payload(fm)
    assert p["hero_archetype"] == "monumental_wordmark"
    assert p["section_topology"] == ["full_bleed_plate"]
    assert p["motion_signature"] == ["scroll_pin"]
    assert p["signature_idea"] == "the idea"

def test_payload_omits_structural_fields_when_absent():
    assert "hero_archetype" not in scout_lib.frontmatter_to_payload({"id": "x", "title": "T"})
```

- [ ] **Step 2: Run → FAIL** (`KeyError hero_archetype`). `/opt/scout-workshop/venv/bin/pytest tests/test_payload_schema.py -v`

- [ ] **Step 3: Implement** — replace `PAYLOAD_FIELDS` (scout_lib.py:765-768):

```python
PAYLOAD_FIELDS = (
    "id source source_url scraped_at title vertical reference_type "
    "techniques color_mood typography_style layout_pattern palette_hex "
    "hero_archetype section_topology motion_signature signature_idea"
).split()
```

- [ ] **Step 4: Run → PASS.**

- [ ] **Step 5: Commit**

```bash
git -C /opt/scout-workshop-wt add scripts/scout_lib.py tests/test_payload_schema.py
git -C /opt/scout-workshop-wt commit -m "feat(schema): structural fields flow into Qdrant payload for new embeds"
```

---

## Task 3: Harden the embedding text (fixes the live crash) + wire validation

**Files:** Modify `scripts/ingest_daemon.py:52-65` (`build_embedding_text`) and `process_one`; Test `tests/test_embedding_text.py`

- [ ] **Step 1: Write the failing test (includes the live crash case)**

```python
# tests/test_embedding_text.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import ingest_daemon

def test_embedding_text_includes_structural_fields():
    fm = {"title": "T", "hero_archetype": "monumental_wordmark",
          "section_topology": ["full_bleed_plate", "manifesto"],
          "motion_signature": ["scroll_pin", "lenis_smooth"],
          "signature_idea": "wordmark dissolves into photo", "techniques": ["a"]}
    text = ingest_daemon.build_embedding_text(fm, "body")
    assert "monumental_wordmark" in text and "full_bleed_plate" in text
    assert "scroll_pin" in text and "wordmark dissolves into photo" in text

def test_embedding_text_survives_malformed_list_items():
    # Reproduces the live crash: a YAML list item that parsed as a dict.
    fm = {"title": "T", "techniques": [{"show-dont-tell": "above the fold is work"}],
          "section_topology": [{"oops": "dict"}]}
    text = ingest_daemon.build_embedding_text(fm, "body")  # must NOT raise
    assert "show-dont-tell" in text
```

- [ ] **Step 2: Run → FAIL** (`TypeError: sequence item ... expected str instance, dict found`). `/opt/scout-workshop/venv/bin/pytest tests/test_embedding_text.py -v`

- [ ] **Step 3: Implement** — replace `build_embedding_text` (ingest_daemon.py:52-65) with a version that adds the structural fields AND coerces every list item to `str` (defensive against malformed scout/LLM output):

```python
def _join(seq) -> str:
    """Join a frontmatter list defensively — list items may be malformed
    (e.g. a YAML 'a: b' parsed as a dict). str() every item so a single bad
    note can never crash the whole ingest pass (the live landia bug)."""
    return ", ".join(str(x) for x in (seq or []))


def build_embedding_text(fm: dict, body: str) -> str:
    """The text we feed to the multimodal embedding alongside the screenshot."""
    parts = [
        f"Title: {fm.get('title', '')}",
        f"Vertical: {fm.get('vertical', '')}",
        f"Reference type: {fm.get('reference_type', '')}",
        f"Color mood: {fm.get('color_mood', '')}",
        f"Typography: {fm.get('typography_style', '')}",
        f"Layout: {fm.get('layout_pattern', '')}",
        f"Hero archetype: {fm.get('hero_archetype', '')}",
        f"Section topology: {_join(fm.get('section_topology'))}",
        f"Motion signature: {_join(fm.get('motion_signature'))}",
        f"Signature idea: {fm.get('signature_idea', '')}",
        f"Techniques: {_join(fm.get('techniques'))}",
        "",
        body[:2000],
    ]
    return "\n".join(parts)
```

- [ ] **Step 4: Wire `validate_structural` as a runtime warn (no crash, no skip)**

At the top of `ingest_daemon.py`, add to the `scout_lib` import block a sibling import:

```python
from structural_schema import validate_structural  # type: ignore
```

In `process_one`, immediately after `fm, body = parse_note(note_path)` (currently line 96), add:

```python
    struct_errs = validate_structural(fm)
    if struct_errs:
        log.warning("structural-schema issues in %s: %s", note_path, "; ".join(struct_errs))
```

- [ ] **Step 5: Run → PASS.** `/opt/scout-workshop/venv/bin/pytest tests/test_embedding_text.py -v`

- [ ] **Step 6: Commit**

```bash
git -C /opt/scout-workshop-wt add scripts/ingest_daemon.py tests/test_embedding_text.py
git -C /opt/scout-workshop-wt commit -m "fix(ingest): defensive list-join (stops live crash) + structural fields + validate warn"
```

---

## Task 4: Slug→id bridge in `build_vault_index`

**Files:** Modify `scripts/workshop.py:243-249`; Test `tests/test_vault_index_slug.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_vault_index_slug.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import workshop

def test_index_resolves_by_both_uuid_and_slug(tmp_path, monkeypatch):
    d = tmp_path / "references" / "awwwards" / "989723a6-studio-namma"
    d.mkdir(parents=True)
    (d / "note.md").write_text("---\nid: 81cdf982-bd0e-56c9-ac2b-10de879eec4e\ntitle: Studio Namma\n---\n\n# X\n", encoding="utf-8")
    (d / "screenshot.png").write_bytes(b"\x89PNG\r\n")
    monkeypatch.setattr(workshop, "VAULT_DIR", tmp_path)
    index = workshop.build_vault_index()
    assert "81cdf982-bd0e-56c9-ac2b-10de879eec4e" in index   # legacy UUID key
    assert "989723a6-studio-namma" in index                  # NEW slug key (what anchors use)
    assert index["989723a6-studio-namma"][0].name == "note.md"
```

- [ ] **Step 2: Run → FAIL** (slug key absent). `/opt/scout-workshop/venv/bin/pytest tests/test_vault_index_slug.py -v`

- [ ] **Step 3: Implement** — in `build_vault_index` (workshop.py:243-249), the loop currently ends with `index[fm_id] = (note, screenshot if screenshot.exists() else None)`. Replace those lines with:

```python
        screenshot = note.parent / "screenshot.png"
        entry = (note, screenshot if screenshot.exists() else None)
        index[fm_id] = entry
        # v1.5: also key by directory slug so AWWWARDS_CONFIGS.anchor_reference_ids
        # (slug form, e.g. "989723a6-studio-namma") resolve. Slug and UUIDv5 never collide.
        index[note.parent.name] = entry
```

- [ ] **Step 4: Run → PASS.**

- [ ] **Step 5: Commit**

```bash
git -C /opt/scout-workshop-wt add scripts/workshop.py tests/test_vault_index_slug.py
git -C /opt/scout-workshop-wt commit -m "fix(retrieval): resolve awwwards anchors by directory slug"
```

---

## Task 5: Listing-frame migration that syncs Qdrant directly

**Files:** Create `scripts/migrate_listing_frames.py`; Test `tests/test_listing_frame_migration.py`

> Because the daemon never revisits embedded notes (Critical Fact #2), the migration must update Qdrant ITSELF via `set_payload` — re-tagging frontmatter alone would leave the Qdrant payload stale and let the 12 frames leak into payload-filtered readiness counts.

- [ ] **Step 1: Write the failing test** (frontmatter path; Qdrant sync is integration-tested in Task 9)

```python
# tests/test_listing_frame_migration.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import migrate_listing_frames as mlf

def test_retags_idempotently_without_qdrant(tmp_path):
    d = tmp_path / "references" / "awwwards" / "989723a6-studio-namma"
    d.mkdir(parents=True)
    (d / "note.md").write_text(
        "---\nid: abc\ntitle: Studio Namma\nreference_type: studio_site\nqdrant_point_id: abc\n---\n\n# X\n",
        encoding="utf-8")
    assert mlf.retag(tmp_path, sync_qdrant=False) == 1
    text = (d / "note.md").read_text()
    assert "reference_type: listing_frame" in text
    assert "original_reference_type: studio_site" in text
    assert mlf.retag(tmp_path, sync_qdrant=False) == 0   # idempotent
```

- [ ] **Step 2: Run → FAIL** (`ModuleNotFoundError`). `/opt/scout-workshop/venv/bin/pytest tests/test_listing_frame_migration.py -v`

- [ ] **Step 3: Implement**

```python
# scripts/migrate_listing_frames.py
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
import argparse, sys
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
```

- [ ] **Step 4: Run → PASS** (tmp vault; `sync_qdrant=False`, no Qdrant needed). `/opt/scout-workshop/venv/bin/pytest tests/test_listing_frame_migration.py -v`

- [ ] **Step 5: Commit**

```bash
git -C /opt/scout-workshop-wt add scripts/migrate_listing_frames.py tests/test_listing_frame_migration.py
git -C /opt/scout-workshop-wt commit -m "feat(vault): listing-frame migration with direct Qdrant set_payload"
```

---

## Task 6: Playbook sourcing fix (dereference + full-page)

**Files:** Modify `skills/scout-playbook.md` §2a/§3a; Test `tests/test_playbook_lint.py`

> The playbook embeds JSON in shell. §2a uses single-quoted `-d '{...}'` (quotes bare); §3a uses double-quoted `-d "{...}"` (quotes backslash-escaped: `\"fullPage\": false`). Edits must preserve each block's escaping; the lint is quote-agnostic via regex.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_playbook_lint.py
import pathlib, re
PLAYBOOK = (pathlib.Path(__file__).resolve().parent.parent / "skills" / "scout-playbook.md").read_text()

def test_awwwards_dereference_directive_present():
    assert "Visit site" in PLAYBOOK
    assert "dereference" in PLAYBOOK.lower()
    assert "do not capture the awwwards.com listing" in PLAYBOOK.lower()

def test_fullpage_screenshot_enabled():
    # quote-agnostic: matches both \"fullPage\": true and "fullPage": true
    assert re.search(r'fullPage\\?"\s*:\s*true', PLAYBOOK)
    assert not re.search(r'fullPage\\?"\s*:\s*false', PLAYBOOK)
```

- [ ] **Step 2: Run → FAIL.** `/opt/scout-workshop/venv/bin/pytest tests/test_playbook_lint.py -v`

- [ ] **Step 3: Edit the playbook**

(a) In §2a, replace the bullet at line 61 ("Each of those resolves to a page where the **target site URL** is the actual reference (Awwwards is itself a directory, not the reference).") with:

```markdown
- **Dereference (REQUIRED — do NOT capture the awwwards.com listing page).** The `/sites/<slug>` links are awwwards.com directory pages, not the reference. For each chosen `/sites/<slug>` candidate, Firecrawl-scrape it with `formats:["links"]`, find the outbound **"Visit site"** URL (the off-awwwards.com link to the studio's own domain), and use THAT real URL as the §3 candidate. If no outbound URL is found, mark the candidate `errored` and skip — never fall back to capturing the awwwards listing frame.
```

(b) In §3a, inside the double-quoted curl body (line 148), change `\"fullPage\": false` to `\"fullPage\": true` (keep the backslash-escaping intact):

```
    \"screenshot\": { \"fullPage\": true },
```

(c) After the §3a screenshot-handling block, add:

```markdown
**Capture-quality gate.** Before writing the note, sanity-check the screenshot: if it is near-blank, a cookie/consent wall, or a loader frame (PNG < 30KB, or markdown body < 400 chars), treat the candidate as `errored` and skip. A premium award site that fails to render is worse than no reference.
```

- [ ] **Step 4: Run → PASS.** `/opt/scout-workshop/venv/bin/pytest tests/test_playbook_lint.py -v`

- [ ] **Step 5: Commit**

```bash
git -C /opt/scout-workshop-wt add skills/scout-playbook.md tests/test_playbook_lint.py
git -C /opt/scout-workshop-wt commit -m "fix(scout): dereference awwwards listing to real site + full-page capture"
```

---

## Task 7: Playbook structural-schema fields (§3b/§3c) + enum-parity test

**Files:** Modify `skills/scout-playbook.md` §3b/§3c; Tests: extend `test_playbook_lint.py`, create `test_enum_parity.py`

- [ ] **Step 1: Write failing assertions**

Append to `tests/test_playbook_lint.py`:

```python
def test_playbook_declares_structural_fields():
    for f in ("hero_archetype", "section_topology", "motion_signature", "signature_idea"):
        assert f in PLAYBOOK, f"playbook missing {f}"
```

Create `tests/test_enum_parity.py` (closes the drift hole presence-lint can't — every enum value the validator accepts must be offered to the LLM in the playbook):

```python
# tests/test_enum_parity.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import structural_schema as ss
PLAYBOOK = (pathlib.Path(__file__).resolve().parent.parent / "skills" / "scout-playbook.md").read_text()

def test_every_enum_value_is_offered_in_playbook():
    missing = [v for group in (ss.HERO_ARCHETYPES, ss.SECTION_TYPES, ss.MOTION_SIGNATURES)
               for v in group if v not in PLAYBOOK]
    assert missing == [], f"enum values not in playbook (validator would reject scout output): {missing}"
```

- [ ] **Step 2: Run → FAIL.** `/opt/scout-workshop/venv/bin/pytest tests/test_playbook_lint.py::test_playbook_declares_structural_fields tests/test_enum_parity.py -v`

- [ ] **Step 3: Edit the playbook** — in §3b's table add four rows enumerating EVERY enum value (so `test_enum_parity` passes):

```markdown
| `hero_archetype` | enum | `monumental_wordmark` \| `full_bleed_photo_hero` \| `split_editorial` \| `kinetic_type` \| `product_canvas_pinned` \| `immersive_canvas`. |
| `section_topology` | string[] | Ordered, from: `full_bleed_plate`, `work_grid`, `manifesto`, `spec_table`, `scroll_chapter`, `studio_statement`, `product_hero`, `monumental_wordmark`, `trust_signals`, `case_grid`, `callout`, `stats_row`. |
| `motion_signature` | string[] | From: `splittype_stagger`, `scroll_pin`, `lenis_smooth`, `parallax`, `webgl_canvas`, `none`. |
| `signature_idea` | string, ≤200 chars | The ONE distinctive idea (the bespoke hook), e.g. "wordmark dissolves into the hero photo on scroll". NOT a reusable skeleton. |
```

In §3c's frontmatter template, after `palette_hex:` add:

```markdown
hero_archetype: <hero_archetype>
section_topology: <section_topology as YAML list>
motion_signature: <motion_signature as YAML list>
signature_idea: <signature_idea>
```

And change the §3c "Why this is a reference" guidance to: `<2–3 sentences naming THE ONE distinctive idea (signature_idea) and the craft that makes it premium. Do NOT describe it as a reusable three-block skeleton.>`

- [ ] **Step 4: Run → PASS** (both lint + parity). `/opt/scout-workshop/venv/bin/pytest tests/test_playbook_lint.py tests/test_enum_parity.py -v`

- [ ] **Step 5: Commit**

```bash
git -C /opt/scout-workshop-wt add skills/scout-playbook.md tests/test_playbook_lint.py tests/test_enum_parity.py
git -C /opt/scout-workshop-wt commit -m "feat(scout): emit structural schema per note + enum-parity guard"
```

---

## Task 8: Playbook source diversification (§2)

**Files:** Modify `skills/scout-playbook.md` §2; Test: extend `test_playbook_lint.py`

- [ ] **Step 1: Failing assertion**

```python
def test_playbook_has_diversified_sources():
    pl = PLAYBOOK.lower()
    assert "godly" in pl and "product page" in pl
    assert "across archetypes" in pl or "spread" in pl
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Edit** — insert §2d after §2c:

```markdown
### 2d. Diversified premium sources (v1.5)
- **Godly** (`https://godly.website/`) — Firecrawl scrape (stealth), parse `data.links` for outbound site URLs; dereference as in §2a.
- **Apple-style product pages** — an operator-seeded list in `state/scout-overflow.txt` (if absent, this source yields nothing — log it, do not fail). Process these `reference_type: product_marketing` candidates with priority; they are the only source of the `product_canvas_pinned` archetype the single-product kit-type needs. Seeds: apple.com/{iphone,airpods,watch}, nothing.tech, teenage.engineering, polestar.com, linear.app, arc.net.
- **Archetype spread (REQUIRED):** when choosing this run's ≤5 candidates, prefer a set spanning **≥2 distinct hero archetypes** — never 5 of the same wordmark-masthead. If discovery surfaces only one archetype, take fewer and spill the rest.

> **Deferred to a later phase (documented, not silently dropped):** per-plate screenshot crops (Phase 0 ships `fullPage:true` only); a dedicated brutalist-style directory source (Godly + Apple seeds suffice for the initial re-harvest).
```

- [ ] **Step 4: Run → PASS.**

- [ ] **Step 5: Commit**

```bash
git -C /opt/scout-workshop-wt add skills/scout-playbook.md tests/test_playbook_lint.py
git -C /opt/scout-workshop-wt commit -m "feat(scout): diversified sources + archetype spread (per-plate crops/brutalist deferred)"
```

---

## Task 9: Gated deploy + migration + re-harvest (live state)

**Only after Tasks 0-8 pass AND the Phase 0 audit approves. The timers are masked (Task 0).**

- [ ] **Step 1: Full suite green in the worktree**

Run: `cd /opt/scout-workshop-wt && /opt/scout-workshop/venv/bin/pytest -q`
Expected: all PASS (bare invocation catches any mis-named test file, not just the seven named ones).

- [ ] **Step 2: Fix the live malformed landia note (data hygiene)**

Task 3's defensive `_join` already stops the crash; this just makes the technique embed as a clean string instead of `str(dict)`. Wrap the whole offending `key: value` list item in a single quoted YAML scalar:

```bash
cd /opt/scout-workshop
/opt/scout-workshop/venv/bin/python - <<'PY'
import re, pathlib
p = pathlib.Path("vault/references/madeinwordpress/72b63ecb-landia/note.md")
s = p.read_text()
s2 = re.sub(r'^(\s*-\s+)(show-don.t-tell:.*)$',
            lambda m: m.group(1) + '"' + m.group(2).replace('"', "'") + '"',
            s, flags=re.M)
p.write_text(s2)
print("changed" if s2 != s else "no-op")
PY
/opt/scout-workshop/venv/bin/python -c "import sys; sys.path.insert(0,'scripts'); from scout_lib import parse_note; from pathlib import Path; fm,_=parse_note(Path('vault/references/madeinwordpress/72b63ecb-landia/note.md')); print('techniques all str:', all(isinstance(x,str) for x in fm['techniques']))"
```
Expected: `changed` then `techniques all str: True`.

- [ ] **Step 3: Merge Phase 0 into `main` in the live tree**

The live tree is on `main` (Task 0). Bring in Tasks 1-8 + the playbook, then remove the now-merged worktree:

```bash
cd /opt/scout-workshop
git merge --no-ff awwwards-v1.5 -m "merge: v1.5 Phase 0 (corpus re-sourcing + shared schema)"
git worktree remove /opt/scout-workshop-wt
/opt/scout-workshop/venv/bin/pytest -q   # green against the live tree
```

- [ ] **Step 4: Apply the migration (vault + Qdrant), using the daemon's push retry**

```bash
cd /opt/scout-workshop
/opt/scout-workshop/venv/bin/python scripts/migrate_listing_frames.py --dry-run        # expect "would retag 12"
/opt/scout-workshop/venv/bin/python scripts/migrate_listing_frames.py --sync-qdrant    # retag + set_payload
git -C vault add references/awwwards
git -C vault commit -m "migrate: re-tag awwwards listing-frame captures + Qdrant payload synced"
git -C vault push origin main
# verify Qdrant payload actually changed:
/opt/scout-workshop/venv/bin/python -c "import sys; sys.path.insert(0,'scripts'); from scout_lib import qdrant_client, COLLECTION_NAME; r=qdrant_client().scroll(COLLECTION_NAME, limit=50, with_payload=True)[0]; n=sum(1 for p in r if (p.payload or {}).get('reference_type')=='listing_frame'); print('listing_frame points in qdrant:', n)"
```
Expected: `listing_frame points in qdrant: 12`. (The timers are masked, so no daemon race.)

- [ ] **Step 5: Push `main` so Scout picks up the new playbook**

```bash
cd /opt/scout-workshop
git pull --rebase origin main    # reconcile any parallel commits
git push origin main             # deploys the playbook (Scout fetches it from main)
```
(If `origin/main` has diverging WIP in `scripts/scout.py`/`dashboard/*`, rebase and keep it + this branch's additive changes — Phase 0 touches neither.)

- [ ] **Step 6: Unmask timers + trigger a re-harvest**

```bash
sudo systemctl unmask scout-ingest.timer scout.timer workshop.timer
sudo systemctl start scout-ingest.timer scout.timer workshop.timer
/opt/scout-workshop/venv/bin/python scripts/ingest_daemon.py --once   # confirm it no longer crashes
sudo systemctl start scout.service   # one manual harvest pass (or wait for 06:00)
```
Expected: ingest exits 0; a new awwwards ref is a capture of a REAL site (not awwwards chrome) and carries the structural fields.

- [ ] **Step 7: Objective readiness evidence (per-cell, matches the spec criterion)**

```bash
cd /opt/scout-workshop && /opt/scout-workshop/venv/bin/python - <<'PY'
import pathlib, yaml, collections
refs = pathlib.Path("vault/references")
rows = []
for n in refs.rglob("note.md"):
    fm = yaml.safe_load(n.read_text().split("\n---\n",1)[0].lstrip("-\n"))
    if not fm or fm.get("reference_type") == "listing_frame":
        continue
    rows.append((fm.get("color_mood","?"), fm.get("reference_type","?"), fm.get("hero_archetype","<none>")))
by_mood = collections.defaultdict(set)
for mood, rtype, arch in rows:
    by_mood[mood].add(arch)
print("usable refs:", len(rows))
for mood, archs in sorted(by_mood.items()):
    print(f"  {mood}: {len(archs)} distinct archetypes -> {sorted(archs)}")
print("READY for Phase 1 when active moods have >=2 distinct archetypes and >=5 usable refs each")
PY
```
This output is the gate evidence the Phase 0 audit checks. Re-harvest accumulates over daily runs until the threshold is met; **do not start Phase 1 until it is.**

---

## Rollback / kill-switch

- **Freeze everything:** `sudo systemctl mask scout.timer scout-ingest.timer workshop.timer`.
- **Revert code:** `git -C /opt/scout-workshop checkout main -- scripts/ skills/scout-playbook.md` (or reset the ff-merge); `PAYLOAD_FIELDS` revert needs no Qdrant action (new fields simply stop being written).
- **Revert the playbook on `main`:** `git revert` the Phase 0 merge commit + push; Scout reverts to the old behavior on its next run.
- **Revert the migration:** re-run a one-off that restores `reference_type` from `original_reference_type` and `set_payload`s it back; or `git -C vault revert` the migrate commit.
- **The worktree** (`/opt/scout-workshop-wt`) is removed at the end: `git -C /opt/scout-workshop worktree remove /opt/scout-workshop-wt`.

## Self-review (spec coverage)

- Sourcing (dereference, fullPage, sources, capture-quality, archetype spread) → Tasks 6, 8. ✓ (per-plate crops + brutalist source explicitly deferred in Task 8.)
- Shared schema, 4 consumers → Task 1 (module) + 2 (payload) + 3 (embedding + runtime validate) + 7 (playbook). Reranker/Gate-A/diversity consumers correctly deferred to Phase 1 (none exist on disk). ✓
- Slug→id bridge → Task 4. ✓
- Re-tag 12 listing-frames + exclude (vault AND Qdrant) → Task 5 + Task 9.4 (verified `=12` in Qdrant). ✓
- Live ingest crash (blocks all harvest) → Task 3 (defensive join) + Task 9.2 (fix the note). ✓
- Readiness ≥2 archetypes / ≥5 per cell → Task 8 (spread) + Task 9.7 (objective per-cell evidence). Predicate wiring → Phase 1. ✓
- Enum-drift guard (module ↔ playbook) → Task 7 (`test_enum_parity`). Module↔Gate-A reconciliation flagged as a Phase-1 obligation in the module docstring. ✓
- Isolation + live safety → Task 0 (worktree + mask) + Task 9 (ff deploy, no daemon race) + Rollback section. ✓

## Execution note

Tasks 0-8 are isolated (worktree, timers masked) and reversible. Task 9 is the gated live-state step. Do not run Task 9 until the Phase 0 plan audit approves Tasks 0-8.
