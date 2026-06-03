# Workshop v1.5 — Awwwards Register + Premium-Concept Engine

Design spec. Authored 2026-06-03.

Status: drafted via superpowers brainstorming + three rounds of multi-agent adversarial review (spine soundness, v1.4 reconciliation, a 4-seat design council on premium quality). Pending Alex review before the implementation plan (writing-plans).

> This revision supersedes the first v1.5 draft. The council established that the original "flip the register" plan was necessary plumbing but **insufficient for premium output**, for three reasons it then fixed: (1) the awwwards corpus is a *sourcing artifact* — one masthead frame captured 12×, not a diverse library; (2) the design enforced structural non-repetition but had no **concept** object to enforce over; (3) the gates measured palette and rewarded the masthead archetype. The design now sequences **corpus re-sourcing → structure + a signature-concept engine → gated shipping**.

---

## 1. Problem & goal

Every kit the Workshop ships looks like the same generic conversion template; only the palette changes. The dormant `AWWWARDS_CONFIGS` registry (scripts/aesthetic_configs.py ~784–1168) encodes the monumental/editorial vocabulary we want (clamp display type, GSAP/Lenis motion, award-site palettes) but `workshop.py` imports only the v1.2 `get_config`, so it is dead code.

**Goal:** produce genuinely *premium*, distinctive websites (awwwards / Apple-grade) — not interchangeable templates — from the weekly cron.

### What "premium" actually is (grounding)

Captured live from apple.com / iphone / airpods-pro / macbook-pro (full-page, headless Chromium; in `/tmp/apple-shots/`). The premium signal is **one committed idea executed with craft over a long scroll**: full-bleed single-subject plates, monumental type as composition, photography (often in motion) as the hero, alternating light/dark rhythm down 13k–30k px pages, radical restraint (one accent; no trust badges / phone bars / service-card grids). Apple's *home* is monumental restraint; Apple's *product pages* are monumental *ideas* (a pinned product canvas, scroll-chapter reveals, a motif). A template has none of this — it is interchangeable.

### Two root causes the council surfaced

1. **The corpus is monocultural by sourcing artifact.** All 12 awwwards anchors are captures of **awwwards.com's `/sites/<slug>` listing frame**, not the award-winning sites themselves (the Studio Namma screenshot shows awwwards chrome with the real site as a thumbnail; the notes say "the real spectacle is on the linked site"). The `madeinwordpress` control — captured from real site URLs — yields genuine diversity (NOMA = full-bleed photo hero), proving the sameness is upstream in `scout-playbook.md` (it scrapes the listing page, `fullPage:false`), not in the model.
2. **There is no generative slot for "the idea."** The pipeline can satisfy every structural gate while shipping archetype #1 with a new texture. Premium requires a **signature concept** as a first-class, varied, gate-enforced artifact.

### Realistic ceiling (honest)

Within the locked constraints (weekly autonomous cron; brand-agnostic `{{BRAND}}` kits; static HTML/CSS/JS + GSAP/Lenis; retry-once→ship-flagged): **consistent awwwards Honorable-Mention / Mobile-Excellence, occasional Site-of-the-Day on strong runs; not reliable SOTD; essentially never the bespoke-WebGL spectacle tier.** The one genuinely premium-hostile constraint is the `{{BRAND}}` rename (a real signature concept is often brand-specific) — mitigated by a thin fictional "concept brief" per kit (§9) that survives rename.

## 2. Locked decisions

From the brainstorm + three review rounds:

