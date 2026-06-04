# Workshop v1.5 — Phase 1a (Awwwards Generation Engine — first runnable kit) Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use `- [ ]` checkboxes.

**Goal:** Make the awwwards register *produce one real premium kit end-to-end* via an additive `--awwwards-oneshot <sub_aesthetic> <kit_type>` CLI — register-aware config accessor, art-direction retrieval over the bootstrapped premium corpus, a per-run **signature-concept** step, an awwwards brief, and the two kit-type generators. **No cron change, no gates, no delivery** — just generate + screenshot a kit into a run dir so we can open and judge it. Gates/flip are Phase 1b/2.

**Architecture:** Everything is additive. `main()`'s existing conversion path is untouched; a new `run_awwwards_oneshot()` function + a CLI flag drive the awwwards pipeline. Generation is config-driven (pinned palette as ground truth, seeded-perturbed per run) + concept-driven (a bespoke `signature_move` per kit) + reference-grounded (the 8 curated premium refs). The live weekly cron still ships nothing (empty queue), so this is safe to merge.

**Tech Stack:** Python 3.12 (`/opt/scout-workshop/venv`), pytest, Qdrant, `claude --print` (opus, via `run_claude`), Playwright. Corpus: `vault/references/curated/` (8 schema-tagged premium refs, embedded).

---

## Key facts (verified)
- `get_awwwards_config(sub)` → `{name, register_family, palette:{bg,fg,accents[],supporting[]}, typography:{primary,primary_alternatives[],secondary,hero_h1_clamp}, photography_prefix, motion_vocabulary[], avoid[], anchor_reference_ids[], min_exemplar_count, vault_pending, ref_kit_template_variant}` (scripts/aesthetic_configs.py). Active sub-aesthetics: `sun-baked`, `warm-earth`, `editorial-mid-century` (all `register_family: restrained-monumental`). `acid-tech`/`cool-jewel` are `vault_pending: True`.
- Corpus payload fields available for retrieval: `source` (`curated`/`awwwards`/`dribbble`/…), `reference_type` (`product_marketing`/`studio_site`/`agency_portfolio`/`listing_frame`/…), `hero_archetype`, `section_topology`, `motion_signature`, `signature_idea`, `color_mood`, `typography_style`, `layout_pattern`, `palette_hex`, `techniques`, `title`.
- `build_vault_index()` keys by frontmatter `id` AND directory slug (Phase 0). `retrieve_inspiration`/`generate_kit`/`synthesize_brief`/`run_claude`/`load_prompt_template`/`KIT_REQUIRED_FILES`/`PAGES` exist as in workshop.py. `scout_lib.embed/qdrant_query/rerank` available.
- Branch off `main` (which has Phase 0). The oneshot is additive; no timer freeze needed (additive + empty queue). Work in a worktree to keep the live tree clean.

## File structure
- Create: `scripts/awwwards_render.py` (config→prompt directives + seeded palette perturbation + retrieval helpers)
- Create tests: `tests/test_awwwards_render.py`, `tests/test_awwwards_retrieval.py`, `tests/test_kit_required_files.py`
- Modify: `scripts/workshop.py` (add `run_awwwards_oneshot()` + `KIT_REQUIRED_FILES_BY_KIT_TYPE` + CLI flag; do NOT touch the conversion path)
- Modify: `skills/workshop-playbook.md` (add 3 prompt blocks: `design_concept`, `kit_generation_editorial_studio`, `kit_generation_single_product`, `brief_synthesis_awwwards`)

---

## Task 0: Branch + worktree (additive, no freeze)

- [ ] **Step 1**
```bash
cd /opt/scout-workshop && git checkout main && git pull --ff-only 2>/dev/null; git branch awwwards-v1.5-p1a
git worktree add /home/deployer/sw-p1a awwwards-v1.5-p1a
cd /home/deployer/sw-p1a && echo "on $(git branch --show-current)"
```
Implement Tasks 1-6 in `/home/deployer/sw-p1a`; tests via `/opt/scout-workshop/venv/bin/pytest`.

---

## Task 1: Awwwards render module (config → directives + seeded palette)

**Files:** Create `scripts/awwwards_render.py`; Test `tests/test_awwwards_render.py`

