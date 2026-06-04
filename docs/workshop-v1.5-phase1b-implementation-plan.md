# Workshop v1.5 — Phase 1b (Quality Gates + retry→ship-flagged) Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use `- [ ]` checkboxes.

**Goal:** Make the awwwards register *self-policing*. Add the three gates from design §10-14 + the retry→ship-flagged orchestration, wired into the oneshot (and reusable by the Phase 2 cron). Critically — per the Phase 1a finding — the genericness/density metrics are computed from **Playwright rendered/computed styles**, NOT the brittle string heuristics that false-negatived the single-product kit.

**Architecture:** Additive on top of Phase 1a (`run_awwwards_oneshot`). After generation+screenshots, `run_quality_gate()` runs: (A) deterministic **render_metrics** (bleed/hero-scale/void/template-tells from the rendered DOM) → genericness + density verdicts; (B) **diversity_gate** (structure-weighted signature vs prior kits in the register_family); (C) **craft_judge** (Claude reads the screenshots). On fail: ONE retry (rotate archetype/anchor-subset/concept, palette-perturbation OFF, reuse images), then ship FLAGGED `below_bar` (DO_NOT_DEPLOY sentinel + `-FLAGGED` name). Never go dark.

**Tech Stack:** Python 3.12, pytest, Playwright (already used by `capture_screenshots`), Qdrant, `claude --print`. Builds on Phase 1a: `scripts/awwwards_render.py`, `scripts/genericness_proxy.py` (string version — superseded by render_metrics for the gate), `run_awwwards_oneshot`, the 4 prompt blocks.

---

## Verified starting point
- `run_awwwards_oneshot(sub, kit_type)` generates kit + screenshots + writes `genericness.json` (string proxy) + `concept.json` + `brief.md` (with `section_manifest` YAML). Two real kits exist on disk under `workshop/runs/*awwwards-*` (use as fixtures).
- `capture_screenshots(kit_dir, run_dir, pages=...)` serves the kit over `http.server` + Playwright — the render harness to reuse for computed-style metrics.
- Design §11 numeric targets: diversity reject `D < 0.34`; genericness fire if `template_sim > 0.70 AND premium_sim < 0.45`; bleed_ratio premium ≥0.6 / template ≤0.2; hero/body premium ≥6× / template ≤3×.

## File structure
- Create: `scripts/render_metrics.py` (Playwright computed-style metrics — genericness + density substrate), `scripts/diversity_gate.py` (structural signature + store + comparator), `scripts/craft_judge.py` (Claude judge wrapper)
- Create tests: `test_render_metrics.py` (against the 2 real kits), `test_diversity_gate.py` (synthetic signatures), `test_density_rules.py`
- Modify: `scripts/workshop.py` (`run_quality_gate` + retry/flag in `run_awwwards_oneshot`), `skills/workshop-playbook.md` (`audit_craft_awwwards` block), `scripts/quality_floor_config.py` (NEW — thresholds), `dashboard/app.py` (surface `flagged` — optional, can defer to Phase 2)

---

## Task 0: Branch + worktree
- [ ] `cd /opt/scout-workshop && git stash push -u -m p1b-wip dashboard/static/ 2>/dev/null; git branch awwwards-v1.5-p1b && git worktree add /home/deployer/sw-p1b awwwards-v1.5-p1b` ; implement in `/home/deployer/sw-p1b`.

## Task 1: render_metrics.py — Playwright computed-style metrics (fixes the false-negative)
**Files:** Create `scripts/render_metrics.py`; Test `tests/test_render_metrics.py`.
- [ ] **Step 1: failing test** — `render_metrics(kit_dir, page_file)` returns `{bleed_ratio, hero_body_ratio, max_vertical_void_px, page_height_px, template_tells:[...]}` computed from the RENDERED page (serve over loopback + Playwright `page.evaluate`). Test against the TWO real kits on disk: assert the editorial kit reads `bleed_ratio >= 0.5` and `hero_body_ratio >= 6`; assert the single-product kit now reads `bleed_ratio` HIGHER than its string-proxy 0.33 (the false-negative fix) — i.e. computed bleed reflects the real full-bleed sand plates.
- [ ] **Step 2-3: implement** — serve `kit_dir` via `http.server` (reuse the pattern in `capture_screenshots`); Playwright render at 1440×900; `page.evaluate` JS:
  - sections = `[...document.querySelectorAll('section,main>div,header~div')]`; for each, `getBoundingClientRect().width >= 0.95*innerWidth` → full-bleed. `bleed_ratio = full_bleed/total`.
  - hero = largest `getComputedStyle(h1).fontSize` among `h1`; body = `getComputedStyle(document.body).fontSize`; `hero_body_ratio = hero/body`.
  - `max_vertical_void_px` = largest gap between consecutive visible text/img bounding boxes sorted by y (the density `vertical_void` check).
  - template_tells (rendered): elements matching trust/badge/avatar/testimonial; a row of ≥3 `.card`/`.service`; `a[href^=tel:]`; ≥2 repeated `.cta`/pill buttons.