- **Deliverable:** both kit-types, one per run via a `kit_type` flag — `editorial-studio` (3-page studio kit) and `single-product` (Apple-style one-product scrollytelling).
- **Single-product = invest now:** harvest real Apple/product-page anchors + author its archetype library *before* the first flip.
- **Conversion demoted, not deleted:** reachable only via `register: "conversion"`; default is `awwwards`.
- **Failure mode:** retry once → ship flagged "below bar" (never go dark). Flagged = `DO_NOT_DEPLOY` quarantine, not an endorsement.
- **v1.4 relationship:** fold in (review variant V1) — reuse `section_manifest`, deterministic density, retry/telemetry/dashboard rails; supersede halt→ship-flagged; leave conversion `self_audit` behind.
- **Council synthesis (this revision):** sequence **C → (A + concept layer), B as cadence** — fix sourcing first (binding constraint), add per-sub-aesthetic structure + a signature-concept engine, keep the ship-once-flagged discipline. Pure precision-fixes (B) was rejected as shipping "the same template one level up."

## 3. Build ordering (one spec, sequenced phases)

The user chose the full-pipeline build (no incremental shipping), but the council found a **hard prerequisite**: the gates and generators operate on `hero_archetype` / `section_topology` signals that do not exist in the corpus or schema today. So the single spec lands in dependency order:

- **Phase 0 — Corpus & schema (prerequisite).** Fix scout sourcing; add the shared structural schema; re-harvest a diverse corpus + Apple-style product anchors. Nothing flips until readiness passes on the new corpus.
- **Phase 1 — Register + concept engine + gates.** The `workshop.py` spine, config archetype libraries, the signature-concept step, the three gates, retry/ship-flagged, naming/migration.
- **Phase 2 — Flip + observe.** Atomic deploy into the idle cron window; dashboard surfaces concept distribution + flagged backlog.

## 4. Relationship to the unbuilt v1.4 plan

v1.4 is contracts-only (design doc + impl plan + register-aware read-only dashboard + pytest fixtures; **no gate code on disk**). Disposition:

| v1.4 asset | v1.5 disposition |
|---|---|
| Brief `section_manifest` (Gate A) | **Reuse + extend** — add `hero_archetype`, `signature_concept`, and the new section-type enum |
| Deterministic density (Gate B.1) | **Reuse but invert the rule** — "≥2 case_grid" is a *template-tell*, not a pass (§11) |
| `wordmark_treatment` density check | **Drop** — the v1.4 *impl plan* already removed it ("no reliable selector"); Gate B.1 = 4 checks |
| Gate B.2 Claude brief-coverage | **Drop/absorb** into the craft judge |
| Gate C retry harness | **Reuse; supersede halt → ship-flagged** |
| `quality_floor_config` + `register_overrides` | **Reuse; add `kit_type` overrides** |
| Telemetry JSONL + dashboard | **Reuse; add `flagged`/`concept`/diversity fields + a flagged-backlog view** (dashboard has no `flagged` concept today) |
| Test fixtures (probe-5 pass, May-17 fail) | **Reuse** for calibration |
| Conversion `self_audit` | **Leave behind** — runs only for `register: conversion` |

## 5. Phase 0 — Corpus re-sourcing & shared schema

**Scout sourcing fixes (`skills/scout-playbook.md`):**
- **Dereference** the awwwards `/sites/<slug>` page to the real outbound site URL ("Visit site") and capture *that*, not the listing frame.
- `screenshot.fullPage: true` + per-plate crops, so the alternating-plate scroll rhythm (the biggest premium signal) is actually recorded.
- Add sources beyond awwwards-SOTD: Godly (godly.website), a brutalist-style directory, and a curated **Apple-style product-page seed list** (apple.com/{iphone,airpods,watch}, Nothing, Teenage Engineering, Polestar, Linear, Arc, Framer/Vercel product pages) tagged `reference_type: product_marketing`.
- Spread per-run picks across archetypes (anti "top-6 of one SOTD date").
- A capture-quality check rejects near-blank/loader screenshots (the most interactive award sites are the most capture-fragile).

