# Workshop v1.3 bootstrap — technical execution document

For VPS Claude executing in `/opt/scout-workshop/` on srv1420550 (Tailscale 100.110.49.44, deployer user).

The conceptual spec lives in `workshop-v1.3-description.md` (Alex approved). This document is the execution plan. If the two ever disagree, the description doc wins; flag it and ask Alex.

---

## How to use this document

Eight phases (Phase 0 through Phase 7), executed in order. After each phase, halt and report back per that phase's "Halt criteria" section. Do not proceed to the next phase without Alex's explicit go.

This document is the approved spec. Do **not** use Superpowers `/brainstorming` to re-litigate the spec itself — Alex and chat Claude already brainstormed it through five iterations. Brainstorming is reserved for specific sub-task decisions where this document is genuinely ambiguous (one such case exists in Phase 1, flagged below). Everywhere else, the spec is authoritative.

Other Superpowers skills are encouraged where they add value, not as overhead:
- `/test-driven-development` for new code in `workshop.py` (Phases 3, 4, 5) — RED-GREEN-REFACTOR catches regressions before commit
- `/writing-plans` if a phase's task list feels unclear — break it into your own sub-tasks before executing
- Subagent code review before each commit — fresh subagent reads diff against spec, flags drift
- `/systematic-debugging` if Phase 7 integration test fails — root-cause before changing code
- Skip Superpowers for data-only changes (config dicts, markdown edits, one-line tweaks) — overhead exceeds value