- [ ] **Step 1: failing test**
```python
# tests/test_awwwards_render.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import awwwards_render as ar

def test_perturb_is_deterministic_and_bounded():
    base = "#B8462C"
    a = ar.perturb_hex(base, seed=0); b = ar.perturb_hex(base, seed=0); c = ar.perturb_hex(base, seed=3)
    assert a == b                      # deterministic per seed
    assert a != base or c != base      # seed actually varies something
    assert a.startswith("#") and len(a) == 7
    assert ar.perturb_hex(base, seed=0) != ar.perturb_hex(base, seed=5)  # different seeds differ

def test_render_directives_has_palette_type_motion_photo():
    d = ar.render_directives("warm-earth", seed=1)
    assert "--color-bg" in d["palette_directive"] and "#" in d["palette_directive"]
    assert "clamp(" in d["typography_directive"]
    assert d["photography_prefix"]
    assert "GSAP" in d["motion_directive"] or "Lenis" in d["motion_directive"]
    assert d["register_family"] == "restrained-monumental"
```

- [ ] **Step 2: run → FAIL.** `/opt/scout-workshop/venv/bin/pytest tests/test_awwwards_render.py -v`

- [ ] **Step 3: implement**
```python
# scripts/awwwards_render.py
"""Render an awwwards sub-aesthetic config into prompt-ready directives.

Palette is the config's GROUND TRUTH, perturbed deterministically per run
(variation_seed) so repeated runs of one cell are visibly distinct but stay
on-aesthetic — restoring the diversity the pinned dict otherwise removes.
"""
from __future__ import annotations
import colorsys, hashlib, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from aesthetic_configs import get_awwwards_config  # type: ignore

def _seeded_unit(seed: int, salt: str) -> float:
    h = hashlib.sha256(f"{seed}:{salt}".encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF  # 0..1

def perturb_hex(hex_str: str, seed: int) -> str:
    """Bounded deterministic HLS shift: H +-8deg, L +-0.05, S +-0.05."""
    s = hex_str.lstrip("#")
    r, g, b = (int(s[i:i+2], 16) / 255 for i in (0, 2, 4))
    h, l, sat = colorsys.rgb_to_hls(r, g, b)
    h = (h + (_seeded_unit(seed, "h") - 0.5) * (16/360)) % 1.0
    l = min(1.0, max(0.0, l + (_seeded_unit(seed, "l") - 0.5) * 0.10))
    sat = min(1.0, max(0.0, sat + (_seeded_unit(seed, "s") - 0.5) * 0.10))
    r, g, b = colorsys.hls_to_rgb(h, l, sat)
    return "#" + "".join(f"{int(round(c*255)):02X}" for c in (r, g, b))

def render_directives(sub_aesthetic: str, seed: int) -> dict:
    cfg = get_awwwards_config(sub_aesthetic)
    pal = cfg["palette"]
    bg = perturb_hex(pal["bg"], seed); fg = perturb_hex(pal["fg"], seed)
    accents = [perturb_hex(a, seed) for a in pal["accents"]]
    supporting = [perturb_hex(c, seed) for c in pal["supporting"]]
    palette_directive = (
        f"Pinned palette (perturbed for this run — use these EXACT hexes as CSS tokens):\n"
        f"  --color-bg: {bg};\n  --color-fg: {fg};\n"
        f"  --color-accent: {accents[0]};\n"
        + "".join(f"  --color-accent-{i+2}: {a};\n" for i, a in enumerate(accents[1:]))
        + "".join(f"  --color-support-{i+1}: {c};\n" for i, c in enumerate(supporting))
        + "This is the only chromatic system on the page. No other accents."
    )
    typ = cfg["typography"]
    typography_directive = (
        f"Primary type class: {typ['primary']}. Hero h1 MUST use font-size: {typ['hero_h1_clamp']} "
        f"(monumental display scale, non-negotiable). Secondary: {typ['secondary']}. "
        f"Tight tracking on display type; generous body line-height."
    )
    motion_directive = (
        "Realize this motion vocabulary with cdnjs GSAP + Lenis (+ SplitType where noted), "
        "SRI + async + graceful degradation:\n- " + "\n- ".join(cfg["motion_vocabulary"])
    )
    return {
        "register_family": cfg["register_family"],
        "palette_directive": palette_directive,
        "typography_directive": typography_directive,
        "photography_prefix": cfg["photography_prefix"],
        "motion_directive": motion_directive,
        "avoid": cfg.get("avoid", []),
    }
```

- [ ] **Step 4: run → PASS.** **Step 5: commit** `git -C /home/deployer/sw-p1a add -A && git -C /home/deployer/sw-p1a commit -m "feat(awwwards): config->directives renderer + seeded palette perturbation"`

