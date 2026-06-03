# Workshop v1.5 — Phase 0 (Corpus Re-Sourcing + Shared Schema) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Scout capture real award-winning sites (not awwwards.com listing frames) full-page, tag every reference with a shared structural schema (`hero_archetype` / `section_topology` / `motion_signature` / `signature_idea`), flow those fields into the Qdrant payload + the embedding + the vault index, and exclude the 12 existing listing-frame captures — so Phase 1's gates and retrieval have a *diverse, structurally-labelled* corpus to work from.

**Architecture:** Scout is an LLM that follows `skills/scout-playbook.md` (fetched from GitHub `main`); the ingest daemon embeds notes into Qdrant via `scout_lib`; Workshop reads the vault via `build_vault_index`. Phase 0 edits the playbook prompt (sourcing + schema), adds a single shared-schema Python module consumed by `scout_lib`, `ingest_daemon`, and `workshop.py`, fixes the anchor slug→id resolution bug, and ships a one-time vault data migration. The corpus re-harvest itself is operational (Scout runs daily once the playbook lands on `main`).

**Tech Stack:** Python 3.12 (venv at `/opt/scout-workshop/venv`), pytest, PyYAML, Qdrant, Firecrawl (via the playbook), two git repos (`scout-workshop` code + `scout-workshop-vault` data).

---

## Deployment constraints (read before starting)

1. **The playbook is served from `main`.** `scripts/scout.py` points Scout at `raw.githubusercontent.com/Xander1993/scout-workshop/main/skills/scout-playbook.md`. Playbook edits on the `awwwards-v1.5` branch **do not affect Scout until merged to `main` and pushed.** Task 9 is the explicit, gated merge step — do not merge earlier.
2. **The vault is a separate repo** (`scout-workshop-vault`, checked out at `/opt/scout-workshop/vault`). The listing-frame migration (Task 8) commits there, not to the code repo.
3. **The ingest daemon refuses >15 pending notes per pass** (`HARD_REFUSE_THRESHOLD`, ingest_daemon.py:184) and warns >10. Re-harvest is paced by Scout's own 5-refs/run cap, so this is fine — but a bulk re-tag (Task 8) must only change *frontmatter of already-embedded notes* (daemon does `set_payload`, never re-embeds existing points), never create 12 new pending notes at once.
4. **Adding fields to `PAYLOAD_FIELDS` makes every already-embedded note show "payload drift"** on the next daemon pass → the daemon calls `set_payload` (no re-embed, cheap). That is the intended backfill mechanism; it is safe.
5. **Work on branch `awwwards-v1.5`.** All code commits land there. Only the playbook merge (Task 9) touches `main`.

## File structure

- Create: `scripts/structural_schema.py` — single source of truth for the structural enums + a validator. Imported by `scout_lib`, `ingest_daemon`, `workshop`.
- Create: `scripts/migrate_listing_frames.py` — one-time vault data migration (re-tag the 12 awwwards listing-frame notes).
- Create: `tests/test_structural_schema.py`, `tests/test_payload_schema.py`, `tests/test_embedding_text.py`, `tests/test_vault_index_slug.py`, `tests/test_playbook_lint.py`, `tests/test_listing_frame_migration.py`.
- Modify: `scripts/scout_lib.py:765-768` (`PAYLOAD_FIELDS`).
- Modify: `scripts/ingest_daemon.py:52-65` (`build_embedding_text`).
- Modify: `scripts/workshop.py:231-267` (`build_vault_index` — add slug keys).
- Modify: `skills/scout-playbook.md` (§2a/§3a sourcing fix; §3b/§3c schema fields; §2 new sources).

---

## Task 1: Shared structural-schema module

