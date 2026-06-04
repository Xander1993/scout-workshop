# Workshop v1.5 — Phase 1a (Awwwards Generation Engine — first runnable kit) Plan — Rev 2

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use `- [ ]` checkboxes.
>
> **Rev 2** — rewritten after a 4-agent audit. Fixes: `generate_kit_images` needs a new `image_prefix_override` param (no `photography_prefix` today); `capture_screenshots` needs a `pages` param (hardcodes `PAGES`); the 3 prompt blocks are now authored in full (not "inline"); model-free genericness proxies pulled forward so the eyeball is backed by numbers; matched-ref **screenshots** passed to the generator; argparse/import-validator safety.

**Goal:** Make the awwwards register *produce one real premium kit end-to-end* via an additive `--awwwards-oneshot <sub_aesthetic> <kit_type>` CLI — register-aware config accessor, art-direction retrieval over the bootstrapped premium corpus, a per-run **signature-concept** step, an awwwards brief, the two kit-type generators, and a model-free genericness readout. **No cron change, no gates, no delivery.** Gates/flip are Phase 1b/2.

**Architecture:** Additive. `main()`'s conversion path is untouched; a new `run_awwwards_oneshot()` + an optional `--awwwards-oneshot` flag (early-return before `load_queue()`) drive the awwwards pipeline. Premium-ness is carried by STRUCTURE (archetype + section topology from the matched premium refs) + a bespoke per-run signature CONCEPT + densely-prescribed generator prompts + the matched refs' actual screenshots. Palette perturbation is cosmetic, NOT the diversity lever (per design §11/§14). The empty cron queue means merging is safe.

**Tech Stack:** Python 3.12 (`/opt/scout-workshop/venv`), pytest, Qdrant, `claude --print`, Playwright. Corpus: `vault/references/curated/` (8 premium refs, embedded: 5 product_marketing, 2 agency_portfolio, 1 studio_site; all carry hero_archetype/section_topology/signature_idea).

---

## Verified facts (from audit)
- `get_awwwards_config(sub)` returns palette{bg,fg,accents[],supporting[]}, typography{primary,hero_h1_clamp,secondary}, photography_prefix, motion_vocabulary[], register_family, avoid[]. Active: sun-baked/warm-earth/editorial-mid-century (restrained-monumental). `get_awwwards_config` RAISES KeyError on unknown but RETURNS for vault_pending → oneshot must check `vault_pending` explicitly.
- `run_claude(prompt,*,effort,add_dirs,tools,...)` — `tools=""` is the CLI-documented way to disable tools (safe for the concept step). `load_prompt_template` reads `>>> BEGIN PROMPT <name>` / `<<< END PROMPT <name>`. `_extract_json_object` exists. `build_vault_index` keys by frontmatter id AND dir slug.
- `generate_kit_images(kit_dir, run_dir, aesthetic_direction=None)` — **no photography_prefix param** (must add `image_prefix_override`). `capture_screenshots(kit_dir, run_dir)` — **hardcodes module `PAGES`** (must add `pages` param). `_send_telegram_kit`/`deliver` are NOT called by the oneshot (deliver=False).
- `scout_lib.embed(text,image_path=None)`, `qdrant_query(vec,filters=None,limit=20)`, `rerank(query,candidates,top_n=5)→[{index,relevance_score,document}]`.
- Import of `aesthetic_configs` runs `_validate_awwwards_configs()` (asserts anchor_reference_ids non-empty XOR vault_pending; does NOT resolve slugs). A syntax/invariant error there **breaks the live Sunday cron** → always `python -c "import aesthetic_configs"` after editing it.
- `aesthetic_configs.py` anchor_reference_ids currently use `<hash>-slug` form; curated dirs are **bare slugs** (`studio-namma`, `apple-airpods-pro`). Use bare slugs when re-pointing.