---

## Task 2: Art-direction retrieval over the premium corpus

**Files:** add to `scripts/awwwards_render.py`; Test `tests/test_awwwards_retrieval.py`

The retrieval selects the best premium references for `(sub_aesthetic, kit_type)`: semantic over the embedded corpus, then **Python post-filter** — `source in {curated, awwwards}`, `reference_type != listing_frame`, and a kit_type→reference_type rule (`single-product` → `product_marketing`; `editorial-studio` → `studio_site`/`agency_portfolio`/`product_marketing`).

- [ ] **Step 1: failing test** (pure post-filter logic, no network)
```python
# tests/test_awwwards_retrieval.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import awwwards_render as ar

def _pt(source, rtype, title):
    return {"source": source, "reference_type": rtype, "title": title}

def test_kit_type_reference_filter():
    pool = [_pt("curated","product_marketing","airpods"), _pt("curated","studio_site","namma"),
            _pt("awwwards","listing_frame","old"), _pt("dribbble","salon_landing","beauty")]
    sp = ar.filter_refs(pool, kit_type="single-product")
    assert [p["title"] for p in sp] == ["airpods"]                  # product_marketing only, no listing_frame/dribbble
    ed = ar.filter_refs(pool, kit_type="editorial-studio")
    assert set(p["title"] for p in ed) == {"airpods","namma"}       # studio+product, exclude listing_frame & dribbble
```

- [ ] **Step 2: run → FAIL.**

- [ ] **Step 3: implement** — add to `awwwards_render.py`:
```python
_KIT_TYPE_RTYPES = {
    "single-product": {"product_marketing"},
    "editorial-studio": {"studio_site", "agency_portfolio", "product_marketing"},
}
_ALLOWED_SOURCES = {"curated", "awwwards"}

def filter_refs(pool: list[dict], kit_type: str) -> list[dict]:
    allow = _KIT_TYPE_RTYPES[kit_type]
    return [p for p in pool
            if p.get("source") in _ALLOWED_SOURCES
            and p.get("reference_type") != "listing_frame"
            and p.get("reference_type") in allow]

def art_direction_query(sub_aesthetic: str, kit_type: str) -> str:
    from aesthetic_configs import get_awwwards_config
    cfg = get_awwwards_config(sub_aesthetic)
    return (f"{cfg['register_family']} {cfg['typography']['primary']} {kit_type} "
            f"monumental editorial premium award-winning website, full-bleed plates, "
            f"restraint, scroll choreography, signature concept")
```

- [ ] **Step 4: run → PASS. Step 5: commit.**

> The live retrieval (`retrieve_awwwards_refs(sub, kit_type, vault_index)`): `embed(art_direction_query(...))` → `qdrant_query(qvec, limit=30)` → map points to payload dicts → `filter_refs(..., kit_type)` → `rerank` on the art-direction docs → resolve `note_path`/`image_path` via `vault_index` (slug or id). Implement it in `awwwards_render.py` alongside (network path, exercised in Task 7, not unit-tested).

---

## Task 3: Signature-concept step (the premium lever)

**Files:** add `design_concept` prompt block to `skills/workshop-playbook.md`; helper in workshop.py.

- [ ] **Step 1** — add to `workshop-playbook.md` (between markers):
```
>>> BEGIN PROMPT design_concept
You are the Workshop's concept director. Given a sub-aesthetic, its selected hero archetype, the retrieved premium reference notes, and the concepts used by recent kits, commit this kit to ONE bespoke signature idea — the single moment the whole page is built around (a kinetic-type hero, a scroll mechanic, a material/texture motif, a pinned-product reveal, a type-as-image masking, etc.). It must be distinct from the recent concepts listed.

Output ONLY a JSON object: {"signature_move": "...", "hook_name": "...", "rationale": "one line", "placement": "where on the page", "brand_premise": "a thin fictional brand premise the concept answers (survives {{BRAND}} rename)"}.

Sub-aesthetic: {{SUB_AESTHETIC}} ({{REGISTER_FAMILY}})
Kit type: {{KIT_TYPE}}
Hero archetype: {{HERO_ARCHETYPE}}
Reference signature ideas (for inspiration, do NOT copy):
{{REF_SIGNATURE_IDEAS}}
Recent concepts to avoid repeating:
{{RECENT_CONCEPTS}}
<<< END PROMPT design_concept
```