- [ ] **Step 4: run → PASS** (against the real kits). **Step 5: commit.** (This supersedes the string `genericness_proxy` for the gate; keep the old module only for the cheap pre-screenshot log.)

## Task 2: diversity_gate.py — structure-weighted signature + comparator
**Files:** Create `scripts/diversity_gate.py`; Test `tests/test_diversity_gate.py`.
- [ ] **Step 1: failing test** — `signature(manifest, render_m, concept, palette)` → dict; `distance(a, b)` per design §11: `0.35·[archetype≠] + 0.25·topo_levenshtein_norm + 0.15·grid_diff + 0.10·type_scale_diff + 0.15·[concept≠]` (palette weight 0). `is_repeat(sig, prior_list, threshold=0.34)` → True if min distance < 0.34. Test: two identical-archetype identical-topology sigs → distance < 0.34 (repeat); two different-archetype sigs → distance ≥ 0.35 (pass); first-run (empty prior) → not repeat.
- [ ] **Step 2-3: implement** the signature (archetype from manifest, ordered_section_types from manifest, grid_bucket + type_scale_bucket from render_metrics, concept_bucket = hash of concept hook, palette_bucket = quantized bg+accent hue/lightness). Damerau-Levenshtein over section-type sequence (normalized 0-1). Store: `workshop/state/structural_signatures.json` (bounded ring, keyed by register_family). `record(sig)` appends; `priors(register_family)` reads.
- [ ] **Step 4: run → PASS. Step 5: commit.**

## Task 3: density rules (reuse v1.4 logic, awwwards/kit_type overrides, invert case_grid)
**Files:** add to `render_metrics.py` or a `density_rules.py`; Test `tests/test_density_rules.py`.
- [ ] Deterministic checks from render_metrics + the section_manifest: `substantial_sections` (index ≥3 for editorial, ≥3 plates for single-product), `vertical_void` (FAIL if `max_vertical_void_px > overrides[register].vertical_void_max_px` AND `page_height_px < 4000`; awwwards override 700), `hero_h1_word_cap` (no hero word >10 chars). **INVERT** the conversion rule: a 3-item `.card` grid is a template-tell (counts against), not a pass condition. Return `{check: pass/fail, evidence}`. Test the void + substantial + invert rules with synthetic metric inputs.
- [ ] Commit.

## Task 4: craft_judge.py + `audit_craft_awwwards` prompt (Claude reads screenshots)
**Files:** Create `scripts/craft_judge.py`; add `audit_craft_awwwards` to playbook.
- [ ] **Step 1** — add to `workshop-playbook.md`:
```
>>> BEGIN PROMPT audit_craft_awwwards
You are the Workshop's awwwards craft judge. You are shown a generated {{KIT_TYPE}} kit's rendered screenshots and the brief's signature_move. Judge: is this award-tier premium, or a template? Read each screenshot file. Output ONLY a JSON object.
Score each 0-3 with one-line evidence:
- monumentality (hero type at true display scale?), restraint (one disciplined accent, no template furniture?), composition (full-bleed plates, negative space, alternating rhythm?), motion_realized (markup shows real GSAP/Lenis/scroll motion, not declared-only?), photographic_depth (substantial on-palette imagery; if images are SVG placeholders score 2/NA), signature_moment (is {{SIGNATURE_MOVE}} actually executed in the page, not just named?).
- template_tells: list any of {trust strip, 3-icon card grid, repeated CTA bar, click-to-call, tiny hero}.
Output: {"scores": {...}, "template_tells": [...], "verdict": "pass"|"below_bar", "reasons": "<=2 lines"}.
Rule: verdict = below_bar if signature_moment < 2 OR monumentality < 2 OR len(template_tells) >= 2; else pass.
Kit type: {{KIT_TYPE}}. signature_move: {{SIGNATURE_MOVE}}. Screenshots: {{SHOT_HOME}} {{SHOT_2}}
<<< END PROMPT audit_craft_awwwards
```
- [ ] **Step 2** — `craft_judge.run(run_dir, kit_type, concept, screenshots)`: substitute + `run_claude(effort="medium", add_dirs=[kit_dir], tools="Read")`, `_extract_json_object`, write `craft_verdict.json`. **Screenshot-absent rule:** if no screenshots, return `{"verdict":"below_bar","reasons":"no-screenshots"}` (never crash). Exercised in Task 6.
- [ ] Commit.