**Files:**
- Create: `scripts/structural_schema.py`
- Test: `tests/test_structural_schema.py`

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

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /opt/scout-workshop && venv/bin/pytest tests/test_structural_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'structural_schema'`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/structural_schema.py
"""Single source of truth for v1.5 structural reference/kit schema.

Consumed by scout_lib (Qdrant payload), ingest_daemon (embedding text),
workshop.py (diversity signature + retrieval), and the scout playbook
(which the LLM follows when writing notes). Keep this enum in lockstep
with skills/scout-playbook.md §3b/§3c and the Gate-A section_manifest enum.
"""
from __future__ import annotations

HERO_ARCHETYPES = (
    "monumental_wordmark", "full_bleed_photo_hero", "split_editorial",
    "kinetic_type", "product_canvas_pinned", "immersive_canvas",
)

# Section-type enum, shared with the Gate-A section_manifest (Phase 1).
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
    """Return a list of human-readable problems with a note's structural fields.

    Empty list == valid. Missing fields are NOT errors here (old notes lack
    them); this validates the SHAPE of fields that ARE present, so the ingest
    daemon and playbook-lint can flag malformed scout output without rejecting
    legacy notes.
    """
    errs: list[str] = []
    ha = fm.get("hero_archetype")
    if ha is not None and ha not in HERO_ARCHETYPES:
        errs.append(f"hero_archetype {ha!r} not in {HERO_ARCHETYPES}")
    st = fm.get("section_topology")
    if st is not None:
        if not isinstance(st, list):
            errs.append("section_topology must be a list")
        else:
            bad = [s for s in st if s not in SECTION_TYPES]
            if bad:
                errs.append(f"section_topology has unknown types: {bad}")
    ms = fm.get("motion_signature")
    if ms is not None:
        if not isinstance(ms, list):
            errs.append("motion_signature must be a list")
        else:
            bad = [m for m in ms if m not in MOTION_SIGNATURES]
            if bad:
                errs.append(f"motion_signature has unknown tags: {bad}")
    si = fm.get("signature_idea")
    if si is not None and (not isinstance(si, str) or not si.strip()):
        errs.append("signature_idea must be a non-empty string when present")
    return errs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /opt/scout-workshop && venv/bin/pytest tests/test_structural_schema.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git -C /opt/scout-workshop add scripts/structural_schema.py tests/test_structural_schema.py
git -C /opt/scout-workshop commit -m "feat(schema): shared structural enum module (hero_archetype/section_topology/motion_signature)"
```

---

## Task 2: Flow structural fields into the Qdrant payload

**Files:**
- Modify: `scripts/scout_lib.py:765-768` (`PAYLOAD_FIELDS`)
- Test: `tests/test_payload_schema.py`

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
    payload = scout_lib.frontmatter_to_payload(fm)
    assert payload["hero_archetype"] == "monumental_wordmark"
    assert payload["section_topology"] == ["full_bleed_plate"]
    assert payload["motion_signature"] == ["scroll_pin"]
    assert payload["signature_idea"] == "the idea"

def test_payload_omits_structural_fields_when_absent():
    payload = scout_lib.frontmatter_to_payload({"id": "x", "title": "T"})
    assert "hero_archetype" not in payload  # legacy notes don't carry it
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /opt/scout-workshop && venv/bin/pytest tests/test_payload_schema.py -v`
Expected: FAIL on `test_payload_includes_structural_fields_when_present` (KeyError `hero_archetype`).

- [ ] **Step 3: Write minimal implementation**

In `scripts/scout_lib.py`, replace the `PAYLOAD_FIELDS` definition (currently lines 765-768):

```python
PAYLOAD_FIELDS = (
    "id source source_url scraped_at title vertical reference_type "
    "techniques color_mood typography_style layout_pattern palette_hex "
    "hero_archetype section_topology motion_signature signature_idea"
).split()
```

`frontmatter_to_payload` (line 771) is unchanged — it iterates `PAYLOAD_FIELDS` and includes only present keys, so absent fields are still omitted.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /opt/scout-workshop && venv/bin/pytest tests/test_payload_schema.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git -C /opt/scout-workshop add scripts/scout_lib.py tests/test_payload_schema.py
git -C /opt/scout-workshop commit -m "feat(schema): structural fields flow into Qdrant payload"
```

---

## Task 3: Add structural fields to the embedding text

**Files:**
- Modify: `scripts/ingest_daemon.py:52-65` (`build_embedding_text`)
- Test: `tests/test_embedding_text.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_embedding_text.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import ingest_daemon

def test_embedding_text_includes_structural_fields():
    fm = {"title": "T", "vertical": "agency", "reference_type": "studio_site",
          "color_mood": "warm-earth", "typography_style": "display-grotesque",
          "layout_pattern": "x", "techniques": ["a"],
          "hero_archetype": "monumental_wordmark",
          "section_topology": ["full_bleed_plate", "manifesto"],
          "motion_signature": ["scroll_pin", "lenis_smooth"],
          "signature_idea": "wordmark dissolves into photo"}
    text = ingest_daemon.build_embedding_text(fm, "body text")
    assert "monumental_wordmark" in text
    assert "full_bleed_plate" in text
    assert "scroll_pin" in text
    assert "wordmark dissolves into photo" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /opt/scout-workshop && venv/bin/pytest tests/test_embedding_text.py -v`
