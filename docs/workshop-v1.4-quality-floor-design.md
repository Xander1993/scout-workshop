# Workshop v1.4 — Quality Floor + Tailnet Dashboard

Design spec. Authored 2026-05-20.

Status: drafted from brainstorming session, pending Alex approval before implementation plan.

## Problem this solves

Recent workshop runs are inconsistent in quality. The May 10 probe-5 run (sun-baked, Studio Namma anchor) and the May 15 agency-modern-minimal run produced awwwards-adjacent kits — dramatic display type, real photographic depth, showpiece wordmarks, multiple substantial content groups per page. The May 17 agency-restrained-luxury-warm run regressed: hero is polished but the homepage collapses into a ~700px vertical void between "Three practices, one register." and "Patient, on the record.", because the three service rows specified in the brief render with only 155 characters of text each and minimal styling, leaving the alternating image-left/image-right layout visually empty.

Investigation findings:

- The May 17 brief itself specified fewer substantial content sections than May 15 (1 services grid vs May 15's 2 grids — disciplines + catalogue).
- The model honored the brief; the brief was thin.
- The existing audit (`self_audit`) caught WCAG contrast issues but not structural sparseness: zero warnings about section density, vertical voids, brief-coverage, or wordmark treatment.
- `{{BRAND}}` tokens in HTML are intentional template placeholders for buyer substitution; what changed between probe-5 and May 17 is the *visual treatment* (showpiece huge wordmark vs small utility text in footer), not the presence of the token.

The current system has three independent gaps:

| Gap | What it lets through | Where it lives |
|---|---|---|
| **A. Brief-density gap** | Brief specifies one substantial content section + decoration. Renders sparse. | Brief-generation prompt |
| **B. Coverage-audit gap** | No check that each specced section renders at substantial density. | Audit prompt |
| **C. Retry-on-warn gap** | Audit warnings ship the kit unchanged. | `workshop.py` orchestration |

v1.4 closes all three with a composed gate pipeline + a tailnet dashboard for observability.

## Architecture

```
queue → vault-gate (v1.3) → brief-gen
                                ↓
                       [NEW Gate A] brief manifest validation (deterministic)
                                ↓ pass / retry-once / halt
                          pre-flight SRI → kit-gen → images → existing audit
                                ↓
                       [NEW Gate B] deterministic density + Claude brief-coverage
                                ↓ pass / [NEW Gate C] retry-kit-gen-once / halt
                          screenshots → commit → Telegram (extended)

                          [PARALLEL] tailnet dashboard reads telemetry JSONL
                                     + per-run state files
                                     → http://100.110.49.44:8211
```

Three gates compose into one pipeline. v1.3 features (vault-gate, SRI pre-flight, palette-aware photography, leak-scan, existing audits) all stay intact. v1.4 wraps them with two new gates + a retry mechanism + a dashboard.

## Components

### 1. Gate A — Brief Manifest validation (deterministic, fast)

Modifies `skills/workshop-playbook.md` so the brief-generation prompt MUST emit a structured `section_manifest` YAML block at the top of `brief.md`:

```yaml
---
section_manifest:
  index:
    - {id: hero, type: hero, required_elements: [h1, subhead, primary_cta, image]}
    - {id: trust, type: stats_row, required_elements: [eyebrow, stat_count_min_3]}
    - {id: services, type: case_grid, min_items: 3, item_requires: [image, h3, body_min_80c]}
    - {id: portfolio, type: case_grid, min_items: 3, item_requires: [image, h3, year]}
    - {id: footer_callout, type: callout, required_elements: [h2, body, secondary_cta]}
    - {id: wordmark, type: showpiece_wordmark, required_elements: [brand_token]}
  services:
    - ...
  contacts:
    - ...
---
```

A new orchestration step `validate_brief_manifest()` in `workshop.py` parses the YAML and enforces:

- Homepage manifest declares **≥2 `case_grid`-or-equivalent sections** OR **≥1 case_grid + ≥1 manifesto block + ≥1 stats_row**.
- All declared sections have schema-valid `type` from a fixed enum (hero, stats_row, case_grid, manifesto, callout, showpiece_wordmark, founder_chip_row, trust_signals, sticky_rail).
- Each `case_grid` declares `min_items` and `item_requires`.

If validation fails → ONE retry of brief generation with the failure recap injected as a system prompt prefix. If retry also fails → halt with Telegram diagnostic. The run does not proceed to kit generation.

### 2. Gate B.1 — Density audit (deterministic, post-generation)

New module `scripts/density_audit.py`. Five checks, each emits `{check_id, status, evidence, brief_section_ref}`:

| Check ID | Measures | Implementation |
|---|---|---|
| `substantial_sections` | Per-page count of `<section>`/`<article>` with ≥80c text + 1 image, OR marked `class="manifesto"` with computed `font-size ≥ 6rem` | Regex on source HTML + Playwright computed-style for manifesto exception. Threshold: index ≥3, services ≥3, contacts ≥2. |
| `vertical_void` | Max consecutive vertical pixels with no rendered visible text or image | Playwright at 1440×900 viewport. Walks DOM, collects bounding boxes of visible `<p>`, `<h*>`, `<img>`, `<video>`. Sorts by y. Returns max gap. **FAIL if max gap > 500px AND total page height < 4000px.** |
| `article_density` | Each non-utility `<article>` has ≥80c text AND (≥1 image OR ≥1 manifesto element) | Regex on source HTML |
| `hero_h1_word_cap` | No word in hero h1 exceeds 10 characters (v1.3 spec, ported here) | Regex on rendered text |
| `wordmark_treatment` | If brief manifest declares `showpiece_wordmark`, footer element containing `{{BRAND}}` has computed `font-size ≥ 6rem` OR `width ≥ 60vw` | Playwright computed style |

Output: `density_audit.json` in run dir. Passed to the orchestrator.

### 3. Gate B.2 — Brief-coverage audit (Claude-as-auditor, semantic)

New prompt template `skills/audit_brief_coverage.md`. Single Claude call per kit:

- Inputs: `brief.md` (with manifest YAML) + `index.html`, `services.html`, `contacts.html` (source HTML)
- Prompt: "For each item in the `section_manifest` YAML, find the rendered equivalent in the HTML files. Grade each as `present` (renders substantially), `sparse` (renders but minimally), or `absent` (no matching element). Return JSON: `[{section_id, status, evidence_selector, notes}]`."
- Run at `effort=medium` (consistent with existing audit's resource profile)
- Tolerance: **≥80% of brief sections must be `present`.** Less than that = Gate B.2 FAIL.

This is the only Claude call in the new pipeline. Audit-variance is contained to this single check; the rest of Gate B is deterministic and reproducible across runs.

### 4. Gate C — Retry orchestration (workshop.py)

Replaces the existing "ship on audit warn" behavior:

```python
def run_quality_gate(run_dir, brief, manifest):
    det = density_audit.run(run_dir, manifest)         # Gate B.1
    cov = brief_coverage.run(run_dir, brief)           # Gate B.2
    return GateResult(det, cov)

# After kit_generation + image_gen + existing audit:
result = run_quality_gate(run_dir, brief, manifest)
if not result.passed:
    log_gate_failure(result)
    telegram_interim("Density failed, retrying with diagnostic recap")
    rerun_kit_generation(strict_recap=result.failure_recap())  # ONE retry
    result = run_quality_gate(run_dir, brief, manifest)
    if not result.passed:
        halt_with_telegram(result, screenshots=existing_screenshots)
        return EXIT_QUALITY_HALT
```

Retry policy:

- Maximum **one** retry. If second attempt also fails → halt; do not commit or push.
- On retry, image generation is reused (no fresh images) — saves tokens, since image-bg-luminance contract has already been validated in attempt 1.
- If second attempt's HTML is byte-identical to first, treat as `model_stuck` → halt with note (avoids infinite-loop edge case where stricter prompts don't change output).
- Halted runs move from `workshop/runs/<slug>/` to `workshop/runs-halted/<timestamp>-<slug>/` so the main runs directory stays clean for tooling that iterates it.

Telegram halt message includes: screenshots from both attempts, brief, HTML diff, audit reports, and commands: `/workshop ship-anyway <halted-slug>`, `/workshop skip <slug>`, `/workshop manual-trigger <slug> with-flag`.

### 5. Tailnet dashboard (`scout-workshop-dashboard` service)

A FastAPI service reading telemetry + per-run state files, served on the Tailscale interface only.

**Tech stack:**
- FastAPI (Python 3.12, reuses existing venv at `/opt/scout-workshop/venv/`)
- Binds to `100.110.49.44:8211` + `127.0.0.1:8211` (loopback for local debug; never public)
- Frontend: single static HTML page with embedded GSAP 3.x + Lenis 1.x for motion, served from FastAPI's `StaticFiles`
- Server-Sent Events endpoint `/events` for live updates when telemetry JSONL grows
- Systemd unit `scout-workshop-dashboard.service` for auto-start, depends on the workshop's venv being intact

**Endpoints:**

| Path | Returns | Notes |
|---|---|---|
| `GET /` | The HTML dashboard | Single self-contained page |
| `GET /api/runs?register=&sub_aesthetic=&status=&since=` | List of run summaries from JSONL | Filterable |
| `GET /api/runs/<slug>` | Full run detail: brief, manifest, density_audit, coverage_audit, retry diff if present | Reads per-run state files |
| `GET /api/screenshot/<slug>/<file>` | Streams the PNG from `workshop/runs/<slug>/kit/screenshots/<file>` | Read-only, sanitized path |
| `GET /api/stats` | Aggregated stats: total runs, ship rate, retry pass rate, avg coverage %, per-sub-aesthetic breakdown | Computed on each call (cheap, JSONL is small) |
| `GET /events` | SSE stream pushing new run summaries when JSONL grows | Watches file with inotify or polling |

**Visual design (eat-our-own-dog-food):**

The dashboard uses the same awwwards-tier vocabulary the workshop should produce:

- Typography: Fraunces variable serif (display + body, two weights, italic axis exploited for stat emphasis), JetBrains Mono for tabular data and HTML diffs
- Palette: dark warm-paper inverse — bg `#1A1612`, fg `#F0E8D8`, accent `#C26A40` (terracotta from May 17 brief), muted `#8A7E70`
- Layout: editorial — generous whitespace, oversized stats, asymmetric grid for run list, sticky filter rail on the right
- Motion: scroll-driven section reveal (GSAP ScrollTrigger), magnetic cursor on filter chips and expandable run cards, marquee ticker for the stats row with hover-pause, real-time pulse animation (border + brief screenshot fade-in) when SSE delivers a new run
- Showpiece footer: oversized `WORKSHOP // FLOOR` wordmark, lifted from the probe-5 Astrodither-style brand treatment

**Information architecture:**

1. **Top**: Sticky header with logo wordmark + nav (Runs · Stats · Halted · Config). Status indicator pulses if a run is in progress.
2. **Hero**: Latest run, full-bleed hero with screenshot blend-mode overlay on the page background. Editorial caption: brief title, register chip, status verdict, gate timings. If the latest run was a halt, the verdict chip is red and clickable to expand the diagnostic.
3. **Stats marquee**: Oversized counters scrolling horizontally — `TOTAL RUNS · 247 · SHIP RATE · 89% · RETRY RECOVERY · 67% · AVG COVERAGE · 94%`. Hover pauses.
4. **Recent runs**: Vertical timeline, last 20 runs as small case-study cards (slug, register chip, screenshot thumbnail, verdict chip, retry indicator). Click expands inline.
5. **Drill-down (expanded run)**: Side-by-side first vs second attempt if a retry happened. HTML diff between attempts (rendered with monospace + line numbers). Full density audit table + coverage audit table. All 6 screenshots in a tappable grid.
6. **Sticky filter rail (right)**: Animated chips for register · sub-aesthetic · status · date range. Changes filter the timeline in-place.

**Live updates:**

The dashboard subscribes to `/events` via EventSource. When a new line lands in the telemetry JSONL, a card slides into the top of the runs timeline with a single-pulse animation. If a halt happens, a banner appears at the top with the halted slug + actions.

**Halt-resolution actions:**

The dashboard does NOT have buttons to ship-anyway or skip — those are explicit user decisions and should remain in the Telegram flow where Alex's authentication is implicit. The dashboard surfaces the halt and links to the Telegram message thread.

## State files written per run

| File | Purpose | When written |
|---|---|---|
| `brief.md` | (existing) brief + new YAML manifest at top | after brief-gen |
| `manifest.json` | Parsed YAML manifest, validated, schema-checked | after Gate A pass |
| `density_audit.json` | Output of Gate B.1 — 5 checks × {status, evidence} | after kit-gen |
| `coverage_audit.json` | Output of Gate B.2 — per-section grade + evidence selectors | after kit-gen |
| `gate_b_verdict.json` | Combined verdict, retry counter, recap text used | after Gate B finishes |
| `attempt-1/` & `attempt-2/` | (only on retry path) snapshots of kit folder before each retry | before second kit-gen |
| `run.log` | (existing) extended with gate timings + verdicts | throughout |

Telemetry aggregation: `/opt/scout-workshop/state/quality_floor_telemetry.jsonl`. One JSON line per kit run, appended atomically:

```json
{
  "ts": "2026-05-24T01:14:35Z",
  "run_slug": "agency-cool-jewel",
  "register": "awwwards",
  "sub_aesthetic": "cool-jewel",
  "gate_a": "pass",
  "gate_b1": {"substantial_sections": "pass", "vertical_void": "fail-720px", "article_density": "pass", "hero_h1_word_cap": "pass", "wordmark_treatment": "pass"},
  "gate_b2": {"sections_present": 4, "sections_sparse": 2, "sections_absent": 0, "coverage_pct": 67},
  "retried": true,
  "retry_outcome": "pass",
  "final_status": "shipped",
  "tokens_used": 84321,
  "duration_seconds": 905
}
```

## Tuning knobs

New file `quality_floor_config.py`:

```python
QUALITY_FLOOR = {
    "thresholds": {
        "vertical_void_max_px": 500,
        "vertical_void_min_page_height": 4000,
        "substantial_section_min_text_chars": 80,
        "coverage_pct_min": 80,
        "hero_h1_max_word_chars": 10,
        "showpiece_wordmark_min_font_rem": 6,
    },
    "retry_policy": {
        "retry_on_gate_b_fail": True,
        "max_retries": 1,
        "reuse_images_on_retry": True,
        "halt_on_identical_retry_output": True,
    },
    "register_overrides": {
        "awwwards": {"vertical_void_max_px": 700},
        "conversion": {"vertical_void_max_px": 400},
    },
    "dashboard": {
        "bind_address": "100.110.49.44",
        "bind_port": 8211,
        "loopback_also": True,
        "sse_poll_seconds": 5,
        "stats_cache_seconds": 30,
    },
}
```

Live-edit config; no code change required to tune thresholds.

## Failure modes handled explicitly

| Case | Behavior |
|---|---|
| Gate A fails (brief lacks manifest) | Retry brief gen once with failure recap; halt if still missing |
| Brief manifest present but malformed YAML | Treat as Gate A fail (strict format) |
| Existing audit returns FAIL (not warn) | Skip Gate B entirely; halt immediately |
| Gate B.2 (Claude) returns malformed JSON | Log warning, treat Gate B.2 as inconclusive, ship if Gate B.1 alone passes |
| Playwright fails to launch for void detection | Skip void check only, run others, ship with warning |
| Retry kit-gen would exceed `budget_tokens_per_run` | Halt without retry; Telegram notes budget exhaustion |
| Brief manifest declares `showpiece_wordmark` but rendered too small | Soft warning in Telegram, doesn't FAIL the gate |
| Run is from `/workshop ship-anyway` override | Skip both Gate B sub-gates entirely |
| Second-attempt HTML byte-identical to first | Halt with `model_stuck` note |
| Dashboard service dies | Workshop runs unaffected; systemd restarts dashboard on next tick |
| Dashboard tries to read screenshot outside `workshop/runs/` | 403 — path traversal blocked |

## Backward compatibility

Zero breaking changes. v1.3 features (vault-gate, SRI pre-flight, palette-aware photography, leak-scan, existing audits, queue.json, Telegram messaging) all stay intact. Setting `QUALITY_FLOOR["retry_policy"]["retry_on_gate_b_fail"] = False` fully disables v1.4 enforcement and runs as v1.3.

The dashboard is purely read-only — it cannot trigger kit generation, modify state, or affect the cron flow. Disabling the dashboard service has no effect on the workshop pipeline.

## Deliverables

5 modules + dashboard:

1. `skills/workshop-playbook.md` — add Section Manifest YAML requirement to brief generation prompt
2. `workshop.py` — Gate A validation + Gate C retry orchestration + halt path
3. `scripts/density_audit.py` — new module, 5 deterministic checks
4. `skills/audit_brief_coverage.md` — new Claude prompt template for semantic coverage
5. `quality_floor_config.py` — tuning knobs, telemetry append, register overrides
6. `dashboard/` — FastAPI service + single-page HTML + systemd unit
   - `dashboard/app.py` — FastAPI app, endpoints, SSE
   - `dashboard/static/index.html` — single-page UI
   - `dashboard/static/style.css` — Fraunces + restrained dark palette
   - `dashboard/static/main.js` — GSAP + Lenis + EventSource + filter logic
   - `systemd/scout-workshop-dashboard.service` — auto-start unit

## Out of scope (deferred)

| Item | Why deferred | Likely version |
|---|---|---|
| New section types (broken grid, asymmetric, sticky horizontal) | Sub-project 3 — structural layout change | v1.6 |
| Technique vocabulary (kinetic type, GLSL, magnetic cursor on kits) | Sub-project 2 — adds capability, not enforcement | v1.5 |
| "Regenerate cooler" iteration commands | Already deferred in v1.3.1+ docs | After v1.4 |
| Audit temperature pinning | Doesn't solve structural gap; band-aid | If telemetry shows variance is the real issue |
| Dashboard ship-anyway / skip buttons | Authentication is implicit in Telegram, not in tailnet | If multiple operators ever access dashboard |
| Multi-region/lang manifest | WPML scope creep | Separate effort |
| Auto-regenerating broken refs in vault | Scout's job, not Workshop's | n/a |

## Estimated effort

~2-3 days of focused implementation by someone with full codebase context. Breakdown:

- Day 1: Gate A + Gate B.1 + tests against May 17 / May 15 / probe-5 historical runs as fixtures
- Day 2: Gate B.2 + Gate C orchestration + Telegram extension + telemetry JSONL
- Day 3: Dashboard FastAPI + static frontend + systemd unit + tailnet smoke test

First production cron run after merge should be observable in the dashboard within minutes.

---

End of design draft. Standing by for "годится" or revision requests. Once approved, the implementation plan is drafted via the writing-plans skill.
