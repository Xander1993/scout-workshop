# Workshop v1.5 — Phase 1b (Quality Gates + retry→ship-flagged) Plan — Rev 2

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use `- [ ]` checkboxes.
>
> **Rev 2** — rewritten after a 4-agent audit that *empirically* disproved Rev 1's metric design. Key changes: (a) deterministic numeric ratios (bleed/hero) are **advisory telemetry, not hard gates** — they don't discriminate premium from template in this design language; the real signals are **template-tells + the visual craft judge**; (b) hero scale is measured by the largest rendered **display-text bounding box** (any tag incl. SVG `<text>`/wordmark), not `<h1>` (the premium editorial kit has zero `<h1>`); (c) a section_manifest **parser** is added (Phase 1a never parsed it); (d) safety fixes: `-flagged` lowercase + dashboard regex, `time.monotonic()` budget baseline, repo-root `state/`, lazy imports, http.server teardown, rename-then-write sequencing, hand-rolled Damerau-Levenshtein.

**Goal:** Make the awwwards register self-policing — a premium kit passes; a kit with conversion-furniture or that repeats a prior structure or that the visual judge calls a template is flagged `below_bar` (retry once, then ship flagged, never go dark). **Both existing real kits MUST pass the calibrated gates** (the editorial kit passing is the acceptance proof — Rev 1 would have failed it).

**Architecture:** Additive on Phase 1a. After generation+screenshots, `run_quality_gate()` runs three signals: (1) **template-tells + density** (deterministic, rendered DOM — the reliable safety floor); (2) **diversity** (structure-weighted signature vs prior kits, non-repetition); (3) **craft judge** (Claude reads screenshots + markup — the premium-vs-template bar, §13-faithful). Numeric bleed/hero ratios are recorded as advisory telemetry. On fail: ONE retry (rotate the hero archetype to the next *distinct* retrieved ref, fresh concept, palette-perturbation OFF, reuse images), guarded by a monotonic budget; then ship FLAGGED.

---