**Shared structural schema (defined once, four consumers — scout note frontmatter, the reranker, the Gate-A manifest, the diversity signature):**
- `hero_archetype` — enum: `monumental_wordmark`, `full_bleed_photo_hero`, `split_editorial`, `kinetic_type`, `product_canvas_pinned`, `immersive_canvas`.
- `section_topology` — ordered enum list: `full_bleed_plate`, `work_grid`, `manifesto`, `spec_table`, `scroll_chapter`, `studio_statement`, `product_hero`, …
- `motion_signature` — tag set: `splittype_stagger`, `scroll_pin`, `lenis_smooth`, `parallax`, `webgl_canvas`, `none` (promotes the §20-deferred motion field into scope).
- `signature_idea` — free text capturing the *one idea* of the reference (explicitly NOT "reusable 3-block skeleton"); grounds the concept bank (§9) in real corpus.

**Re-harvest targets / readiness:**
- Anchor **pool ≥5** per `(sub_aesthetic × kit_type)` spanning **≥3 distinct `hero_archetype`s**; per-run subset (`min_exemplar_count`) stays 2–3 so subset rotation is non-degenerate (today warm-earth/editorial-mid-century have exactly 2 → rotation is a no-op).
- The 12 existing listing-frame captures are re-tagged `reference_type: listing_frame` and **excluded** from anchor pools (kept only as negative examples).
- **Readiness requires ≥2 distinct `hero_archetype`s** resolvable for a `(sub_aesthetic, kit_type)` cell — otherwise the diversity gate has nothing to diversify against, and the cell stays gated (`vault_pending`-equivalent).

**Schema migration:** scout backfill defaults; `build_vault_index`, ingest daemon, and rerank default-handle missing fields; lands atomically with the spine (§19).

## 6. Routing & queue

```json
{
  "register": "awwwards",
  "rotation": [
    {"sub_aesthetic": "sun-baked",             "kit_type": "single-product"},
    {"sub_aesthetic": "warm-earth",            "kit_type": "editorial-studio"},
    {"sub_aesthetic": "editorial-mid-century", "kit_type": "single-product"},
    {"sub_aesthetic": "warm-earth",            "kit_type": "single-product"},
    {"sub_aesthetic": "sun-baked",             "kit_type": "editorial-studio"},
    {"sub_aesthetic": "editorial-mid-century", "kit_type": "editorial-studio"}
  ],
  "cursor": 0,
  "visit_counts": {},
  "conversion_enabled": false
}
```

- `pick_target` returns `rotation[cursor]`, advances `cursor` mod len, increments `visit_counts["<sub_aesthetic>:<kit_type>"]`; `variation_seed = visit_counts[key]` (deterministic per-cell counter → drives archetype/concept/anchor-subset selection so the Nth run of a cell differs from the 1st).
- Rotation is filtered through `known_awwwards_sub_aesthetics(active_only=True)` (vault_pending self-skip).
- **Single-product readiness uses product-page anchors** (`kit_type_overrides.single_product.anchor_reference_ids`, empty until harvest, and/or `reference_type: product_marketing` filter) — **not** the studio anchors. Without this, single-product cells would pass against mastheads (the "product name on a masthead" failure §2 forbids). `cursor:0` is a single-product cell → **skipped day-one** until product anchors resolve (expected, not a bug).
- `load_queue` is schema-guarded (malformed JSON → loud alert, exit 0); writes are atomic (tmp+replace). Runtime `queue.json` is gitignored/host-written; only `queue.json.example` is tracked.

## 7. Retrieval (art-direction + anchors)

- **Slug→id bridge (blocking fix):** anchor IDs are directory slugs (`989723a6-studio-namma`); `build_vault_index()` keys on the frontmatter `id:` UUIDv5 (`81cdf982-…`) — zero overlap. Add a second index keyed on `note.parent.name`; unit-test that every active anchor resolves. (All 5 active anchors verified to resolve under the slug index.)
- **Anchor-subset rotation:** select `min_exemplar_count`-of-pool via a `variation_seed` window, biased to span ≥2 `hero_archetype`s.
- **Art-direction retrieval:** rerank on the shared structural fields (`hero_archetype`, `section_topology`, `motion_signature`, `color_mood`, `typography_style`) — replacing the conversion CTA query and the old `color_mood/typography_style/layout_pattern`-only rerank. The conversion `build_query_text` is used only for `register: conversion`.