Expected: FAIL (`monumental_wordmark` not in text).

- [ ] **Step 3: Write minimal implementation**

In `scripts/ingest_daemon.py`, replace `build_embedding_text` (lines 52-65) so the `parts` list includes the structural fields before the body:

```python
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
        f"Section topology: {', '.join(fm.get('section_topology', []) or [])}",
        f"Motion signature: {', '.join(fm.get('motion_signature', []) or [])}",
        f"Signature idea: {fm.get('signature_idea', '')}",
        f"Techniques: {', '.join(fm.get('techniques', []) or [])}",
        "",
        body[:2000],
    ]
    return "\n".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /opt/scout-workshop && venv/bin/pytest tests/test_embedding_text.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git -C /opt/scout-workshop add scripts/ingest_daemon.py tests/test_embedding_text.py
git -C /opt/scout-workshop commit -m "feat(schema): structural fields enter the embedding text"
```

> Note: changing `build_embedding_text` does NOT re-embed existing notes (the daemon's idempotency contract never re-embeds an indexed point). New fields affect only notes embedded *after* this lands. Legacy notes keep their original vectors; their payloads backfill via Task 2's `set_payload` drift path. This is acceptable — re-harvested refs (Task 9) are the ones that need the richer embedding.

---

## Task 4: Slug→id bridge in `build_vault_index`

**Files:**
- Modify: `scripts/workshop.py:231-267` (`build_vault_index`)
- Test: `tests/test_vault_index_slug.py`

**Context:** `anchor_reference_ids` in `AWWWARDS_CONFIGS` are directory slugs (`989723a6-studio-namma`), but `build_vault_index` keys on the frontmatter `id:` UUIDv5. The two never match, so anchor resolution returns nothing. Fix: also key the index by `note.parent.name` (the directory slug). Slug and UUID forms never collide (different shapes), so they can share one dict.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_vault_index_slug.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import workshop

def _make_note(dirpath, uuid_id):
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / "note.md").write_text(
        f"---\nid: {uuid_id}\ntitle: Studio Namma\n---\n\n# Studio Namma\n", encoding="utf-8")
    (dirpath / "screenshot.png").write_bytes(b"\x89PNG\r\n")

def test_index_resolves_by_both_uuid_and_slug(tmp_path, monkeypatch):
    refs = tmp_path / "references" / "awwwards" / "989723a6-studio-namma"
    _make_note(refs, "81cdf982-bd0e-56c9-ac2b-10de879eec4e")
    monkeypatch.setattr(workshop, "VAULT_DIR", tmp_path)
    index = workshop.build_vault_index()
    # legacy UUID key still works
    assert "81cdf982-bd0e-56c9-ac2b-10de879eec4e" in index
    # NEW: directory-slug key resolves (this is what anchor_reference_ids use)
    assert "989723a6-studio-namma" in index
    assert index["989723a6-studio-namma"][0].name == "note.md"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /opt/scout-workshop && venv/bin/pytest tests/test_vault_index_slug.py -v`
Expected: FAIL — `989723a6-studio-namma` not in index.

- [ ] **Step 3: Write minimal implementation**

In `scripts/workshop.py`, in `build_vault_index` (the loop at lines 242-248), after the existing `index[fm_id] = (...)` assignment, add a slug key. The current loop body:

```python
    for note in refs_root.rglob("note.md"):
        fm_id = _read_frontmatter_id(note)
        if not fm_id:
            log.warning("no id in frontmatter: %s", note)
            continue
        screenshot = note.parent / "screenshot.png"
        index[fm_id] = (note, screenshot if screenshot.exists() else None)