## Verified starting point (from audit)
- `run_awwwards_oneshot` (workshop.py:1213) writes `brief.md` (with a fenced ```yaml section_manifest: `{hero_archetype, sections:[...], signature_move}`), `concept.json`, screenshots, `genericness.json`. **Nothing parses the manifest** (only `if "section_manifest" not in out: warn`, :1179). No `manifest.json` written. PyYAML 6.0.1 available; Damerau-Levenshtein NOT available (hand-roll).
- The editorial kit renders its wordmark as SVG `<text class="wordmark">` → **0 `<h1>`** (Rev-1's hero metric breaks). Both kits' top-level `<section>`s are full-width → bleed saturates ~1.0.
- `capture_screenshots(kit_dir, run_dir, pages=)` (workshop.py:760) = the loopback+Playwright+`finally`-teardown harness to copy. `HTTP_PORT` shared (sequential ok).
- Dashboard `RUN_SLUG_RE` (dashboard/app.py:38) is `[a-z0-9-]+$` (lowercase) → use `-flagged` + widen regex. Dashboard reads repo-root `state/quality_floor_telemetry.jsonl` (app.py:29).
- `render_directives(sub, seed)` (awwwards_render.py:36), one call site (workshop.py:1229) + test (test_awwwards_render.py:16) — adding `perturb=True` default keeps both green.

## File structure
- Create: `scripts/awwwards_manifest.py` (parse+validate brief→manifest.json), `scripts/render_metrics.py` (Playwright DOM metrics), `scripts/diversity_gate.py` (signature+DL+store), `scripts/craft_judge.py`
- Create tests: `test_awwwards_manifest.py`, `test_render_metrics.py` (vs the 2 real kits), `test_diversity_gate.py`
- Modify: `scripts/workshop.py` (`run_quality_gate`+retry in `run_awwwards_oneshot`, **lazy imports**), `skills/workshop-playbook.md` (`audit_craft_awwwards`), `scripts/awwwards_render.py` (`perturb` param), `dashboard/app.py` (widen `RUN_SLUG_RE`)
- Create: `scripts/quality_floor_config.py`

## Task 0: Branch + worktree
- [ ] `cd /opt/scout-workshop && git stash push -u -m p1b dashboard/static/ 2>/dev/null; git branch awwwards-v1.5-p1b && git worktree add /home/deployer/sw-p1b awwwards-v1.5-p1b` ; implement there.

## Task 1: section_manifest parser (the missing input — hard-fail)
**Files:** Create `scripts/awwwards_manifest.py`; Test `tests/test_awwwards_manifest.py`.
- [ ] **Step 1: failing test** — `parse_manifest(brief_text)` extracts the first ```yaml … ``` fence, `yaml.safe_load`s it, returns `{hero_archetype, sections:[...], signature_move}`; raises `ManifestError` if absent/unparseable; `validate(m)` checks `hero_archetype ∈ structural_schema.HERO_ARCHETYPES` and every `sections` item ∈ `structural_schema.SECTION_TYPES`. Test on a real brief.md (read `workshop/runs/*editorial-studio*/brief.md`) → returns a manifest with a valid hero_archetype; test a brief with no fence → raises.
- [ ] **Step 2-3: implement** (regex `` ```yaml\n(.*?)\n``` `` DOTALL; yaml.safe_load; validate). **Step 4: PASS. Step 5: commit.**
- [ ] (Phase-1a touch-up) In `run_awwwards_oneshot`, after writing brief.md, `m = awwwards_manifest.parse_manifest(brief.read_text()); (run_dir/"manifest.json").write_text(json.dumps(m))` — hard-fail the run if it doesn't parse (the gates require it).

## Task 2: render_metrics.py — robust DOM metrics (hero-by-bbox, template-tells)
**Files:** Create `scripts/render_metrics.py`; Test `tests/test_render_metrics.py`.
- [ ] **Step 1: failing test** — `render_metrics(kit_dir, page_file="index.html")` serves + Playwright-renders + returns `{display_hero_px, body_px, hero_scale_ratio, bleed_ratio, max_vertical_void_px, page_height_px, template_tells:[...]}`. Test against BOTH real kits (read-only): **the editorial kit MUST yield `hero_scale_ratio >= 4` and `template_tells == []`** (Rev-1 failed this — the acceptance proof); the single-product kit yields `template_tells == []` and a non-trivial `hero_scale_ratio`.
- [ ] **Step 2-3: implement.** Reuse `capture_screenshots`' http.server Popen + readiness poll + **`finally` terminate→wait(5)→kill** teardown. `page.evaluate`:
  - `display_hero_px` = max over `h1,h2,[class*="wordmark"],[class*="mark"],[class*="hero"] :is(h1,h2,svg,text), svg text` of `getBoundingClientRect().height` (the largest rendered display element, tag-agnostic → catches SVG wordmarks). `body_px` = parseFloat(getComputedStyle(body).fontSize). `hero_scale_ratio = display_hero_px / body_px`.
  - `bleed_ratio` = fraction of top-level `<section>` with `rect.width >= 0.95*innerWidth` — **recorded as advisory telemetry only** (it saturates; not a gate input).
  - `max_vertical_void_px` = largest y-gap between consecutive visible text/img boxes (density `vertical_void`).
  - `template_tells` (rendered DOM): any visible `[class*="trust"],[class*="badge"],[class*="avatar"],[class*="testimonial"]`; a row of ≥3 sibling `[class*="card"],[class*="service"]`; `a[href^="tel:"]`; ≥2 repeated `.cta`/pill buttons; a tiny hero (`hero_scale_ratio < 3`).
- [ ] **Step 4: PASS** (calibrated so the editorial kit passes). **Step 5: commit.** (Supersedes the string `genericness_proxy` for the gate.)

## Task 3: diversity_gate.py — structure-weighted signature (+ hand-rolled DL)
**Files:** Create `scripts/diversity_gate.py`; Test `tests/test_diversity_gate.py`.
- [ ] **Step 1: failing test** — `_damerau_levenshtein(a,b)` (hand-rolled, list-of-tokens) + `signature(manifest, render_m, concept) -> dict` + `distance(a,b)` = `0.35·[archetype≠] + 0.30·topo_DL_norm + 0.20·grid_or_typescale_diff + 0.15·[concept≠]` (palette excluded) + `is_repeat(sig, priors, threshold=0.34)`. Test: identical archetype+topology → distance<0.34; distinct archetype → ≥0.35; empty priors → not repeat.
- [ ] **Step 2-3: implement.** signature = `{archetype, ordered_section_types (from manifest.sections), type_scale_bucket (round hero_scale_ratio), concept_bucket (hash of concept hook)}`. Store `state/structural_signatures.json` (repo-root `state/`, bounded ring keyed by `register_family`); `record(sig, family)` / `priors(family)`. **Step 4: PASS. Step 5: commit.**

## Task 4: craft_judge.py + `audit_craft_awwwards` (§13-faithful visual bar)
**Files:** Create `scripts/craft_judge.py`; add playbook block.
- [ ] **Step 1** — add `audit_craft_awwwards` block: Claude reads the kit's screenshots **and the HTML/CSS/JS markup** (so motion + signature can be judged from code, not just a static frame), scores each criterion 0-3 with evidence: monumentality, restraint, composition, motion_realized (from markup), signature_moment (is {{SIGNATURE_MOVE}} executed?). Instruction: **score structure/markup, NOT placeholder-image fidelity (images may be SVG placeholders).** template_tells list. Output JSON `{scores, template_tells, verdict, reasons}`. **§13-faithful rule:** `verdict = below_bar if ANY score == 0, OR signature_moment < 2, OR monumentality < 2, OR len(template_tells) >= 2, OR weighted_sum < threshold; else pass.`
- [ ] **Step 2** — `craft_judge.run(run_dir, kit_dir, kit_type, concept, shots)`: substitute (incl. screenshot + kit_dir paths), `run_claude(effort="medium", add_dirs=[kit_dir], tools="Read")`, `_extract_json_object`, write `craft_verdict.json`. **No screenshots ⇒ `{"verdict":"below_bar","reasons":"no-screenshots"}` (never crash).** Commit.

## Task 5: run_quality_gate + retry→ship-flagged (with all safety fixes)
**Files:** `scripts/workshop.py`, `scripts/quality_floor_config.py`, `dashboard/app.py`, `scripts/awwwards_render.py`.
- [ ] **Step 1** — `quality_floor_config.py`: `QUALITY_FLOOR = {"diversity_reject_below":0.34, "hero_scale_min":4, "template_tells_max":1, "vertical_void_max_px":{"awwwards":{"editorial-studio":900,"single-product":1600}}, "craft_weighted_min":11, "retry":{"max":1,"disable_palette_perturb_on_retry":True,"reuse_images":True}, "run_budget_s":5400}`.
- [ ] **Step 2** — `render_directives(sub, seed, perturb=True)`: when `perturb=False`, use pinned palette verbatim. Update the call site (workshop.py:1229) + test.
- [ ] **Step 3** — widen `dashboard/app.py` `RUN_SLUG_RE` to allow a trailing `(-flagged)?` (keep lowercase). (So flagged runs stay visible.)
- [ ] **Step 4** — `run_quality_gate(run_dir, kit_dir, kit_type, register_family, manifest, concept)` (lazy-import render_metrics/diversity_gate/craft_judge INSIDE the function so a module error can't kill the cron main()): rm=render_metrics; det_ok = `rm.hero_scale_ratio>=hero_scale_min and len(rm.template_tells)<=template_tells_max and rm.max_vertical_void_px<=void_max[kit_type]`; sig=diversity_gate.signature(...); repeat=is_repeat(sig, priors(family)); craft=craft_judge.run(...). `passed = det_ok and not repeat and craft["verdict"]=="pass"`. Record sig; append a telemetry line to repo-root `state/quality_floor_telemetry.jsonl`. Return verdict {passed, reasons, rm, craft}.
- [ ] **Step 5** — extend `run_awwwards_oneshot`: add `t0 = time.monotonic()` at entry. After screenshots: `v = run_quality_gate(...)`. If `not v.passed` and `time.monotonic()-t0 < run_budget_s`: ONE retry — fresh `run_design_concept` (avoid prior hook) + `synthesize_brief_awwwards` with `hero` = the next retrieved ref whose `hero_archetype` differs from attempt 1 (record `retry_archetype_from→to`; if none differs, rotate concept only) + `generate_kit_awwwards` with `render_directives(sub, seed, perturb=False)`; reuse images; re-screenshot; re-gate. **Identical-output guard:** if attempt-2 `raw_kit_output.txt` == attempt-1, skip re-gate → flagged. If still `not passed`: write `DO_NOT_DEPLOY` + `verdict.json` INTO run_dir, THEN `run_dir = run_dir.rename(run_dir.with_name(run_dir.name + "-flagged"))`, THEN use the new path. Always append telemetry. Commit.

## Task 6: calibrate + merge + audit
- [ ] Suite green (esp. `test_render_metrics` asserting the EDITORIAL kit passes — the Rev-1 regression). Merge to main (additive). **`python scripts/workshop.py --dry-run` must still reach the conversion readiness gate** (proves the cron path is intact + lazy imports work).
- [ ] Re-run the oneshot for both kit_types; confirm: manifest.json written, gate runs, the editorial-archetype kit PASSES, a deliberately-thin kit flags `-flagged` + `DO_NOT_DEPLOY` + telemetry line, dashboard still lists the flagged run.
- [ ] Eyeball + read `verdict.json`/`craft_verdict.json`. Acceptance: premium passes, weak flagged, cron untouched.

## Explicitly deferred (documented, not silently dropped)
- **§11 template/premium CENTROID similarity** (`template_sim`/`premium_sim`): deferred — a centroid over ~3 kits is statistically meaningless; threshold/tell-based detection substitutes until the corpus is large. (Config carries no unused centroid keys.)
- **§10 per-section `required_elements`** + the **brief-time predicted-signature precheck**: deferred to a later pass; the post-generation diversity gate covers repetition for now. `structural_schema` parity obligation noted.
- **§12 `article_density`**: folded into `substantial_sections`/`template_tells` (single-product is one long page; standalone article-density is ambiguous).

## Rollback
Additive: `git reset --hard fe2222c` or revert the merge. State side-effects: `state/structural_signatures.json` + `state/quality_floor_telemetry.jsonl` (delete-safe) + any `-flagged` run dirs (rename back). No vault/Qdrant mutation in the gate path.