Superpowers' session-start-hook may suggest reading `getting-started/SKILL.md` again. You've already loaded it (per Alex's screenshot). Don't reload. Proceed with this document.

---

## Pre-execution context

### Repository layout (must match this on session start)

```
/opt/scout-workshop/
├── scripts/
│   ├── workshop.py             (v1.2 — modify in Phases 3-5)
│   ├── scout.py                (don't touch — Scout owns this)
│   ├── ingest_daemon.py        (don't touch — Scout owns this)
│   ├── aesthetic_configs.py    (v1.2 — extend in Phase 1)
│   ├── generate_kit_images.py  (v1.2 — monkey-patch at runtime only, no permanent edit)
│   └── reaction_poller.py      (v1.2 — don't touch)
├── skills/
│   ├── scout-playbook.md       (don't touch)
│   └── workshop-playbook.md    (v1.2.1 — extend in Phase 2)
├── workshop/
│   ├── kit-template/           (v1.2 conversion-register template — don't touch)
│   ├── kit-template-awwwards/  (NEW — create in Phase 3)
│   ├── state/queue.json        (v1.2 schema — extend in Phase 6)
│   └── runs/                   (ephemeral per-run dirs, gitignored)
├── systemd/                    (don't touch — Phase 7 may need timer reload only)
└── docs/                       (drop v1.3 ADRs and notes here)
```

Output repo (separate, on the same VPS): the kits repository. Verify path on Phase 0; recent past sessions had it at `/opt/camelotflows-kits/` but confirm.

### Baseline sha256 hashes (verify all match on Phase 0)

These are the v1.2 protected files. If any differ from baseline on Phase 0, **halt and report** — do not auto-correct.

```
workshop-playbook.md                          a64c99d6
aesthetic_configs.py                          f07a180a
generate_kit_images.py                        506ebef5
kit-template/README.md                        b8e14ccd
kit-template/assets/css/style.css             c3c41b56
kit-template/assets/js/main.js                d14e297b
kit-template/contacts.html                    babacd00
kit-template/index.html                       03842af1
kit-template/services.html                    20d0f3af
```

(First 8 chars only. Run `sha256sum <path> | cut -c1-8` to compare.)

### Existing VPS services — never touch

`hermes-qdrant-vps` container (Qdrant on localhost:6333 — Workshop reads only its own `scout_workshop` collection; `hermes_knowledge` and `dreamscape_studio` collections are off-limits), `n8n`, `OpenClaw` + `NemoClaw`, `Hermes Agent`, `hermes-gateway-vps`. Workshop's ports stay in the 8200-8210 range. If any Phase touches Docker, isolate volumes and namespaces from these services.

### What v1.3 adds (recap — description doc has the long version)

Two new mechanisms on top of nine components:

- **Mechanism 1 (empirical anchoring):** each non-sun-baked sub-aesthetic config is built from 2-3 exemplar SOTDs identified during Phase 1, not from abstract mood words.
- **Mechanism 2 (vault-gated rotation):** Workshop verifies anchor refs are present in vault before generating a sub-aesthetic kit. If not, skip in rotation.

Nine components:
1. New awwwards aesthetic family in `aesthetic_configs.py` (5 sub-aesthetics, exemplar-anchored)
2. New `self_audit_awwwards` prompt in `workshop-playbook.md`
3. Awwwards kit-template variant in `workshop/kit-template-awwwards/`
4. Orchestration-time URL+SRI pre-flight in `workshop.py`
5. Palette-aware photography prefix in `workshop.py` (runtime monkey-patch of `generate_kit_images`)
6. Source-HTML leak scan in `workshop.py` (replaces Playwright innerText scan)
7. Hero h1 word-length cap in `workshop-playbook.md` kit_generation prompt
8. Hard reference diversification with fail-loud in `workshop.py`
9. Vault-gated rotation in `workshop.py`

---

## Phase 0 — Pre-flight + plan

### Goal

Verify v1.2 baseline intact, infrastructure ready, dependencies present. Write the bootstrap plan to disk for Alex review before any modification.

### Steps

1. **Confirm Superpowers loaded.** From `/using-superpowers` skill state — should already be active per Alex's screenshot.

2. **Verify baseline sha256 hashes** for the 9 protected files listed above. Use `sha256sum <path> | cut -c1-8` and compare. If any differ:
   - Output the diff to terminal
   - Halt immediately
   - Do NOT auto-correct or proceed
   - Wait for Alex to investigate

3. **Verify repository state.**
   - `cd /opt/scout-workshop && git status` — should be clean
   - `git log -1 --oneline` — record current HEAD
   - `cat workshop/state/queue.json | jq` — record current state (v1.2 was `completed: 7/7, remaining: []`)
   - `find /opt /home -maxdepth 4 -name "camelotflows-kits" -type d 2>/dev/null` — locate output repo exactly
   - In output repo: `git log -1 main --oneline` (expect `72c7fb6` restrained-luxury-warm-v2), `git tag | grep awwwards-probe` (expect 5 tags), `git branch -a | grep experimental` (expect the probe branch)

4. **Verify vault state.**
   - `find /opt/scout-workshop/vault/references/ -name "*.md" | wc -l` — record total ref count
   - `find /opt/scout-workshop/vault/references/awwwards/ -name "note.md" | wc -l` — record awwwards ref count
   - Check Scout cron: `systemctl status scout.timer` — verify timer active, last fire recent. If not running: **report only, don't restart from Workshop session** — that's a separate concern.

5. **Verify Qdrant accessibility.**
   - `curl -s localhost:6333/collections/scout_workshop | jq .result.points_count` — record point count
   - Compare to vault file count. They should roughly match (some lag is fine).

6. **Verify Python dependencies present.**
   - `python3 -c "import httpx, hashlib, playwright; print('ok')"` — should print `ok`
   - `playwright install --dry-run chromium` — verify Chromium installed
   - If any missing: record but do NOT install yet. Phase 0 is read-only.

7. **Verify port range 8200-8210.**
   - `ss -tlnp | grep -E ':820[0-9]'` — should return nothing (no conflicts)
   - If any port in range occupied by another service: record which, halt for Alex.

8. **Save the iteration report and probe-iter.py to permanent location** (if still in /tmp).
   - If `/tmp/awwwards-probe-iteration-report.md` exists: `cp` to `/opt/scout-workshop/docs/awwwards-probe-iteration-report-2026-05-10.md`
   - If `/tmp/awwwards-probe-iter.py` exists: `cp` to `/opt/scout-workshop/docs/awwwards-probe-iter-2026-05-10.py.ref` (rename .ref so it's not mistaken for executable)
   - If files missing (likely if VPS rebooted): ask Alex to provide them — he has them.

9. **Write bootstrap plan** to `/opt/scout-workshop/docs/v1.3-bootstrap-plan.md` containing:
   - Date/time of Phase 0 execution
   - All Phase 0 step results (baseline hash table, repo state, vault state, Qdrant state, dependency state, port state)
   - Any anomalies found
   - Estimated time per subsequent phase based on what you see
   - Open questions for Alex

### Halt criteria

Report to Alex:
- Single line per Phase 0 step (PASS / FAIL / ANOMALY)
- Link to `/opt/scout-workshop/docs/v1.3-bootstrap-plan.md`
- Any blocker that requires Alex's input before Phase 1 (most commonly: hash mismatch, port conflict, missing iteration report)

Wait for Alex's go before Phase 1.

### Don't

- Don't modify any of the 9 protected files
- Don't `pip install` anything — Phase 0 is verification only
- Don't start `/brainstorming` — there's nothing ambiguous in Phase 0
- Don't try to restart Scout services if you find them down

---

## Phase 1 — Exemplar anchoring + awwwards aesthetic family (Mechanism 1)

This is the highest-judgment phase. Outcome quality of the entire v1.3 register depends on it.

### Goal

For each of 4 unvalidated sub-aesthetics (acid-tech, cool-jewel, warm-earth, editorial-mid-century), identify 2-3 exemplar Awwwards SOTDs and build their `aesthetic_configs.py` entries from those exemplars. Sun-baked already has anchors from probe-5.

### Superpowers usage in this phase

**This is the one phase where `/brainstorming` is genuinely useful.** Exemplar identification is ambiguous, requires Alex's taste, benefits from dialog. Invoke `/brainstorming` before proposing exemplars. Pattern:

1. For each unanchored sub-aesthetic, analyze the existing vault first (read `note.md` frontmatter from `/opt/scout-workshop/vault/references/awwwards/*/note.md`, filter by `color_mood` / `typography_style` / `layout_pattern` markers that intuitively match the sub-aesthetic name).
2. Present 3-5 vault candidates per sub-aesthetic to Alex through brainstorming questions.
3. Alex confirms 2-3 exemplars (may also propose external SOTDs not yet in vault — see below).
4. If Alex names external SOTDs not in vault: these need one-time injection. Two options:
   - Wait for Scout to organically collect them (slow, uncertain)
   - One-time manual ingest via Scout's existing pipeline — invoke `scout.py` with the specific URL as a single-target run. This is out-of-band but the cleanest way to get specific exemplars in vault.

After exemplars confirmed, **stop brainstorming**. The rest of the phase (config building) is mechanical extraction from the exemplar refs.

### Steps

1. **Vault analysis pass.** For each of 4 sub-aesthetics, read all current `awwwards/*/note.md` notes (under `/opt/scout-workshop/vault/references/awwwards/`) and shortlist candidates matching the sub-aesthetic's mood:
   - **acid-tech:** neon palette markers, dark backgrounds, terminal/cyberpunk typography, motion-heavy
   - **cool-jewel:** deep saturated palette (emerald/sapphire/ruby), glossy textures, editorial composition
   - **warm-earth:** terracotta/sienna/ochre palette, organic curves, earthy textures
   - **editorial-mid-century:** muted print-magazine palette, serif headlines, grid-heavy layout

2. **Brainstorm with Alex** (Superpowers `/brainstorming`):
   - Show 3-5 candidates per sub-aesthetic from vault
   - Note any sub-aesthetics with zero vault candidates — these may need external injection
   - Ask which 2-3 per sub-aesthetic to lock as anchors
   - Ask whether Alex wants external SOTDs injected for any sub-aesthetic; if yes, get URLs

3. **External injection (if requested).** For each external SOTD URL:
   - Run `scout.py --single-url <url>` (verify Scout supports this; if not, document the workaround Alex used and replicate)
   - Confirm ref lands in vault and gets embedded by ingest_daemon

4. **Build `aesthetic_configs.py` entries.** For each of 5 sub-aesthetics (sun-baked already exists in probe-5 V5 OVERRIDE form; port that in; build 4 new), construct a config dict with:
   ```python
   "acid-tech": {
       "palette": {
           "bg": "#0A0A0A",
           "fg": "#F2F2F2",
           "accents": ["#00FFAA", "#FF006E"],
           "supporting": ["#1A1A1A", "#888888"],
       },
       "photography_prefix": "High-key fluorescent register, target mean luminance 180-220, sharp neon highlights, glossy reflections, hard light...",
       "motion_vocabulary": [
           "GSAP scrollTrigger pinning",
           "SplitType character stagger reveal",
           "magnetic CTA on hover",
           "Lenis smooth scroll",
       ],
       "anchor_reference_ids": ["awwwards-sotd-2026-04-22-some-acid-tech-site", "awwwards-sotd-2026-03-15-another"],
       "min_exemplar_count": 2,
       "ref_kit_template_variant": "awwwards",  # Phase 3 creates this
   },
   ```
   Palette values **extracted from exemplar refs**, not invented. Photography prefix **matched to exemplar luminance**, not invented. Motion vocabulary **catalogued from what the exemplar sites actually do**, not from a generic list. This is the core of Mechanism 1.

5. **Run subagent code review** on the new `aesthetic_configs.py` section before commit. Subagent reads the diff against the description doc + this bootstrap, flags any drift (e.g., "this palette doesn't actually match the exemplars listed", "photography prefix is generic, not exemplar-derived").

6. **Commit.** Commit message format:
   ```
   v1.3 Phase 1: awwwards aesthetic family with exemplar anchoring

   Add awwwards-tier section to aesthetic_configs.py with 5 sub-aesthetics
   (sun-baked, acid-tech, cool-jewel, warm-earth, editorial-mid-century).
   Each sub-aesthetic config built from 2-3 exemplar Awwwards SOTDs:
   - sun-baked: Studio Namma, Marvell, Astrodither, Obys (probe-5 anchors)
   - acid-tech: [exemplar list]
   - cool-jewel: [exemplar list]
   - warm-earth: [exemplar list]
   - editorial-mid-century: [exemplar list]

   Mechanism 1 of v1.3: configs are exemplar-anchored, not abstract.
   anchor_reference_ids + min_exemplar_count enable Mechanism 2 (Phase 5).

   Co-Authored-By: Claude <noreply@anthropic.com>
   ```

### Halt criteria

Report to Alex:
- For each sub-aesthetic: list of confirmed anchor IDs and brief palette/photography summary
- Subagent code review verdict (clean / flags raised)
- Commit SHA
- Any sub-aesthetic that's still unanchored (e.g., zero vault candidates AND Alex didn't propose externals) — flag clearly, don't ship the config without anchors

Wait for Alex's go before Phase 2.

### Don't

- Don't invent exemplars — only use ones Alex confirms
- Don't build a config without anchors — that defeats Mechanism 1
- Don't ship a config with anchors that aren't actually in vault — vault-gating (Phase 5) will fail for that sub-aesthetic

---

## Phase 2 — Playbook additions

### Goal

Add `self_audit_awwwards` prompt and hero h1 word-length rules to `workshop-playbook.md`. Existing v1.2 prompts (`brief_synthesis`, `kit_generation`, `self_audit`) stay untouched.

### Superpowers usage

Markdown prompt editing is not a TDD candidate. Skip `/test-driven-development`. Subagent review on the diff is worthwhile — prompts are load-bearing for kit quality.

### Steps

1. **Add `self_audit_awwwards` prompt** to `workshop-playbook.md` between new markers `>>> BEGIN PROMPT self_audit_awwwards` / `<<< END PROMPT self_audit_awwwards`. Prompt structure mirrors `self_audit` but with the new boolean set:
   ```
   You are auditing an awwwards-tier kit. Different rubric from conversion register.

   For each page (index.html, services.html, contacts.html), evaluate these boolean checks:

   - has_one_primary_cta: Is there exactly one primary CTA across the kit? (Multiple
     conflicting CTAs = false.)
   - manifesto_headline_present: Does the hero contain a manifesto headline (statement,
     not a generic tagline)?
   - architectural_type_scale: Is the typography scale dramatic — large h1 contrast
     against body, multi-level hierarchy?
   - motion_libraries_loaded_with_sri: Are motion libraries (GSAP / ScrollTrigger /
     SplitType / Lenis) loaded with SHA-512 SRI integrity attributes?
   - palette_multi_tonal: Does the palette contain ≥4 distinct colors (not just
     bg + 1 accent)?

   For each false: write ≤2 sentence explanation.

   Then list up to 5 soft warnings about anything that reads as "ThemeForest tier"
   rather than "awwwards-tier" (e.g., generic stock photography, default rounded-pill
   CTAs, sub-grid 12-col bootstrap-feel, etc.).

   Output as JSON: { booleans: {...}, warnings: [...] }
   ```
   Adapt verbiage to match existing playbook tone.

2. **Update `kit_generation` prompt** to add hero h1 word-length rules. Add a section near the existing typography/layout rules:
   ```
   ## Hero h1 word-length discipline

   No word in the hero h1 headline may exceed 10 characters. If your natural
   phrasing would include a longer word, substitute. Concrete substitutions
   (apply when appropriate):
   - "Considered" → "Kept"
   - "Treatments" → "Care"
   - "Architectural" → "Built"
   - "Distinguished" → "Set apart"
   - "Restorative" → "Renewed"

   Hero h1 font size is clamp(3.5rem, 16vw, 12rem) — NOT 22vw. Smaller ceiling
   prevents overflow at 390px mobile viewport even with maximum-length permitted
   words.
   ```

3. **Frontmatter version bump:** `workshop-playbook.md` frontmatter version 1.2.1 → 1.3.0. Update `last_modified` if present.

4. **Subagent review:**
   - Read full updated playbook
   - Diff against v1.2.1
   - Verify new prompt markers don't collide with existing ones
   - Verify v1.2 self_audit untouched (sha256 of just that section unchanged)
   - Verify total playbook length still under any hard limits (past chats had a 15K char threshold per prompt — verify each prompt independently under that)

5. **Commit.** Format:
   ```
   v1.3 Phase 2: self_audit_awwwards prompt + hero h1 word-length rules

   Add self_audit_awwwards prompt with awwwards-tier boolean set
   (has_one_primary_cta, manifesto_headline_present, architectural_type_scale,
   motion_libraries_loaded_with_sri, palette_multi_tonal). Existing self_audit
   for conversion register untouched.

   Add hero h1 word-length discipline (≤10 chars per word, clamp 16vw not 22vw)
   to kit_generation prompt with concrete substitution examples.

   workshop-playbook.md version 1.2.1 → 1.3.0.

   Co-Authored-By: Claude <noreply@anthropic.com>
   ```

### Halt criteria

Report:
- Length of new `self_audit_awwwards` prompt (chars)
- Total playbook length
- Subagent review verdict
- Commit SHA

Wait for Alex's go before Phase 3.

### Don't

- Don't modify v1.2 `self_audit` — it serves conversion register, leave it alone
- Don't combine the two audit prompts — they must be distinct, routed by `aesthetic_direction` in Phase 6
- Don't expand the word-length rules with more substitutions than listed — Alex iterates if needed; over-prescribing creates rigidity

---

## Phase 3 — Awwwards kit-template variant

### Goal

Create `workshop/kit-template-awwwards/` with a manifesto-hero base structure that the awwwards register will build from. Five static files like v1.2 kit-template.

### Superpowers usage

Static HTML/CSS scaffold. Not a TDD candidate. Subagent review on structure (does this match probe-5's anatomy without being a 1:1 copy?) is worthwhile.

### Steps

1. **Read probe-5's output** (commit `4ce81c3` on `experimental/awwwards-probe-2026-05-10` branch of camelotflows-kits) as structural reference. Note its anatomy: manifesto hero → portfolio/work grid → services as type-stack → single CTA → oversized footer wordmark.

2. **Create `workshop/kit-template-awwwards/`** with five files:
   - `index.html` — manifesto hero + portfolio-grid placeholder + type-stack services + footer wordmark
   - `services.html` — manifesto headline + alternating image-text rows (NOT card grid) + single CTA
   - `contacts.html` — manifesto headline + ONE contact mechanism (form OR phone link prominent, not both) + footer wordmark
   - `assets/css/style.css` — base structural CSS only (custom properties for palette, layout grid, type scale variables — values are placeholders to be replaced by kit_generation)
   - `assets/js/main.js` — empty scaffold with `<!-- placeholder for motion library wiring -->` comments at injection points
   - `README.md` — describes the awwwards variant, references probe-5 as quality anchor

3. **Token placeholders** preserved in same locations as v1.2 kit-template: `{{BRAND}}`, `{{PHONE_E164}}`, `{{EMAIL}}`, etc. Reuse the existing token list — don't invent new tokens.

4. **NOT a 1:1 copy of probe-5.** This is a base scaffold Workshop generates kits **from**, not a finished kit to be copied. Concrete: probe-5's "& glyph section" or "credit-chip row" are specific moves that distilled from refs — they don't go in the template. The template has placeholders for portfolio cells, type-stack items, etc.; Workshop's kit_generation fills them per brief.

5. **Subagent structural review:**
   - Read the new template
   - Compare to probe-5's HTML
   - Flag if it reads as "probe-5 with placeholders" (= 1:1 copy with variables) instead of "scaffold for the awwwards register" (= structural shape only)
   - If flagged, refactor

6. **Commit.** Format:
   ```
   v1.3 Phase 3: awwwards kit-template variant

   Create workshop/kit-template-awwwards/ with manifesto-hero base structure
   for the awwwards register. Five files matching v1.2 kit-template layout:
   index.html, services.html, contacts.html, assets/css/style.css,
   assets/js/main.js, plus README.md.

   Anatomy from probe-5 reference (commit 4ce81c3): manifesto hero, portfolio
   grid, type-stack services, single CTA discipline, oversized footer wordmark.
   This is a scaffold for generation, not a 1:1 copy of probe-5.

   Co-Authored-By: Claude <noreply@anthropic.com>
   ```

### Halt criteria

Report:
- File sizes for each of the 5 files
- Subagent review verdict
- Side-by-side: token list in v1.2 kit-template vs new awwwards variant (should be identical)
- Commit SHA

Wait for Alex's go before Phase 4.

### Don't

- Don't 1:1 copy probe-5 — it's reference for shape, not content
- Don't add WordPress block patterns, theme.json, or any WP-specific files — Workshop ships static HTML/CSS/JS
- Don't add a Docker config — Workshop uses `python -m http.server`, not DDEV

---

## Phase 4 — Orchestration additions to workshop.py (URL+SRI + palette photography + leak scan)

### Goal

Add three orchestration components to `workshop.py`: URL+SRI pre-flight, palette-aware photography prefix, source-HTML leak scan. These are all in `workshop.py` so they share one phase.

### Superpowers usage

**`/test-driven-development` actively useful here.** Three deterministic-IO functions, each with clear failure modes. RED-GREEN-REFACTOR cycle:
- Write test with known input → known output (RED: function doesn't exist or wrong)
- Implement minimum code to pass
- Refactor for clarity

Tests live in `/opt/scout-workshop/tests/` (create directory if not present, gitignored or git-tracked per project convention — check what's already there).

Subagent code review before commit.

### Steps

#### 4a. URL+SRI pre-flight (Component 4)

1. **Write tests first** (`tests/test_sri_preflight.py`):
   - Mock `httpx.get` to return known file content
   - Compute expected SHA-512 of that content
   - Assert function returns `{lib_name: 'sha512-<expected>'}`
   - Test fail-loud path: mock returns 404 → function raises explicit error
   - Test fail-loud path: mock returns content, expected hash provided as second arg, hashes differ → function raises explicit error

2. **Implement `compute_sri_block(libraries: dict) -> dict`** in `workshop.py`:
   ```python
   def compute_sri_block(libraries: dict[str, str]) -> dict[str, str]:
       """Fetch each CDN library URL, compute SHA-512 SRI hash.
       
       Args:
           libraries: {lib_name: url} dict, e.g.
               {"gsap": "https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js", ...}
       
       Returns:
           {lib_name: integrity_string} dict for direct injection into prompt.
       
       Raises:
           SRIPreflightError if any URL fails or returns non-200.
       """
   ```

3. **Integration:** modify `kit_generation` invocation site to call `compute_sri_block` before prompt construction, pass result as `{{SRI_BLOCK}}` substitution into kit_generation prompt.

4. Update `kit_generation` prompt in `workshop-playbook.md` to reference `{{SRI_BLOCK}}` as the exact strings to use.

#### 4b. Palette-aware photography prefix (Component 5)

1. **Write tests first** (`tests/test_palette_photography.py`):
   - `parse_bg_luminance(html_path)` with mock HTML containing `--color-bg: #FFFFFF` → returns 255.0
   - Same with `#000000` → returns 0.0
   - Same with `#7F7F7F` → returns 127.0 (or accurate luminance approximation)
   - `build_photography_prefix(luminance)`: high luminance → low-key instruction, low luminance → high-key instruction
   - Edge cases: malformed CSS variable → raises explicit error

2. **Implement `parse_bg_luminance`** and `build_photography_prefix` in `workshop.py`. Luminance formula: standard perceptual luminance (0.299*R + 0.587*G + 0.114*B for sRGB without gamma correction is acceptable for this purpose — exemplar is sufficient, not pixel-perfect).

3. **Integration:** between `kit_generation` and `generate_kit_images` invocation, parse the generated `index.html`, compute photography prefix, monkey-patch `generate_kit_images.GENERATION_PROMPT_PREFIX`. After image generation completes, **restore** the original prefix (so subsequent runs aren't contaminated).

#### 4c. Source-HTML leak scan (Component 6)

1. **Write tests first** (`tests/test_leak_scan.py`):
   - HTML with `{{BRAND}}` in source → flag as leak
   - HTML with `{{<!-- -->2026<!-- -->}}` → flag as leak (probe-1 case)
   - HTML with `text-transform: lowercase` on `<span>{{BRAND}}</span>` → do NOT flag (probe-4 false positive case — scan reads source, not rendered)
   - HTML with no tokens → return clean

2. **Implement `scan_source_html_for_leaks(html_paths: list) -> list[str]`**. Regex against file contents directly:
   ```python
   LEAK_PATTERNS = [
       r'\{\{[^}]+\}\}',  # any {{TOKEN}}
       r'\{%[^%]+%\}',    # any {% template %}
       # add others as discovered
   ]
   ```

3. **Integration:** replace the existing Playwright-based leak scan call in `workshop.py` with the new source-HTML scan. Playwright still used for screenshots in Phase 7, but not for leak scanning.

### Phase 4 wrap-up

- Subagent code review on the diff (all three components)
- Run the full test suite — all tests should pass GREEN
- Commit. Format:
  ```
  v1.3 Phase 4: orchestration components (URL+SRI, palette photography, leak scan)

  Add three orchestration components to workshop.py with TDD test coverage:

  - compute_sri_block: orchestration-time URL fetch + SHA-512 SRI computation.
    Fail-loud on 404 or hash mismatch. Eliminates probe-2 fabricated-URL failure
    mode.

  - parse_bg_luminance + build_photography_prefix: palette-aware photography
    prefix for image generation. Monkey-patches generate_kit_images.GENERATION_
    PROMPT_PREFIX per run, restores after. Matches probe-5 V5 mutation.

  - scan_source_html_for_leaks: regex-based source-HTML scan replacing
    Playwright innerText scan. Fixes probe-4 text-transform false-positive.

  Tests in tests/test_sri_preflight.py, test_palette_photography.py,
  test_leak_scan.py — all GREEN.

  Co-Authored-By: Claude <noreply@anthropic.com>
  ```

### Halt criteria

Report:
- Test count and pass/fail per component
- Lines added to workshop.py
- Subagent review verdict
- Commit SHA

Wait for Alex's go before Phase 5.

### Don't

- Don't modify `generate_kit_images.py` directly — runtime monkey-patch + restore only
- Don't merge the leak scan and Playwright into one function — keep them separate, Playwright for screenshots only
- Don't skip the restore step on photography prefix — contamination across runs is a real risk

---

## Phase 5 — Reference handling: diversification + vault-gating (Components 8, 9 / Mechanism 2)

### Goal

Modify `retrieve_inspiration` to apply max-1-per-source-domain filter (Component 8). Add `check_vault_gates` function for Mechanism 2 (Component 9). Both go in `workshop.py`.

### Superpowers usage

**`/test-driven-development` again useful.** Both functions are deterministic against vault state. Tests use mock vault data.

### Steps

#### 5a. Hard reference diversification (Component 8)

1. **Write tests first:**
   - Mock vault returns 5 refs, 3 from same domain → `retrieve_inspiration` returns 3 from different domains
   - Mock vault returns 5 refs, all from same domain → function raises `InsufficientDiversityError`
   - Mock vault returns 5 refs from 5 different domains → function returns 3 (top 3 by score)
   - Override flag `allow_domain_duplicates=True` → function returns 3 ignoring filter

2. **Implement filter** as a post-Qdrant-retrieve step:
   - Pull top-20 from Qdrant (more than 3 to give filter room)
   - Apply Cohere rerank
   - Apply max-1-per-source-domain filter (use `source_domain` field from ref metadata)
   - Return top 3 after filter, or raise `InsufficientDiversityError`

3. **Fail-loud path:** when `InsufficientDiversityError` raised, Workshop's main loop catches it, sends Telegram message naming the brief and current vault diversity state, aborts run.

#### 5b. Vault-gated rotation (Component 9 / Mechanism 2)

1. **Write tests first:**
   - Mock queue: 1 item with sub_aesthetic=sun-baked, vault has sun-baked anchors → gate passes, returns that item
   - Mock queue: 1 item with sub_aesthetic=acid-tech, vault missing acid-tech anchors → gate fails, function returns None for that item
   - Mock queue: 3 items, first 2 have failing gates, 3rd passes → function returns 3rd item
   - Mock queue: 3 items all failing → function returns None and Workshop fails-loud

2. **Implement `check_vault_gates(queue_items, aesthetic_configs, vault_index) -> queue_item | None`:**
   - For each queue item in order:
     - Look up its sub_aesthetic in `aesthetic_configs`
     - Get `anchor_reference_ids` and `min_exemplar_count`
     - Count how many of those anchor IDs are present in current vault index
     - If count ≥ min_exemplar_count, return this item
   - If no item passes, return None

3. **Integration:** modify Workshop's main loop to call `check_vault_gates` BEFORE `pick_next_target`. If None returned, send Telegram with per-sub-aesthetic vault state, abort.

4. **retrieve_inspiration integration with anchors:** when generating an awwwards kit, force-include 1 of the sub-aesthetic's anchor refs in the 3 retrieved refs (to ensure anchored material reaches the model). The other 2 come from rerank + diversification filter.

### Phase 5 wrap-up

- Subagent code review on the diff
- Run test suite, all GREEN
- Commit. Format:
  ```
  v1.3 Phase 5: reference diversification + vault-gated rotation

  Add Component 8 (hard reference diversification) and Component 9 (vault-gated
  rotation) to workshop.py with TDD test coverage.

  - retrieve_inspiration now applies max-1-per-source-domain filter post-Cohere-
    rerank. Raises InsufficientDiversityError if can't satisfy. Override flag
    allow_domain_duplicates for manual escape.

  - check_vault_gates: pre-pick verification that next queue item's sub-aesthetic
    has anchor refs present in vault. Skips items that fail; returns None if
    nothing in queue passes. Workshop main loop fails-loud to Telegram with
    per-sub-aesthetic vault state.

  - retrieve_inspiration force-includes 1 anchor ref per awwwards kit. The other
    2 come from rerank + diversification.

  Mechanism 2 of v1.3: sub-aesthetics enter active rotation only when vault
  contains their anchor exemplars.

  Co-Authored-By: Claude <noreply@anthropic.com>
  ```

### Halt criteria

Report:
- Test count and pass/fail
- Subagent review verdict
- Commit SHA
- Concrete vault-gate evaluation for current vault state: which of the 5 sub-aesthetics currently pass the gate, which don't. (This is the readiness signal for Phase 7.)

Wait for Alex's go before Phase 6.

### Don't

- Don't apply the diversification filter to v1.2 conversion kits unless Alex confirms — they were not built with this filter in mind, may break existing behavior
- Don't have `check_vault_gates` skip queue items silently — every gate failure should be logged with reason
- Don't force-include anchor refs for v1.2 conversion kits — that's awwwards-only logic

---

## Phase 6 — Wiring: aesthetic_direction routing + queue.json schema

### Goal

Wire all the new components together. Workshop reads `aesthetic_direction` and `sub_aesthetic` from queue items, routes to correct pipeline.

### Superpowers usage

Wiring is integration code. Subagent review essential. TDD partial — write tests for the routing function, but the wiring itself is glue code where tests have diminishing returns.

### Steps

1. **Update `queue.json` schema:**
   ```json
   {
     "completed": 7,
     "remaining": [
       {
         "slug": "2026-05-17-acid-tech-saas-tools",
         "aesthetic_direction": "awwwards",   // NEW
         "sub_aesthetic": "acid-tech",         // NEW (only for awwwards)
         "vertical": "saas-tools",             // existing
         "brief_hints": {...}                  // existing
       }
     ]
   }
   ```
   v1.2 queue items missing `aesthetic_direction` default to `conversion` (backward compat).

2. **Add routing in Workshop's main loop:**
   ```python
   if kit["aesthetic_direction"] == "awwwards":
       template_path = "workshop/kit-template-awwwards/"
       audit_prompt = "self_audit_awwwards"
       use_diversification_filter = True
       use_vault_gate = True
   else:  # conversion (default)
       template_path = "workshop/kit-template/"
       audit_prompt = "self_audit"
       use_diversification_filter = False
       use_vault_gate = False
   ```

3. **Update kit_generation prompt invocation** to inject correct template and the SRI block (Phase 4) and word-length rules (Phase 2) at the right substitution points.

4. **Update self_audit invocation** to use the correct prompt name (`self_audit` vs `self_audit_awwwards`) based on direction.

5. **Test routing function** (`tests/test_routing.py`): given a queue item, returns the correct (template_path, audit_prompt, flags) tuple.

6. **Subagent integration review:** read entire `workshop.py`, trace one full awwwards run mentally, verify all new components fire in correct order.

7. **Commit:**
   ```
   v1.3 Phase 6: aesthetic_direction routing + queue schema update

   Wire all v1.3 components together via aesthetic_direction flag on queue
   items. Awwwards items route to kit-template-awwwards/ template,
   self_audit_awwwards prompt, diversification filter, vault gate. Conversion
   items unchanged behavior.

   queue.json schema gains aesthetic_direction (required for new items, defaults
   to "conversion" for backward compat) and sub_aesthetic (required for awwwards
   items, ignored for conversion).

   Co-Authored-By: Claude <noreply@anthropic.com>
   ```

### Halt criteria

Report:
- Routing function test results
- Subagent integration review verdict
- Schema migration note: any v1.2 queue items needed touching? (Probably not — queue currently empty per v1.2 wrap-up.)
- Commit SHA

Wait for Alex's go before Phase 7.

### Don't

- Don't break v1.2 conversion pipeline — existing queue items must still process correctly
- Don't require `sub_aesthetic` on conversion items — it's awwwards-only

---

## Phase 7 — Integration smoke test

### Goal

Manual-trigger Workshop with a sun-baked queue entry (the only validated sub-aesthetic). Verify all v1.3 components fire correctly and produce a real kit. THEN run a v1.2 conversion queue entry to verify nothing's regressed.

### Superpowers usage

If anything fails: `/systematic-debugging`. Don't fix randomly. Phase 4's 4-phase RCA methodology applies.

### Steps

1. **Stage sun-baked test entry** in `workshop/state/queue.json`:
   ```json
   {
     "slug": "2026-05-XX-sun-baked-smoke-test",
     "aesthetic_direction": "awwwards",
     "sub_aesthetic": "sun-baked",
     "vertical": "studio-portfolio",
     "brief_hints": {"register": "european-design-studio"}
   }
   ```

2. **Run `workshop-manual.service`:** `sudo systemctl start workshop-manual.service`. Tail logs: `journalctl -u workshop-manual -f`.

3. **Trace through the run.** Verify each component fires:
   - Vault gate passes for sun-baked? (It should — sun-baked has probe-5 anchors)
   - retrieve_inspiration returns 3 refs including 1 anchor, all different domains?
   - SRI block computed correctly?
   - kit_generation produces 5 static files?
   - Palette parsed from index.html, photography prefix built, generate_kit_images runs with patched prefix?
   - Image luminance differential ≥20 against bg?
   - self_audit_awwwards runs and returns JSON with awwwards boolean set?
   - Source-HTML leak scan runs and returns clean?
   - Hero h1 word-length verification passes?
   - Playwright takes 3 screenshots?
   - Commit lands in camelotflows-kits in a new dated dir?
   - Telegram delivers screenshots + commit URL + audit summary?

4. **Stage conversion test entry** to verify v1.2 still works:
   ```json
   {
     "slug": "2026-05-XX-conversion-smoke-test",
     "aesthetic_direction": "conversion",
     "vertical": "garage-doors",
     "brief_hints": {...}
   }
   ```
   Run workshop-manual.service again. Verify it uses v1.2 path (kit-template/, self_audit, no diversification filter, no vault gate).

5. **If any step fails:**
   - `/systematic-debugging` — Phase 1 root-cause identification before any fix
   - Do NOT modify code blindly
   - Report failure to Alex with RCA before proposing fix

6. **Document smoke test results** in `/opt/scout-workshop/docs/v1.3-smoke-test-report.md`.

### Halt criteria

Report:
- Each pipeline step PASS/FAIL with timing
- Sun-baked kit output: screenshots, commit URL
- Conversion smoke test PASS/FAIL
- Any defects found
- Telegram delivery confirmed

If sun-baked smoke test fails: stop. Don't proceed to Phase 8. Debug first.
If sun-baked passes and conversion regresses: stop. Don't ship.
If both pass: get Alex's eyes on screenshots, wait for go before Phase 8.

### Don't

- Don't proceed if sun-baked fails — that's the only empirically validated sub-aesthetic; failure here means deeper issues
- Don't auto-fix flaky behavior — Alex needs to see what happened
- Don't run all 5 sub-aesthetics in this phase — only sun-baked + 1 conversion. Others get their first runs in production cron after Alex enables.

---

## Phase 8 — Final deploy + version bump

### Goal

Bump version, push, document, declare v1.3.0 shipped.

### Steps

1. **Version bump:** `workshop-playbook.md` frontmatter version → 1.3.0 (if not already set in Phase 2).
2. **Write v1.3 ADR** in `/opt/scout-workshop/docs/architecture-decisions.md` summarizing key decisions: parallel vs supersede (parallel), full rotation choice, vault-gating mechanism, anchor-based config building.
3. **Push to origin:** `git push origin main` on `/opt/scout-workshop/`. Push camelotflows-kits if new commits there from Phase 7 smoke tests.
4. **Restore queue.json** to empty `remaining: []` after smoke tests (or per Alex's instruction — he may want to keep test entries for inspection).
5. **Verify systemd timers** still armed: `systemctl status scout.timer workshop.timer`. v1.3 didn't change timers — they should remain identical to v1.2.
6. **Final Telegram message** to Alex: "v1.3.0 shipped. Sun-baked validated. Awwwards register active. Next cron Sunday."

### Halt criteria

v1.3.0 declared shipped. Final status report includes:
- Git SHAs of all v1.3 commits (Phases 1-6 each had a commit, 8 has the version-bump commit)
- camelotflows-kits status (any new kits from Phase 7 smoke tests, on main or experimental branch per smoke test policy)
- queue state
- Next scheduled cron fire time
- Open items for v1.3.1 (if any surfaced during execution)

### Don't

- Don't push to camelotflows-kits main without Alex's explicit approval — smoke test kits should land on experimental branch or be discarded depending on quality
- Don't enable cron rotation for non-sun-baked sub-aesthetics in this phase — that happens organically as vault accumulates anchor refs

---

## End-of-bootstrap checklist

By the time Phase 8 completes, the following must be true:

- [ ] All 9 protected files from v1.2 baseline still match their original sha256 EXCEPT `workshop-playbook.md` (now v1.3.0 with `self_audit_awwwards` added and `kit_generation` updated) and `aesthetic_configs.py` (now contains awwwards-tier family with 5 sub-aesthetics).
- [ ] `workshop/kit-template/` byte-identical to v1.2 baseline (no changes to conversion template).
- [ ] `workshop/kit-template-awwwards/` exists with 5 static files + README.
- [ ] `workshop.py` has new functions: `compute_sri_block`, `parse_bg_luminance`, `build_photography_prefix`, `scan_source_html_for_leaks`, `check_vault_gates`, and updated `retrieve_inspiration`.
- [ ] `tests/` directory contains test files for all new functions, all GREEN.
- [ ] `workshop-playbook.md` version 1.3.0.
- [ ] At least sun-baked sub-aesthetic produces a valid kit end-to-end (Phase 7 confirmed).
- [ ] v1.2 conversion pipeline still produces valid kits (Phase 7 confirmed).
- [ ] Telegram delivery confirmed for both registers.
- [ ] No modifications to `scout.py`, `ingest_daemon.py`, or `reaction_poller.py`.
- [ ] No new Docker containers, no DDEV install, no WordPress install.
- [ ] hermes-qdrant-vps and other untouchable services unchanged (verify `systemctl status` of each).
- [ ] Documents written: `v1.3-bootstrap-plan.md`, `v1.3-smoke-test-report.md`, ADR entry.

If any item unchecked at end: do not declare v1.3.0 shipped. Report blocker to Alex.

---

## Open issues deferred to v1.3.1+

(Document these as they surface during bootstrap — they go in the deferred queue.)

- Iteration commands ("regenerate cooler" / specific corrections from Telegram replies)
- Skip-and-retry for failing sub-aesthetics in rotation
- Multi-style-bucket diversification (finer than max-1-per-domain)
- Audit determinism (temperature=0 if `claude --print` supports it — needs CLI verification)
- Per-sub-aesthetic kit-template variants (currently all awwwards sub-aesthetics share one template; sun-baked vs acid-tech might want different anatomies eventually)

---

## Communication during execution

- After each phase: halt, report per the phase's halt criteria, wait for Alex's go
- If a sub-task is ambiguous: ask (but don't `/brainstorming` the entire spec — narrow questions only)
- If you find a bug in v1.2 during execution: report it, don't fix it as part of v1.3 — that's scope creep
- If a phase takes longer than expected: report progress checkpoint, don't push through silently
- Russian primary in conversational reports; English for technical proper nouns, file paths, function names

End of bootstrap. Phase 0 begins on Alex's go.