## File structure
- Create: `scripts/awwwards_render.py` (config→directives, perturbation, retrieval helpers), `scripts/genericness_proxy.py` (model-free template-vs-premium metrics)
- Create tests: `tests/test_awwwards_render.py`, `test_awwwards_retrieval.py`, `test_kit_required_files.py`, `test_genericness_proxy.py`
- Modify: `scripts/workshop.py` (run_awwwards_oneshot + KIT_REQUIRED_FILES_BY_KIT_TYPE + capture_screenshots `pages` param + CLI flag), `scripts/generate_kit_images.py` (`image_prefix_override` param), `skills/workshop-playbook.md` (4 prompt blocks)

---

## Task 0: Branch + worktree (additive); stash live dirty tree
- [ ] `cd /opt/scout-workshop && git stash push -u -m "p1a-preflight dashboard WIP" dashboard/static/ 2>/dev/null; git branch awwwards-v1.5-p1a && git worktree add /home/deployer/sw-p1a awwwards-v1.5-p1a`
- Implement Tasks 1-6 in `/home/deployer/sw-p1a`; tests via `/opt/scout-workshop/venv/bin/pytest`. (Restore dashboard WIP after merge: `git stash pop`.)

## Task 1: Awwwards render module (config → directives + seeded palette)
*(Unchanged from Rev 1 — `scripts/awwwards_render.py` with `perturb_hex(hex,seed)` bounded HLS shift + `render_directives(sub,seed)` returning palette_directive/typography_directive/photography_prefix/motion_directive/register_family/avoid. Tests: determinism+bounds+format, directives contain `--color-bg`/`clamp(`/motion. **Docstring reframe:** "Palette perturbation is COSMETIC variation, not the premium/diversity lever — structure (archetype+concept) carries premium. Per design §11/§14 palette is a tie-breaker.")* Implementation identical to Rev 1 Task 1 Step 3. Commit.

## Task 2: Art-direction retrieval (`filter_refs` + live `retrieve_awwwards_refs`)
*(Unchanged from Rev 1 — `filter_refs(pool,kit_type)` post-filter [source∈{curated,awwwards}, reference_type≠listing_frame, kit_type→{single-product:product_marketing; editorial-studio:studio_site/agency_portfolio/product_marketing}] + `art_direction_query`. Test the pure filter.)* PLUS the live `retrieve_awwwards_refs(sub,kit_type,vault_index,k=4)`: embed→`qdrant_query(qvec,limit=30)`→payload dicts→`filter_refs`→`rerank`→resolve note_path/image_path via vault_index. **Guard the invariant:** skip any survivor whose payload lacks `hero_archetype` (`if not p["payload"].get("hero_archetype"): continue`) rather than bare-key access. Require ≥`min_exemplar_count` survivors else raise. Commit.

## Task 3: `generate_kit_images` — add `image_prefix_override` (NEW code-modify)
**Files:** `scripts/generate_kit_images.py`; Test: extend `test_awwwards_render.py` or a small unit.
- [ ] **Step 1** — read `generate_kit_images.py` `_resolve_image_prefix` + the `generate_kit_images(kit_dir, run_dir, aesthetic_direction=None)` signature.
- [ ] **Step 2** — add a param: `generate_kit_images(kit_dir, run_dir, aesthetic_direction=None, image_prefix_override=None)`. At the point it computes the prefix, `prefix = image_prefix_override if image_prefix_override else _resolve_image_prefix(aesthetic_direction)`. (Additive; conversion path passes no override → unchanged.)
- [ ] **Step 3** — unit test: calling with `image_prefix_override="EDITORIAL X"` uses it (monkeypatch the image API or assert the prefix is threaded into the manifest-prompt path). Minimal: assert the function accepts the kwarg and the override wins over `_resolve_image_prefix`. Commit.

## Task 4: `capture_screenshots` — add `pages` param + robustness (NEW code-modify)
**Files:** `scripts/workshop.py`.
- [ ] **Step 1** — change `capture_screenshots(kit_dir, run_dir)` → `capture_screenshots(kit_dir, run_dir, pages=PAGES)`; replace the loop's use of module `PAGES` with the param. (Conversion path calls with default → unchanged.)
- [ ] **Step 2** — change `wait_until="networkidle"` → `wait_until="load"` + `page.wait_for_timeout(2500)` settle (GSAP/Lenis kits may never reach networkidle within 20s). Keep `full_page=True`.
- [ ] **Step 3** — no new test (Playwright/IO); exercised in Task 7. Commit.