## 8. Generation — configs, two kit-types, no monoculture

**Register-aware accessor (blocking fix):** `_aesthetic_substitutions` (workshop.py) and `_resolve_image_prefix` (generate_kit_images.py:97) currently call v1.2 `get_config`, which returns the conversion-wellness `DEFAULT_CONFIG` for awwwards names and KeyErrors on the dict-shaped fields. Add an awwwards accessor reading `get_awwwards_config()` (`palette` dict, `typography.hero_h1_clamp`, `photography_prefix`, `motion_vocabulary`).

**Kill the byte-identical DNA (the core anti-sameness move):**
- **`hero_archetype` library per `sub_aesthetic × kit_type`** (2–4 entries, **disjoint across sub-aesthetics in the same `register_family`**), each a terse *compositional contract* (grid topology, wordmark placement, fold rhythm) — **not** literal CSS (literal CSS was the original sin). Selected by `variation_seed % len`. This is the structural axis the diversity gate and the brief-time precheck need an input for.
- **Differentiate `hero_h1_clamp` and `motion_vocabulary` per sub-aesthetic** (a serif at 12rem ≠ a grotesque at 12rem): per-style type-laws + a distinctive primary motion move over a common Lenis substrate.
- **`no-byte-twins` validator** (import-time): assert no two active sub-aesthetics share an identical `hero_h1_clamp` or identical first-3 `motion_vocabulary`, and no shared `hero_archetype` name within a `register_family`. Collapse becomes a load-time error, not silent drift.

**`KIT_REQUIRED_FILES` from the manifest (blocking fix):** driven by `kit_type` — `editorial-studio` → `index/work/contact.html`; `single-product` → `index.html` (+ enumerated `assets/css/style.css`, `assets/js/main.js`, `image-prompts.json`). The single-product file set is enumerated explicitly so the §18 file-existence test is writable.

**Two kit-type prompt templates** (new playbook blocks), both: positively prescribe the selected archetype's topology (removal alone regresses — the model back-fills conversion defaults), open with the **signature concept** (§9) as the organizing idea, realize the motion signature via cdnjs GSAP/Lenis/SplitType (SRI + async + graceful degradation), and omit conversion furniture. `editorial-studio`: monumental hero → manifesto → full-bleed work grid → studio statement → contact. `single-product`: full-bleed product hero → pinned product canvas with scroll-chapter reveals → spec/detail plates → single CTA.

**Single-product config (invest-now):** `kit_type_overrides.single_product` adds the product-section vocabulary + product-glamour `photography_prefix` + relaxed `avoid` (a product page legitimately repeats a buy CTA). Its archetype library is authored **from harvested product-page exemplars**, not invented; gated until anchors resolve.

**Pipeline-order fix:** image-gen stays **before** screenshots; delete the `strip_picsum_audit_concerns` coupling (a conversion-compliance notion the craft judge owns/drops).

**Page-list threading (blocking fix):** `PAGES`, `capture_screenshots`, and the Telegram delivery `order` tuple are hardcoded to `index/services/contacts`. Derive the page list from `kit_type`/manifest and thread it through capture + delivery — otherwise awwwards kits `goto` a missing `services.html`, capture zero screenshots, and the craft judge (which reads screenshots) auto-flags everything.

## 9. The signature-concept engine (highest-leverage addition)

The premium-vs-template boundary is **a committed idea**, so the concept becomes a first-class artifact:

- **Concept bank:** a curated, rotating set of ~8–12 distinct *mechanisms* (kinetic-type hero, horizontal scroll-chapter, pinned-product canvas, material/texture motif, editorial-grid rupture, oversized-cursor interaction, type-as-image masking, scroll-reactive color shift), grounded in the new `signature_idea` reference field.
- **`design_concept` step** (new cheap `--effort medium` Claude call, *before* the section_manifest): given the config + selected archetype + anchor subset + prior kits' concepts, commit to ONE `signature_move` for this kit — `concept.json: {signature_move, hook_name, rationale, placement, brand_premise}`. `brand_premise` is the thin fictional brand premise the concept answers (survives the `{{BRAND}}` rename). Threaded verbatim into generation; the page is subordinated to this one idea ("one idea per screen" promoted from observation to instruction).
- **Cross-occurrence rule:** the same `(sub_aesthetic, kit_type)` cell must not reuse the same concept on consecutive visits.