- [ ] **Step 2** — in workshop.py add `run_design_concept(sub, kit_type, hero_archetype, refs, recent, run_dir)`: load template, substitute, `run_claude(effort="medium", tools="", add_dirs=[run_dir])`, `_extract_json_object` the result, write `run_dir/concept.json`, return the dict. (Reuse the existing `_extract_json_object`.) Exercised in Task 7.

- [ ] **Step 3: commit** the playbook + helper.

---

## Task 4: Awwwards brief synthesis prompt

**Files:** add `brief_synthesis_awwwards` block to `workshop-playbook.md`.

- [ ] **Step 1** — the brief consumes the directives (Task 1), the chosen hero archetype + section topology (from the top reference's `hero_archetype`/`section_topology`), the `signature_move` (Task 3), and `kit_type`. It MUST emit a `section_manifest` YAML block (hero_archetype + ordered section types) + the standard brief sections (Aesthetic, Palette = the perturbed tokens verbatim, Typography, Layout/topology, Hero copy seed, the Signature concept as the organizing idea). NO conversion block. Add the block with tokens: `{{SUB_AESTHETIC}} {{REGISTER_FAMILY}} {{KIT_TYPE}} {{PALETTE_DIRECTIVE}} {{TYPOGRAPHY_DIRECTIVE}} {{MOTION_DIRECTIVE}} {{HERO_ARCHETYPE}} {{SECTION_TOPOLOGY}} {{SIGNATURE_MOVE}} {{REFERENCE_NOTES_LIST}}`. (Full block authored inline during implementation, modeled on the existing `brief_synthesis` block but awwwards-shaped and conversion-free.)

- [ ] **Step 2: commit.**

---

## Task 5: Two kit-type generators + per-kit_type required files

**Files:** add `kit_generation_editorial_studio` + `kit_generation_single_product` blocks to `workshop-playbook.md`; `KIT_REQUIRED_FILES_BY_KIT_TYPE` in workshop.py; Test `tests/test_kit_required_files.py`.

- [ ] **Step 1: failing test**
```python
# tests/test_kit_required_files.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import workshop
def test_required_files_per_kit_type():
    es = workshop.KIT_REQUIRED_FILES_BY_KIT_TYPE["editorial-studio"]
    sp = workshop.KIT_REQUIRED_FILES_BY_KIT_TYPE["single-product"]
    assert "index.html" in es and "work.html" in es and "contact.html" in es
    assert "index.html" in sp and "work.html" not in sp          # single-product is one page
    assert "assets/css/style.css" in es and "assets/css/style.css" in sp
    assert "image-prompts.json" in es and "image-prompts.json" in sp
```

- [ ] **Step 2: run → FAIL.**

- [ ] **Step 3: implement** — in workshop.py:
```python
KIT_REQUIRED_FILES_BY_KIT_TYPE = {
    "editorial-studio": ("index.html", "work.html", "contact.html",
                          "assets/css/style.css", "assets/js/main.js", "image-prompts.json"),
    "single-product":   ("index.html",
                          "assets/css/style.css", "assets/js/main.js", "image-prompts.json"),
}
```
Add the two playbook generator blocks: both open with the `{{SIGNATURE_MOVE}}` as the organizing idea, positively prescribe the archetype's topology + the perturbed palette tokens + `hero_h1_clamp` + the motion stack (cdnjs GSAP/Lenis/SplitType, SRI), omit ALL conversion furniture (no CTA-every-page, no click-to-call, no trust block, no GA4/Clarity), keep universal quality (semantic HTML, a11y, lazy-load, picsum + image-prompts.json manifest). `editorial-studio` = monumental hero → manifesto → full-bleed work grid → studio statement → contact (3 pages). `single-product` = full-bleed product hero → pinned product canvas w/ scroll-chapter reveals → spec plates → single CTA (1 page).

- [ ] **Step 4: run → PASS. Step 5: commit.**

---

## Task 6: Oneshot orchestration + CLI flag

**Files:** `scripts/workshop.py`.

- [ ] **Step 1** — add `run_awwwards_oneshot(sub_aesthetic, kit_type, *, deliver=False)`:
  1. `cfg = get_awwwards_config(sub_aesthetic)`; abort if `vault_pending`.
  2. `seed = 0` (CLI default; cron uses visit_counts later).
  3. `directives = awwwards_render.render_directives(sub_aesthetic, seed)`.
  4. `vault_index = build_vault_index()`; `refs = awwwards_render.retrieve_awwwards_refs(sub_aesthetic, kit_type, vault_index)`; require ≥ `min_exemplar_count`.
  5. `hero_archetype, section_topology = refs[0]["payload"]["hero_archetype"], refs[0]["payload"].get("section_topology", [])`.
  6. `concept = run_design_concept(sub_aesthetic, kit_type, hero_archetype, refs, recent=[], run_dir)`.
  7. `synthesize_brief_awwwards(...)` → brief.md (+ section_manifest).
  8. `generate_kit_awwwards(brief, refs, run_dir, kit_type, directives, concept)` — like `generate_kit` but uses the kit_type template + `KIT_REQUIRED_FILES_BY_KIT_TYPE[kit_type]` + awwwards substitutions (no `_aesthetic_substitutions`/`_extract_prior_kits_palettes`).
  9. `generate_kit_images(kit_dir, run_dir, photography_prefix=directives["photography_prefix"])` (pass the prefix explicitly — do NOT route through v1.2 `_resolve_image_prefix`).
  10. `capture_screenshots(kit_dir, run_dir)` using the kit_type's page list (derive PAGES from `KIT_REQUIRED_FILES_BY_KIT_TYPE`).
  11. Write `run_dir` under `workshop/runs/{ts}-awwwards-{sub}-{kit_type}/`. Do NOT deliver/push (deliver=False) — just leave the kit + screenshots for eyeballing.
- [ ] **Step 2** — CLI: in `main()` add `argparse` `--awwwards-oneshot SUB KIT_TYPE`; if present, call `run_awwwards_oneshot` and return (bypasses the conversion queue path entirely).
- [ ] **Step 3** — `capture_screenshots` currently hardcodes `PAGES`; add a `pages` param defaulting to the conversion trio, pass the kit_type pages from the oneshot.
- [ ] **Step 4: commit.**

---

## Task 7: Generate the first premium kit (eyeball)

- [ ] **Step 1: full suite green** `cd /home/deployer/sw-p1a && /opt/scout-workshop/venv/bin/pytest -q`
- [ ] **Step 2: merge to main** (additive; live cron unaffected) `cd /opt/scout-workshop && git merge --no-ff awwwards-v1.5-p1a -m "feat: v1.5 Phase 1a awwwards generation engine (oneshot)" && git worktree remove /home/deployer/sw-p1a`
- [ ] **Step 3: re-point anchors** — set `AWWWARDS_CONFIGS[*].anchor_reference_ids` for the 3 active sub-aesthetics to curated slugs (`studio-namma`, `marvell-tile-stone`, `silent-house`, `t11-creative`); add `kit_type_overrides`-style product anchors (`apple-airpods-pro`, `apple-macbook-pro`, `apple-home`, `apple-iphone`) — or rely on Task 2 retrieval (semantic, kit_type-filtered) which already finds them. Keep anchors as a documented seed.
- [ ] **Step 4: generate one of each kit_type**
```bash
cd /opt/scout-workshop
/opt/scout-workshop/venv/bin/python scripts/workshop.py --awwwards-oneshot warm-earth editorial-studio
/opt/scout-workshop/venv/bin/python scripts/workshop.py --awwwards-oneshot sun-baked single-product
ls -t workshop/runs | head -2
```
- [ ] **Step 5: eyeball** — open the kits' screenshots (`workshop/runs/<slug>/kit/screenshots/*.png`) and judge against the Apple grammar: monumental type, full-bleed, restraint, the signature concept realized, motion present, NO conversion furniture. This is the Phase 1a acceptance gate.

---

## Self-review (coverage)
- Spec §6 register accessor → Task 1. §7 art-direction retrieval → Task 2. §9 concept engine → Task 3. §8 brief → Task 4. §8 two generators + KIT_REQUIRED_FILES → Task 5. Wiring + photography_prefix fix + page-list → Task 6. First kit + anchor re-point → Task 7.
- **Deferred to Phase 1b (correctly):** the 3 gates (diversity/density/craft), retry→ship-flagged, the cron flip (Phase 2), per-run `visit_counts` seed rotation, per-config archetype libraries. Phase 1a proves generation; gates enforce quality next.
- **Known limitation:** seed fixed at 0 for the CLI (variation across runs comes in 1b with `visit_counts`); archetype taken from the top retrieved ref (not yet a config library).

## Execution note
Tasks 1-6 are additive + reversible (worktree). Task 7 merges (safe: additive, empty cron queue) + runs generation (claude cost). The first kit is the milestone to judge before building Phase 1b gates.