## Task 5: run_quality_gate + retry→ship-flagged orchestration
**Files:** `scripts/workshop.py`, `scripts/quality_floor_config.py` (new).
- [ ] **Step 1** — `quality_floor_config.py`: `QUALITY_FLOOR = {"diversity_reject_below":0.34, "genericness":{"template_sim":0.70,"premium_sim":0.45,"bleed_min":0.5,"hero_body_min":4}, "vertical_void_max_px":{"awwwards":700}, "retry":{"max":1,"disable_palette_perturb_on_retry":True,"reuse_images":True}, "run_budget_s":6000}`.
- [ ] **Step 2** — `run_quality_gate(run_dir, kit_dir, kit_type, register_family, manifest, concept, directives)`: compute render_metrics → genericness verdict (bleed<bleed_min or hero_body<hero_body_min or template_tells≥2 → fail) + density checks; diversity signature vs priors (record after); craft_judge. Combined `passed = genericness_ok and density_ok and not diversity_repeat and craft.verdict=="pass"`. Return a verdict object with reasons.
- [ ] **Step 3** — extend `run_awwwards_oneshot`: after screenshots, `result = run_quality_gate(...)`. If not passed and within `run_budget_s`: ONE retry — re-run concept (rotate, avoid prior concept) + brief (next archetype from the retrieved refs, or `cfg` archetype rotation) + kit-gen, **palette perturbation OFF** (seed reused → render_directives gets `perturb=False`), reuse images; re-screenshot; re-gate. If still not passed: rename run_dir with `-FLAGGED`, write `DO_NOT_DEPLOY` sentinel + `flag_reasons` in a `verdict.json`. Always record the signature + a telemetry line to `state/quality_floor_telemetry.jsonl`. Log the verdict.
- [ ] **Step 4** — add `render_directives(sub, seed, perturb=True)` param (perturb off → use pinned palette verbatim). Commit.

## Task 6: end-to-end + merge + audit
- [ ] Suite green. Merge `awwwards-v1.5-p1b` → main (additive). Import check.
- [ ] Re-run the oneshot for both kit_types; confirm: gate runs, render_metrics fixes the single-product false-negative (computed bleed reflects reality), craft_judge returns a verdict, a deliberately-thin kit gets flagged `-FLAGGED` + `DO_NOT_DEPLOY`, telemetry line written.
- [ ] Eyeball + read `verdict.json`/`craft_verdict.json`. Phase 1b acceptance: a premium kit passes all gates; the gates *enforce* (a weak kit is flagged, not silently shipped).

## Self-review (coverage vs design §10-14)
- §11 diversity (structure-weighted, palette=0, D<0.34, register_family ring) → Task 2. §11 genericness (computed bleed/hero, template-tells) → Task 1 (**Playwright, fixing the Phase 1a string false-negative**). §12 density (reuse + invert case_grid + awwwards void override) → Task 3. §13 craft judge (screenshots, per-criterion, signature-executed, template_tells veto, kit_type) → Task 4. §14 retry→ship-flagged (one retry, archetype rotation, palette-off-on-retry, reuse images, budget guard, DO_NOT_DEPLOY/-FLAGGED, telemetry) → Task 5.
- **Deferred to Phase 2:** the cron flip (queue rotation with visit_counts seed), dashboard `flagged` surfacing, un-deferring acid-tech/cool-jewel. Phase 1b makes the oneshot self-policing; Phase 2 automates it weekly.

## Rollback
Additive: `git reset --hard fe2222c` or revert the merge. No state/vault/Qdrant mutations except the additive `structural_signatures.json` + telemetry JSONL (safe to delete).