## 10. Gate A — manifest + brief-time precheck

Reuse v1.4's `section_manifest` (YAML → validated `manifest.json`), extended: `hero_archetype` populated from the selected library entry; new section-type enum values (`monumental_wordmark`, `manifesto`, `work_grid`, `product_hero`, `scroll_chapter`, `spec_table`, `studio_statement`) **each with per-type `required_elements`** (matching v1.4's existing entries — deliberately extends v1.4's "enum stable" policy); a reference to the `signature_move` so later gates can verify it shipped. **Brief-time predicted-signature precheck:** derive the structural signature from the manifest before generation; collision with a prior kit in the same `register_family` ⇒ re-synthesize the brief once (cheapest retry point).

## 11. Gate F — structure-weighted diversity + first-occurrence genericness

New module `scripts/diversity_gate.py`.

**Structure-weighted signature** (palette demoted to tie-breaker — the residual leak in the prior draft):
```
sig = { archetype, ordered_section_types, grid_bucket(max_cols, asymmetry, bleed_ratio),
        type_scale_bucket(hero_h1_px ÷ body_px), concept_bucket, palette_bucket(tie-break only) }
```
- Distance `D = 0.35·[archetype≠] + 0.25·topo_levenshtein + 0.15·grid_diff + 0.10·type_scale_diff + 0.15·[concept≠]`; **palette weight 0.0 in D** (used only as an exact-tie / identical-hex boolean). (Weights fold the council's structure axes + the concept axis; calibrate against fixtures.)
- Topology distance = normalized Damerau-Levenshtein over the section-type sequence.
- **Reject (too-similar) if `min D over prior kits in same register_family < 0.34`.** Derivation: the 3 shipped kits score `D ≈ 0.04`; two genuinely distinct archetypes score `≥ 0.35` from the archetype term alone. Compare cross-sub-aesthetic within `register_family` (where the sameness lives), bounded ring N=12. Empty store ⇒ auto-pass + record.

**First-occurrence genericness detector** (fires even on kit #1 — the gate the prior draft lacked):
- `TEMPLATE_centroid` (the proven masthead/conversion skeleton, derivable today from the 3 shipped kits) vs `PREMIUM_centroid` (full-bleed-plate grammar from the Apple shots + probe-5).
- **Flag if `template_sim > 0.70 AND premium_sim < 0.45`**, regardless of store emptiness. Deterministic proxies (no model call): `bleed_ratio` (premium ≥0.6 / template ≤0.2), `hero_h1_px ÷ body_px` (premium ≥6× / template ≤3×), presence of template tells {trust strip, 3-icon-card grid, repeated CTA furniture}. Single-product's PREMIUM centroid is gated behind the product-anchor harvest (warn-only until then).

## 12. Gate B.1 — density (reuse v1.4, inverted for awwwards)

Author `scripts/density_audit.py` per v1.4, parameterised by `register` + `kit_type`, **4 checks** (`substantial_sections`, `vertical_void`, `article_density`, `hero_h1_word_cap`; `wordmark_treatment` dropped). **Invert the masthead-rewarding rule:** for awwwards, "≥2 case_grid" is a *template-tell*, not a pass; require "≥N full-bleed single-idea plates, ≤1 multi-card grid." Thresholds via `quality_floor_config.py` with `register_overrides["awwwards"]` + `kit_type` overrides (single-product is one long page; calibrate `vertical_void_max_px` away from the May-17 fixture's ~700px boundary).

## 13. Gate H — craft judge (premium-vs-template, with veto)

New prompt `skills/audit_craft_awwwards.md`, replacing `self_audit` for awwwards; reads the **screenshots**. Per-criterion evidence-scored (0–3) + thresholds, parameterised by `kit_type`:
- **Monumentality**, **Restraint**, **Composition** (full-bleed plates / negative space / alternating rhythm), **Motion realised** (libs actually present), **Photographic depth**.
- **Signature moment** — is the per-run `signature_move` present, executed (not declared-only), and distinct from the last N concepts? (Makes the concept enforceable.)
- **`template_tells` (veto)** — if ≥2 of {trust strip, 3-icon-card grid, repeated CTA furniture, hero/body < 3×} are present, **verdict = below_bar even if Monumentality/Restraint/Composition all pass.** Breaks the "rubric rewards the masthead" trap.
- **Aggregation:** `pass` iff no criterion scores 0, the `template_tells` veto does not fire, and the weighted sum ≥ the kit_type threshold; else `below_bar`. **Screenshots absent ⇒ skip judge, `below_bar` (`no-screenshots`), never crash.**

## 14. Retry / flag orchestration

Extends v1.4's Gate-C harness; halt → ship-flagged:
- One retry on any gate fail, **guarded by `RUN_BUDGET_S ≈ 6000s`** (checked before the retry; `run_claude` worst case 3660s/phase; ~25 min margin under `TimeoutStartSec=7500`).
- Retry **advances a deterministic `archetype_rotation_order`** and rotates the anchor subset/concept; **palette perturbation is disabled on retry** (palette-rotation is the proven no-op). Reuse images for unchanged image-ids; re-screenshot; re-judge.
- Second attempt byte-identical ⇒ ship flagged, no loop.
- **Ship-flagged is enforcing, not advisory:** flagged kit ships to `runs/<slug>/` with a `DO_NOT_DEPLOY` sentinel, a `-FLAGGED` name suffix, and `flagged:true, flag_reasons:[...]` in telemetry; Telegram delivers a **triage card** (failing axis, both attempts' screenshots, `ship-anyway`/`skip`/`requeue-with-archetype` actions) visually distinct from a passing delivery.
- **Trend SLO:** if `flagged_rate` over the trailing 8 runs in a `register_family` > 50%, emit a LOUD weekly alert ("register is producing templates") + auto-requeue the worst cell with forced archetype rotation. (The closest thing to blocking that respects never-go-dark.)

## 15. Delivery, naming, telemetry, dashboard

- Run/kit names keep a literal `awwwards` segment: `{ts}-awwwards-{sub_aesthetic}-{kit_type}[-FLAGGED]` (parses under the real `RUN_SLUG_RE`; `_infer_register` keys on the `awwwards` segment). `deliver()`/`_send_telegram_kit` thread `register`+`sub_aesthetic`+`kit_type` (no `vertical`); single-kit per run.
- `get_awwwards_config` KeyError from a bad queue entry is caught in `main()` → telegram alert (not a silent systemd FAILURE).
- **Telemetry JSONL** adds: `register`, `sub_aesthetic`, `kit_type`, `variation_seed`, `signature_concept`, `diversity_D`, `genericness_template_sim`/`premium_sim`, `template_tells_fired[]`, `craft_per_criterion`, `flagged`, `flag_reasons`, `retry_archetype_from→to`.
- **Dashboard:** add a `flagged` column, a genericness column, a **flagged-backlog view**, and a **concept-distribution chart** (a single concept dominating the rotation is a visible regression, the way palette-sameness was the original tell). Sub_aesthetic/kit_type are read from telemetry, not the fused slug. Dashboard stays read-only.

## 16. Conversion register (demoted / opt-in)

The v1.2 path (`get_config`, conversion query, conversion requirements, `self_audit` booleans) stays intact, reached only via `register: "conversion"`. Reproduces today's behaviour exactly. Default is awwwards.

## 17. State files & config

`queue.json` (+`.example`, new schema); `structural_signatures.json` (ring); per-run `manifest.json`, `concept.json`, `{diversity,density,craft}_verdict.json`, `DO_NOT_DEPLOY` sentinel when flagged; `quality_floor_telemetry.jsonl`; `quality_floor_config.py` (thresholds + `register_overrides` + `kit_type` overrides + retry policy: `max_retries:1`, `ship_flagged_on_fail:true`, `reuse_images_on_retry:true`, `stop_on_identical_retry_output:true`, `run_budget_s:6000`, `diversity_reject_below:0.34`, genericness cuts `0.70`/`0.45`, `flagged_rate_slo:0.5`).

## 18. Error handling & failure modes

Malformed queue → loud alert, exit 0. All active cells fail readiness → loud alert, non-zero (never silent dark). `get_awwwards_config` KeyError → telegram alert. Claude phase timeout → existing retry-once-then-abort. Image-gen hard fail → non-fatal (placeholders). Screenshot fail → craft judge skipped, ship flagged `no-screenshots`. Diversity store empty → auto-pass + record. Retry would exceed `RUN_BUDGET_S` → skip retry, ship flagged. Capture-quality fail (loader/blank) → reject ref (scout) / flag (kit).

## 19. Testing strategy

- **Unit:** slug→id resolution; queue rotation + visit_counts/variation_seed; archetype-library selection + `no-byte-twins` validator; anchor-subset rotation; structure-weighted signature + comparator (the 3 shipped kits ⇒ D≈0.04 reject; distinct archetypes ⇒ pass); genericness centroids; concept cross-occurrence; `KIT_REQUIRED_FILES` per kit_type; page-list threading.
- **Calibration (reuse v1.4 fixtures + new):** craft + density + genericness PASS probe-5, FAIL May-17; the 3 shipped kits FAIL the diversity gate as repeats; a single-product fixture passes; a deliberate structural repeat is rejected. Validate the 0.34 / 0.70 / 0.45 cuts before flip.
- **Integration:** `--dry-run` resolves target + anchors + art-direction top-up + concept with no generation.
- **Eyeball:** first real cron output vs the Apple grammar (§1).

## 20. Migration & deployment

Timer is live + enabled (next fire Sun 2026-06-07 01:00 UTC) but the queue is exhausted → safe idle window. Phase 0 (scout + re-harvest) runs first against the idle cron. Deploy the queue-schema swap + spine atomically (old code returns None on the new schema; new code requires it); new `queue.json` written atomically; optionally disable the timer during deploy. The flock makes a mid-deploy fire exit 0.

## 21. Out of scope (deferred)

`acid-tech` / `cool-jewel` (vault_pending until neon/jewel anchors harvested); `immersive_canvas`/WebGL archetypes (capture-fragile, code-gen-unreliable — beyond the ceiling); `vault/wisdom` curated corpus.

## 22. Open risks

- **Single-product is fully contingent on a harvest that hasn't happened** — the vault holds **zero** Apple-style product-page exemplars today (the 3 `product_marketing` notes are SOTD mastheads). Gated cells make this safe (never ship a fake product page) but the quality is promissory; if scout can't source enough product pages, single-product is capped.
- **Outbound-dereference fragility:** the most award-winning sites are the most JS/WebGL-heavy and capture-fragile; capture-quality checks prevent silent degradation back toward the easy-to-capture masthead bias.
- **Archetype/threshold calibration on a small corpus:** the diversity/genericness cuts derive from ~3 kits + probe-5 + Apple shots; validate against fixtures before flip. Mis-flags are bounded by ship-flagged (never dark) + requeue-with-rotation.
- **`{{BRAND}}` rename caps brand-specific concepts** below SOTD; the `brand_premise` mitigation narrows but doesn't erase this.
- **Craft-judge subjectivity** on "signature moment present" inherits audit non-determinism; evidence-scored criteria + the deterministic `template_tells` veto + ship-flagged bound the blast radius.

---

End of design draft. Standing by for review; once approved, the implementation plan is drafted via the writing-plans skill (sequenced Phase 0 → 1 → 2).