```

becomes:

```python
    for note in refs_root.rglob("note.md"):
        fm_id = _read_frontmatter_id(note)
        if not fm_id:
            log.warning("no id in frontmatter: %s", note)
            continue
        screenshot = note.parent / "screenshot.png"
        entry = (note, screenshot if screenshot.exists() else None)
        index[fm_id] = entry
        # v1.5: also key by directory slug so AWWWARDS_CONFIGS.anchor_reference_ids
        # (slug form, e.g. "989723a6-studio-namma") resolve. Slug and UUIDv5 forms
        # never collide. The slug is the note's parent directory name verbatim.
        index[note.parent.name] = entry
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /opt/scout-workshop && venv/bin/pytest tests/test_vault_index_slug.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git -C /opt/scout-workshop add scripts/workshop.py tests/test_vault_index_slug.py
git -C /opt/scout-workshop commit -m "fix(retrieval): resolve awwwards anchors by directory slug in build_vault_index"
```

---

## Task 5: Listing-frame migration script (vault data)

**Files:**
- Create: `scripts/migrate_listing_frames.py`
- Test: `tests/test_listing_frame_migration.py`

**Context:** the 12 `vault/references/awwwards/*` notes are captures of awwwards.com's listing frame, not the award sites. Re-tag their `reference_type` to `listing_frame` so Phase 1 readiness/anchor logic excludes them. This edits already-embedded notes' frontmatter; the next ingest pass detects payload drift and calls `set_payload` (no re-embed). The script is idempotent.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_listing_frame_migration.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import migrate_listing_frames as mlf

def test_retags_awwwards_notes_idempotently(tmp_path):
    note_dir = tmp_path / "references" / "awwwards" / "989723a6-studio-namma"
    note_dir.mkdir(parents=True)
    (note_dir / "note.md").write_text(
        "---\nid: abc\ntitle: Studio Namma\nreference_type: studio_site\n"
        "qdrant_point_id: abc\n---\n\n# Studio Namma\n", encoding="utf-8")
    changed = mlf.retag(tmp_path)
    assert changed == 1
    text = (note_dir / "note.md").read_text()
    assert "reference_type: listing_frame" in text
    assert "original_reference_type: studio_site" in text  # provenance kept
    # idempotent: second run changes nothing
    assert mlf.retag(tmp_path) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /opt/scout-workshop && venv/bin/pytest tests/test_listing_frame_migration.py -v`
Expected: FAIL — `ModuleNotFoundError: migrate_listing_frames`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/migrate_listing_frames.py
"""One-time vault migration: re-tag awwwards listing-frame captures.

The 12 vault/references/awwwards/* notes are captures of awwwards.com's
listing frame, not the award sites. Re-tag reference_type -> listing_frame
(preserving the original under original_reference_type) so Phase 1 anchor/
readiness logic excludes them. Idempotent; safe to re-run. Run against the
vault repo, then let the ingest daemon set_payload the drift.

    venv/bin/python scripts/migrate_listing_frames.py            # apply
    venv/bin/python scripts/migrate_listing_frames.py --dry-run  # report only
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scout_lib import parse_note, write_note, VAULT_DIR  # type: ignore


def retag(vault_root: Path, dry_run: bool = False) -> int:
    awwwards = vault_root / "references" / "awwwards"
    if not awwwards.is_dir():
        return 0
    changed = 0
    for note in awwwards.rglob("note.md"):
        fm, body = parse_note(note)
        if fm.get("reference_type") == "listing_frame":
            continue  # already migrated
        fm["original_reference_type"] = fm.get("reference_type")
        fm["reference_type"] = "listing_frame"
        changed += 1
        if not dry_run:
            write_note(note, fm, body)
    return changed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--vault", default=str(VAULT_DIR))
    args = ap.parse_args()
    n = retag(Path(args.vault), dry_run=args.dry_run)
    print(f"{'would retag' if args.dry_run else 'retagged'} {n} note(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /opt/scout-workshop && venv/bin/pytest tests/test_listing_frame_migration.py -v`
Expected: PASS (uses a tmp vault; does NOT touch the real vault).

- [ ] **Step 5: Commit (code only — not the vault yet)**

```bash
git -C /opt/scout-workshop add scripts/migrate_listing_frames.py tests/test_listing_frame_migration.py
git -C /opt/scout-workshop commit -m "feat(vault): listing-frame re-tag migration script (idempotent)"
```

---

## Task 6: Playbook sourcing fix (dereference + full-page)

**Files:**
- Modify: `skills/scout-playbook.md` §2a and §3a
- Test: `tests/test_playbook_lint.py` (a lint guard — the playbook is an LLM prompt, so we assert it contains the required directives)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_playbook_lint.py
import pathlib
PLAYBOOK = (pathlib.Path(__file__).resolve().parent.parent / "skills" / "scout-playbook.md").read_text()

def test_awwwards_dereference_directive_present():
    # §2a/§3a must instruct dereferencing the awwwards /sites/<slug> page to the
    # real outbound site URL before capture (the root-cause fix).
    assert "Visit site" in PLAYBOOK or "outbound site URL" in PLAYBOOK
    assert "do NOT capture the awwwards.com listing page" in PLAYBOOK.lower() \
        or "dereference" in PLAYBOOK.lower()

def test_fullpage_screenshot_enabled():
    assert '"fullPage": true' in PLAYBOOK
    assert '"fullPage": false' not in PLAYBOOK
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /opt/scout-workshop && venv/bin/pytest tests/test_playbook_lint.py -v`
Expected: FAIL — current playbook has `"fullPage": false` and no dereference directive.

- [ ] **Step 3: Edit the playbook**

In `skills/scout-playbook.md` §2a, after the awwwards `curl` block, replace the bullet that says "Each of those resolves to a page where the target site URL is the actual reference" with an explicit dereference procedure:

```markdown
- **Dereference (REQUIRED — do NOT capture the awwwards.com listing page).** The `/sites/<slug>` links are awwwards.com directory pages, not the reference. For each chosen `/sites/<slug>` candidate: Firecrawl-scrape it with `formats:["links"]`, find the outbound **"Visit site"** URL (the off-awwwards.com link, typically labelled "Visit site" / in a `target=_blank` anchor to the studio's own domain), and use THAT real site URL as the candidate you process in §3. If no outbound URL can be found, mark the candidate `errored` and skip — never fall back to capturing the awwwards listing frame.
```

In §3a, change the screenshot options in the `curl` body from:

```json
    "screenshot": { "fullPage": false },
```
to:
```json
    "screenshot": { "fullPage": true },
```

And add, immediately after the §3a screenshot-handling block, a capture-quality gate:

```markdown
**Capture-quality gate.** Before writing the note, sanity-check the screenshot: if it is near-blank, a cookie/consent wall, or an obvious loader frame (e.g. <30KB PNG, or markdown body <400 chars), treat the candidate as `errored` and skip it. A premium award site that fails to render is worse than no reference — do not record a broken capture as an exemplar.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /opt/scout-workshop && venv/bin/pytest tests/test_playbook_lint.py::test_awwwards_dereference_directive_present tests/test_playbook_lint.py::test_fullpage_screenshot_enabled -v`
Expected: PASS.

- [ ] **Step 5: Commit (branch only — does NOT affect live Scout yet; see Task 9)**

```bash
git -C /opt/scout-workshop add skills/scout-playbook.md tests/test_playbook_lint.py
git -C /opt/scout-workshop commit -m "fix(scout): dereference awwwards listing to real site + full-page capture"
```

---

## Task 7: Playbook structural-schema fields (§3b/§3c)

**Files:**
- Modify: `skills/scout-playbook.md` §3b (analysis table) and §3c (note template)
- Test: `tests/test_playbook_lint.py` (extend)

- [ ] **Step 1: Add failing lint assertions**

Append to `tests/test_playbook_lint.py`:

```python
def test_playbook_declares_structural_fields():
    for field in ("hero_archetype", "section_topology", "motion_signature", "signature_idea"):
        assert field in PLAYBOOK, f"playbook missing structural field {field}"
    # the hero-archetype enum values must be enumerated for the LLM
    for v in ("monumental_wordmark", "full_bleed_photo_hero", "product_canvas_pinned"):
        assert v in PLAYBOOK
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /opt/scout-workshop && venv/bin/pytest tests/test_playbook_lint.py::test_playbook_declares_structural_fields -v`
Expected: FAIL.

- [ ] **Step 3: Edit the playbook**

In §3b's analysis-field table, add four rows (keep the existing table format):

```markdown
| `hero_archetype` | enum | The hero's structural archetype: `monumental_wordmark` \| `full_bleed_photo_hero` \| `split_editorial` \| `kinetic_type` \| `product_canvas_pinned` \| `immersive_canvas`. Pick the closest. |
| `section_topology` | string[] | Ordered list of section types down the page, from: `full_bleed_plate`, `work_grid`, `manifesto`, `spec_table`, `scroll_chapter`, `studio_statement`, `product_hero`, `trust_signals`, `case_grid`, `callout`, `stats_row`. |
| `motion_signature` | string[] | Motion tags observed: `splittype_stagger`, `scroll_pin`, `lenis_smooth`, `parallax`, `webgl_canvas`, `none`. |
| `signature_idea` | string, ≤200 chars | The ONE distinctive idea/concept of the site (the bespoke hook), e.g. "wordmark dissolves into the hero photo on scroll". NOT a reusable skeleton description. |
```

In §3c's frontmatter template, add the four fields after `palette_hex`:

```markdown
palette_hex: <palette_hex as YAML list>
hero_archetype: <hero_archetype>
section_topology: <section_topology as YAML list>
motion_signature: <motion_signature as YAML list>
signature_idea: <signature_idea>
```

And change the §3c "Why this is a reference" guidance to capture the idea, not a skeleton:

```markdown
## Why this is a reference

<2–3 sentences naming THE ONE distinctive idea (the signature_idea) and the craft that makes it premium. Do NOT describe it as a reusable three-block skeleton — capture what is bespoke about it.>
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /opt/scout-workshop && venv/bin/pytest tests/test_playbook_lint.py -v`
Expected: PASS (all playbook-lint tests).

- [ ] **Step 5: Commit**

```bash
git -C /opt/scout-workshop add skills/scout-playbook.md tests/test_playbook_lint.py
git -C /opt/scout-workshop commit -m "feat(scout): emit structural schema (hero_archetype/topology/motion/signature_idea) per note"
```

---

## Task 8: Playbook source diversification (§2)

**Files:**
- Modify: `skills/scout-playbook.md` §2 (Discover)
- Test: `tests/test_playbook_lint.py` (extend)

- [ ] **Step 1: Add failing lint assertions**

```python
def test_playbook_has_diversified_sources():
    assert "godly.website" in PLAYBOOK.lower() or "godly" in PLAYBOOK.lower()
    assert "product page" in PLAYBOOK.lower()
    assert "across archetypes" in PLAYBOOK.lower() or "spread" in PLAYBOOK.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /opt/scout-workshop && venv/bin/pytest tests/test_playbook_lint.py::test_playbook_has_diversified_sources -v`
Expected: FAIL.

- [ ] **Step 3: Edit the playbook**

Add a new discovery sub-section §2d and a picking rule. After §2c, insert:

```markdown
### 2d. Diversified premium sources (v1.5)
- **Godly** (`https://godly.website/`) — Firecrawl scrape (stealth), parse `data.links` for outbound site URLs; dereference as in §2a.
- **Apple-style product pages** — a curated seed list lives in `state/scout-overflow.txt` (operator-seeded). Process these `reference_type: product_marketing` candidates with priority; they are the only source of the `product_canvas_pinned` archetype that the single-product kit-type needs. Seed examples: apple.com/{iphone,airpods,watch} product pages, nothing.tech, teenage.engineering, polestar.com, linear.app, arc.net.
- **Archetype spread (REQUIRED):** when choosing this run's ≤5 candidates, prefer a set that spans **≥2 distinct hero archetypes** — do NOT take 5 sites that are all the same wordmark-masthead. If discovery only surfaces one archetype, take fewer and spill the rest.
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /opt/scout-workshop && venv/bin/pytest tests/test_playbook_lint.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git -C /opt/scout-workshop add skills/scout-playbook.md tests/test_playbook_lint.py
git -C /opt/scout-workshop commit -m "feat(scout): diversified sources (Godly + Apple product pages) + archetype spread"
```

---

## Task 9: Apply migration + deploy playbook to `main` (gated operational step)

**This task changes live state. Do it only after Tasks 1-8 pass and the Phase 0 audit approves.**

- [ ] **Step 1: Run the full Phase 0 test suite green**

Run: `cd /opt/scout-workshop && venv/bin/pytest tests/test_structural_schema.py tests/test_payload_schema.py tests/test_embedding_text.py tests/test_vault_index_slug.py tests/test_listing_frame_migration.py tests/test_playbook_lint.py -v`
Expected: all PASS.

- [ ] **Step 2: Apply the listing-frame migration to the real vault (dry-run first)**

```bash
cd /opt/scout-workshop
venv/bin/python scripts/migrate_listing_frames.py --dry-run   # expect "would retag 12 note(s)"
venv/bin/python scripts/migrate_listing_frames.py             # apply
git -C vault add references/awwwards
git -C vault commit -m "migrate: re-tag awwwards listing-frame captures (reference_type: listing_frame)"
git -C vault push origin main
```
Expected: 12 notes re-tagged; vault pushed. The next `scout-ingest` tick will `set_payload` the drift (no re-embed).

- [ ] **Step 3: Merge the playbook to `main` so Scout picks it up**

The playbook is served from `main`. Merge only the scout-facing files (playbook + schema module + scout_lib/ingest changes are all on `awwwards-v1.5`); since `main` may have unrelated WIP, do a clean merge of this branch's Phase 0 commits:

```bash
cd /opt/scout-workshop
git checkout main && git pull origin main
git merge --no-ff awwwards-v1.5 -m "merge: v1.5 Phase 0 (corpus re-sourcing + shared schema)"
git push origin main
git checkout awwwards-v1.5
```
Expected: `main` now serves the updated playbook; next Scout run dereferences + full-page-captures + emits structural fields.

> If `main` has conflicting WIP in `scripts/scout.py`/`dashboard/*`, resolve in favour of keeping that WIP plus this branch's additive changes — Phase 0 does not modify `scout.py` or the dashboard.

- [ ] **Step 4: Trigger a re-harvest pass and verify**

```bash
cd /opt/scout-workshop
systemctl start scout.service 2>/dev/null || venv/bin/python scripts/scout.py
# after the run + an ingest tick:
venv/bin/python scripts/ingest_daemon.py --once
```
Expected: new awwwards refs are captures of real sites (check a new `vault/references/awwwards/<slug>/screenshot.png` is the actual site, not awwwards chrome) and carry `hero_archetype`/`section_topology`/`motion_signature`/`signature_idea`. Re-harvest accumulates over several daily runs toward ≥5 refs per active sub-aesthetic spanning ≥3 archetypes (the Phase 1 readiness target).

- [ ] **Step 5: Record the corpus state for the Phase 0 audit**

```bash
cd /opt/scout-workshop && venv/bin/python - <<'PY'
import pathlib, yaml, collections
refs = pathlib.Path("vault/references")
by_arch = collections.Counter()
for n in refs.rglob("note.md"):
    fm = yaml.safe_load(n.read_text().split("---",2)[1])
    if fm.get("reference_type") == "listing_frame":
        continue
    by_arch[fm.get("hero_archetype","<none>")] += 1
print("archetype distribution (excl. listing_frame):", dict(by_arch))
PY
```
Expected: a distribution spanning multiple archetypes (not 100% `<none>` / one archetype). This output is the evidence the Phase 0 audit checks.

---

## Self-review (spec coverage)

- Spec §5 "scout sourcing fixes" → Tasks 6, 8. ✓
- Spec §5 "shared structural schema (4 consumers)" → Task 1 (module) + Task 2 (payload) + Task 3 (embedding) + Task 7 (playbook). ✓
- Spec §5 "slug→id bridge" → Task 4. ✓
- Spec §5 "re-tag 12 listing-frame captures, exclude from anchor pools" → Task 5 (script) + Task 9 Step 2 (apply). The *exclusion* logic (readiness skips `listing_frame`) is consumed in Phase 1; Phase 0 only produces the tag. ✓ (noted)
- Spec §5 "re-harvest targets ≥5/archetype" + "readiness ≥2 archetypes" → Task 8 (archetype spread) + Task 9 (operational harvest). The readiness *predicate* wiring is Phase 1. ✓ (noted)
- Spec §5 "schema migration default-handles missing fields" → Task 2 (omit-when-absent) + Task 3 (`.get` defaults) + Task 1 (`validate_structural` tolerates missing). ✓

**Deferred to Phase 1 (correctly out of Phase 0 scope):** wiring `listing_frame` exclusion + `≥2 archetype` readiness into `pick_target`/retrieval; the art-direction rerank query; consuming the new payload fields in `retrieve_inspiration`'s `candidate_docs`.

**Known limitation (documented, not a gap):** legacy notes keep text-only-era embeddings; only re-harvested refs get the richer multimodal embedding. Acceptable — the awwwards pool is being rebuilt anyway.

---

## Execution note

Tasks 1-8 are pure branch work (TDD, reversible). Task 9 is the one live-state step (vault migration + playbook→main merge + re-harvest) and is gated behind the Phase 0 audit. Do not run Task 9 until the audit approves Tasks 1-8.