## Task 5: Design-concept prompt (the premium lever)
*(Unchanged from Rev 1 — `design_concept` block + `run_design_concept(...)` helper writing `concept.json` via `_extract_json_object`, `run_claude(effort="medium", tools="")`.)* Commit.

## Task 6: The three awwwards prompt blocks (authored IN FULL)

Add to `skills/workshop-playbook.md`. These are authored here (not "inline") because they must positively prescribe premium structure and explicitly strip conversion furniture.

### 6a. `brief_synthesis_awwwards`
```
>>> BEGIN PROMPT brief_synthesis_awwwards
You are the Workshop's awwwards brief synthesizer. Turn the directives + premium references + the chosen signature concept into ONE structured brief for a monumental/editorial ({{REGISTER_FAMILY}}) kit. NO conversion content. First character of output must be `#`.

Begin with a YAML section_manifest block, then the brief. Exact manifest shape:
```yaml
section_manifest:
  hero_archetype: {{HERO_ARCHETYPE}}
  sections: [<ordered list from this enum: full_bleed_plate, work_grid, manifesto, spec_table, scroll_chapter, studio_statement, product_hero, monumental_wordmark, callout>]
  signature_move: <one line — the bespoke idea from below>
```
Then:
# Brief — {{SUB_AESTHETIC}} / {{KIT_TYPE}}
## Aesthetic
2-4 sentences on the feel. Reference the premium notes you Read by name.
## Signature concept (the organizing idea — the page is SUBORDINATE to this)
Restate {{SIGNATURE_MOVE}} and how every section serves it.
## Palette
Use these EXACT perturbed hex tokens verbatim as CSS custom properties (do NOT invent or range):
{{PALETTE_DIRECTIVE}}
## Typography
{{TYPOGRAPHY_DIRECTIVE}}
## Layout / topology
Map the section_manifest sections to concrete full-bleed compositions. {{HERO_ARCHETYPE}} hero. Monumental scale, generous negative space, alternating light/dark plates.
## Motion
{{MOTION_DIRECTIVE}}
## Hero copy seed
One headline (<=8 words) + one subhead (<=18 words), brand premise: a fictional brand the concept answers.
## Reference notes (Read each)
{{REFERENCE_NOTES_LIST}}

Avoid (other sub-aesthetics' territory): {{AVOID_LIST}}
End there. No conversion structure, no CTA-placement section, no trust signals.
<<< END PROMPT brief_synthesis_awwwards
```

### 6b/6c. `kit_generation_editorial_studio` and `kit_generation_single_product`
Both blocks share this spine (authored once per block, with the kit-type-specific files + topology):
```
>>> BEGIN PROMPT kit_generation_<KITTYPE>
You are the Workshop's awwwards kit generator. Build a PREMIUM, monumental/editorial static kit. The page is SUBORDINATE TO ONE IDEA: {{SIGNATURE_MOVE}} — if a section doesn't serve it, cut it. This is award-tier work, not a template.

# Read first
- Brief: {{RUN_DIR}}/brief.md   - Concept: {{RUN_DIR}}/concept.json
- Premium reference screenshots (study the COMPOSITION — full-bleed plates, scale, restraint): {{REF_IMAGE_1}} {{REF_IMAGE_2}} {{REF_IMAGE_3}}

# Files (exact — <KITTYPE> set)
[editorial-studio]: index.html, work.html, contact.html, assets/css/style.css, assets/js/main.js, image-prompts.json
[single-product]: index.html, assets/css/style.css, assets/js/main.js, image-prompts.json

# Positive premium mandates (REQUIRED)
- Hero h1 font-size MUST be the clamp from the brief (monumental display scale). Hero text / body text size ratio >= 6x.
- Full-bleed single-subject plates; >=60% of sections are full-bleed (bleed_ratio >= 0.6). Generous negative space. Alternating light/dark rhythm.
- Use the brief's EXACT palette hex tokens verbatim. One disciplined accent system, nothing else.
- Realize the motion vocabulary via cdnjs GSAP + Lenis (+ SplitType where the concept calls for kinetic type): <script src=cdnjs ... integrity=... crossorigin=anonymous async>. Graceful degradation if blocked.
- [editorial-studio] topology: monumental hero -> manifesto -> full-bleed work grid -> studio statement -> contact.
- [single-product] topology: full-bleed product hero (headline bottom-left) -> pinned product canvas with scroll-chapter feature reveals -> spec/detail plates -> ONE closing CTA.

# HARD EXCLUSIONS (these are conversion furniture — DO NOT EMIT)
- No "primary CTA above the fold on every page", no repeated header CTA. No `tel:` click-to-call. No GA4 / Microsoft Clarity head snippets. No trust-signals/badge/avatar block. No {{PHONE_E164}} / business-hours / services-card grid. No rounded-pill bootstrap buttons.

# Universal quality (KEEP)
Semantic HTML5, one <h1>/page, correct heading nesting, mobile-first CSS, lazy-load + width/height on below-fold <img>, fetchpriority=high on hero img, descriptive alt text. Placeholder images use https://picsum.photos/seed/{image-id}/{w}/{h} and an image-prompts.json manifest (same schema as the conversion block: keys=image-ids, values={html_path,alt_text,generation_prompt (editorial/award register, end 'no text or logos.'),aspect_ratio in 1:1|4:3|3:4|16:9|9:16,placement}).

# Output protocol
Use Write for each file. Then print one line: `KIT WRITTEN`. Brand tokens: {{BRAND}} verbatim.
<<< END PROMPT kit_generation_<KITTYPE>
```
- [ ] Add `KIT_REQUIRED_FILES_BY_KIT_TYPE` (editorial-studio: index/work/contact + assets; single-product: index + assets) with the test from Rev 1 Task 5. Commit.

## Task 7: Genericness proxy (model-free; pulled forward from design §11)
**Files:** `scripts/genericness_proxy.py`; Test `tests/test_genericness_proxy.py`.
- [ ] **Step 1: failing test** — `score_kit(kit_dir)` returns `{bleed_ratio, hero_body_ratio, template_tells:[...], verdict}` from parsing the kit HTML/CSS. Test on two fixtures: a synthetic "template" HTML (3-card grid + trust strip + small hero) → high template_tells, low bleed; a "premium" HTML (full-bleed plates + clamp hero) → low tells, high bleed.
- [ ] **Step 2-4** — implement deterministic parsing: `bleed_ratio` = fraction of `<section>` that are full-bleed (width:100vw / no max-width container / `.bleed`-ish), `hero_body_ratio` = parsed hero h1 font-size vs body font-size (from CSS/clamp max), `template_tells` = presence of {trust/badge/avatar class, a 3-item card grid, repeated `.cta`/pill, `tel:` link}. `verdict` = "premium-leaning" if bleed≥0.5 and hero_body≥4 and tells≤1 else "template-leaning". Run → PASS. Commit. (This is also the seed of the Phase 1b §11 detector.)

## Task 8: Oneshot orchestration + CLI flag
**Files:** `scripts/workshop.py`.
- [ ] `run_awwwards_oneshot(sub_aesthetic, kit_type)`:
  1. `cfg = get_awwwards_config(sub)`; if `cfg["vault_pending"]: raise SystemExit("sub-aesthetic is vault_pending")`.
  2. `seed = 0`; `directives = awwwards_render.render_directives(sub, seed)`.
  3. `vault_index = build_vault_index()`; `refs = retrieve_awwwards_refs(sub, kit_type, vault_index)`.
  4. `hero = refs[0]["payload"].get("hero_archetype", "monumental_wordmark")`; `topo = refs[0]["payload"].get("section_topology", [])`.
  5. `concept = run_design_concept(sub, kit_type, hero, refs, recent=[], run_dir)`.
  6. `synthesize_brief_awwwards(...)` → brief.md; **assert** `"section_manifest" in brief.read_text()` (1b gates depend on it) else log warning.
  7. `generate_kit_awwwards(brief, refs, run_dir, kit_type, directives, concept)` — uses `kit_generation_<kit_type>` template, `KIT_REQUIRED_FILES_BY_KIT_TYPE[kit_type]`, passes top-3 refs' `image_path` as `{{REF_IMAGE_n}}`, the perturbed palette/typography/motion directives, and `{{SIGNATURE_MOVE}}` from concept. No `_aesthetic_substitutions`/`_extract_prior_kits_palettes`.
  8. `try: generate_kit_images(kit_dir, run_dir, image_prefix_override=directives["photography_prefix"]) except (ImageGenError, Exception) as e: log.warning(...)` (mirror main()'s non-fatal handling).
  9. `pages = [f[:-5] for f in KIT_REQUIRED_FILES_BY_KIT_TYPE[kit_type] if f.endswith(".html")]`; `try: capture_screenshots(kit_dir, run_dir, pages=pages) except Exception: log.warning(...)`.
  10. `gp = genericness_proxy.score_kit(kit_dir); log.info("genericness: %s", gp); (run_dir/'genericness.json').write_text(json.dumps(gp))`.
  11. run_dir = `workshop/runs/{ts}-awwwards-{sub}-{kit_type}/`. No deliver.
- [ ] CLI: `parser.add_argument("--awwwards-oneshot", nargs=2, metavar=("SUB","KIT_TYPE"))`; in `main()` **immediately after parse, before `acquire_lock()`/`load_queue()`**: `if args.awwwards_oneshot: run_awwwards_oneshot(*args.awwwards_oneshot); return 0`. (Optional flag → no-arg cron unaffected.) Commit.

## Task 9: Run + eyeball (the milestone)
- [ ] **Suite green:** `cd /home/deployer/sw-p1a && /opt/scout-workshop/venv/bin/pytest -q`
- [ ] **Re-point anchors (bare slugs)** in aesthetic_configs.py active configs → `["studio-namma","marvell-tile-stone","silent-house","t11-creative"]` (editorial) + product seeds; then **`/opt/scout-workshop/venv/bin/python -c "import sys;sys.path.insert(0,'scripts');import aesthetic_configs;print('import OK')"`** (proves the live cron still imports).
- [ ] **Merge** (live tree clean — dashboard WIP stashed in Task 0): `cd /opt/scout-workshop && git merge --no-ff awwwards-v1.5-p1a -m "feat: v1.5 Phase 1a awwwards generation engine (oneshot)" && git worktree remove /home/deployer/sw-p1a && git stash pop` ; `/opt/scout-workshop/venv/bin/pytest -q`
- [ ] **Generate two DIFFERENT archetypes** (probe diversity, not the same masthead):
```bash
/opt/scout-workshop/venv/bin/python scripts/workshop.py --awwwards-oneshot sun-baked single-product      # product_canvas_pinned (Apple refs)
/opt/scout-workshop/venv/bin/python scripts/workshop.py --awwwards-oneshot warm-earth editorial-studio    # monumental_wordmark (studio refs)
```
- [ ] **Eyeball + numbers:** open `workshop/runs/<slug>/kit/screenshots/*.png`; read `genericness.json` for each (expect `verdict: premium-leaning`, bleed_ratio ≥ 0.5, hero_body_ratio ≥ 4, template_tells empty). Judge against the Apple grammar. This is the Phase 1a acceptance gate — if a kit reads generic, the prompt blocks (Task 6) need tightening before Phase 1b.

## Self-review (coverage)
- Code-modify gaps fixed: generate_kit_images override (Task 3), capture_screenshots pages+robustness (Task 4). Prompts authored in full (Task 6). Genericness proxies pulled forward (Task 7) — backs the eyeball + seeds §11. Ref screenshots passed to generator (Task 8.7). argparse optional + early-return + import check (Task 8/9). Palette reframed cosmetic (Task 1).
- **Deferred to 1b (correct):** the 3 enforcing gates + retry→ship-flagged, per-config archetype libraries + no-byte-twins validator, visit_counts seed rotation, cron flip (Phase 2). Phase 1a proves generation + gives a numbers-backed eyeball; 1b enforces.

## Rollback
Additive: `git reset --hard 913d698` (or revert the merge). Anchor edit is the only import-validated change — the Task 9 import check gates it. Worktree disposable. No vault/Qdrant/delivery mutations.
