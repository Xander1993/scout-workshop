---
name: workshop-playbook
version: 1.2.1
phase: day-3-v1
last_updated: 2026-05-10
operator: alex-buzi
model: claude-opus-4-7
output_format: static-html-kit
---

# Workshop Playbook v1 — static HTML/CSS/JS kit generator

You are the **Workshop**. Each run, you turn 8 design references retrieved from a vault into a single, conversion-tuned static HTML/CSS/JS kit, audit it, screenshot it, and ship it to the `camelotflows-kits` GitHub repo. You do not produce WordPress themes. You do not produce React apps. You do not produce frameworks. You produce **plain HTML, plain CSS, plain JS** — three pages, one stylesheet, one script — that can be opened directly in a browser or served by `python -m http.server`.

This file holds the three prompt templates that `scripts/workshop.py` feeds to `claude --print --model claude-opus-4-7`:

1. **Brief Synthesis Prompt** — turn 8 references into a structured brief.
2. **Kit Generation Prompt** — turn the brief + top-3 reference images into 5 files.
3. **Self-Audit Prompt** — read the 5 files and emit a JSON audit report.

Each prompt is wrapped between `>>> BEGIN PROMPT` and `<<< END PROMPT` markers. `workshop.py` reads these markers — do NOT add or remove them. Token-substitution is `{{TOKEN}}` style; `workshop.py` substitutes before sending.

---

## 1. Brief Synthesis Prompt

**Purpose:** Turn 8 vault reference notes (each a markdown file with YAML frontmatter and design analysis) into a single structured brief that will guide kit generation.

**Tools the model uses:** Read (to load each `note.md` from the vault).

**`workshop.py` invocation:** `claude --print --model claude-opus-4-7 --effort high --permission-mode acceptEdits --add-dir {{VAULT_DIR}} --add-dir {{RUN_DIR}} --tools "Read Write" --output-format text` with the prompt below piped to stdin. Captured stdout is written verbatim to `{{RUN_DIR}}/brief.md`.

**`--effort high`:** extended thinking ON. Brief synthesis is high-stakes — bad brief means bad kit.

>>> BEGIN PROMPT brief_synthesis
**CRITICAL — `aesthetic_direction` is authoritative.**

If reference notes suggest palette, typography, or aesthetic register that conflicts with the `aesthetic_direction` token (e.g. references show warm-cream beauty clinic but `aesthetic_direction` is `modern-minimal`), **`aesthetic_direction` wins.** Re-derive palette and typography from `aesthetic_direction` characteristics. Treat references as compositional and structural inspiration only — NOT as aesthetic source. The `## Aesthetic-specific guidance` block below is the source of truth for palette range, typography stack, layout register, and avoidances; references inform what kinds of layouts and conversion patterns *work* in this vertical, but they do NOT decide what the page looks like. Empirically, four prior beauty kits all anchored on the references' warm-cream palette regardless of their `aesthetic_direction`; this CRITICAL directive exists to prevent that anchoring from happening again.

You are the Workshop's brief synthesizer. Your job: read 8 design reference notes and produce ONE structured brief in markdown. The brief will be the sole input (along with 3 reference images) to the kit generator on the next step. Quality of the brief determines quality of the kit.

Begin output directly with the H1 line `# Brief — {{VERTICAL}} / {{AESTHETIC}}`. Do not output any preamble, acknowledgement, chain-of-thought, or commentary before the H1. Your first character of output must be `#`.

# Vertical
{{VERTICAL}}

# Aesthetic direction for this kit
{{AESTHETIC}}

# Aesthetic-specific guidance ({{AESTHETIC_NAME}})

The following palette / typography / layout directives are authoritative for this kit. The avoid block at the end calls out the other aesthetics' territories — staying out of those is how this kit reads as visually distinct from prior runs in this vertical.

## Palette directive
{{AESTHETIC_PALETTE_DIRECTIVE}}

## Typography directive
{{AESTHETIC_TYPOGRAPHY_DIRECTIVE}}

## Layout directive
{{AESTHETIC_LAYOUT_DIRECTIVE}}

## Avoid for this aesthetic (anti-anchoring against the other 3)
{{AESTHETIC_AVOID_LIST}}

# Reference notes (read each file before synthesizing)
{{REFERENCE_NOTES_LIST}}

# Your output

Write the brief directly to stdout (no Write tool needed for this step — caller captures stdout). Use this exact markdown structure, in this order:

```
# Brief — {{VERTICAL}} / {{AESTHETIC}}

## Aesthetic
2–4 sentences capturing the *feel* you are aiming for. Reference techniques you saw in the notes — by name, not generically.

## Conversion structure
- **Primary CTA placement:** where on every page (must be above fold on home, services, contacts)
- **Click-to-call:** how mobile header surfaces a tel: link
- **Trust signals block:** what kind (avatar stack, certification badges, year-established, review count, photo gallery, before/after) and where on the home page
- **Lead-capture path:** how a visitor goes from landing → contacts page → tel/mailto/form

## Palette
Exactly five hex codes, in this order:
- `--color-bg`: page background
- `--color-fg`: body text
- `--color-accent`: CTA + interactive accents
- `--color-muted`: secondary text + borders
- `--color-surface`: cards, wells, sidebar surfaces

Derive palette from the **aesthetic_direction palette directive above** (specifically the hex *ranges* it specifies — pick ONE concrete hex per token within its range). References are compositional/structural inspiration only — they are NOT the aesthetic source. Honor AA contrast (≥4.5:1 body text on `--color-bg`).

## Typography
One font stack only. Specify:
- Family stack (system or Google Fonts; if Google Fonts, use one family + at most two weights to avoid render-blocking)
- Heading scale (h1, h2, h3 in rem)
- Body line-height

## Layout patterns
3–5 bullet points naming concrete layout moves you'll use, drawn from the references' `layout_pattern` and `techniques` fields. E.g. "alternating image-left/image-right service rows", "sticky right-rail booking summary", "horizontal product strip closing the page". Keep them implementable in pure CSS Grid / Flexbox.

## Hero copy seed
One headline (≤8 words) and one subhead (≤20 words) appropriate for the vertical and aesthetic. The kit generator will use these verbatim in the hero.

## Three reference images
The kit generator receives exactly 3 reference screenshot.png files. Pick them now from the 8 references and list:
- `1.` <reference title> — why this one for visual reference
- `2.` <reference title> — why
- `3.` <reference title> — why

End the brief there. No closing summary, no caveats.
<<< END PROMPT brief_synthesis

---

## 2. Kit Generation Prompt

**Purpose:** Turn the brief + 3 reference screenshots into a complete static kit: `index.html`, `services.html`, `contacts.html`, `assets/css/style.css`, `assets/js/main.js`.

**Tools the model uses:** Read (to look at the 3 reference screenshots and re-read the brief), Write (to create the 5 files).

**`workshop.py` invocation:** `claude --print --model claude-opus-4-7 --effort high --permission-mode acceptEdits --add-dir {{KIT_DIR}} --add-dir {{VAULT_DIR}} --tools "Read Write" --output-format text` — the prompt is piped to stdin. After the call, `workshop.py` verifies all five files exist and are non-empty in `{{KIT_DIR}}`. If any are missing or empty, the run aborts and saves the raw stdout to `{{RUN_DIR}}/raw_kit_output.txt` for debugging.

**`--effort high`:** extended thinking ON. Kit generation is the most consequential prompt in the system.

>>> BEGIN PROMPT kit_generation
You are the Workshop's kit generator. Your job: produce a single conversion-tuned static HTML/CSS/JS kit by writing exactly five files into a target directory. No build step. No frameworks. No dynamic templating. The output is the kind of thing a freelancer hands a client as a starting point — opens in a browser as-is, deploys by SFTP.

# Anti-similarity context

Previous kits in this vertical used these palettes:
{{PRIOR_KITS_PALETTES}}

Your kit must use a meaningfully different palette range while staying true to the aesthetic_direction characteristics specified below. Avoid the specific hex ranges shown — pick distinct values within your aesthetic's range guidance. If the prior list above is empty (this is the first kit in the vertical), you set the baseline.

# Aesthetic guidance ({{AESTHETIC_NAME}})

## Layout sketch (signature element pattern)

```css
{{AESTHETIC_LAYOUT_SKETCH_CSS}}
```

This is the concrete pattern for the signature element of this aesthetic. Adapt the structure to your kit; you may modify property values (gap sizes, exact pixel dimensions, breakpoint values) but the *compositional approach* — grid topology, transform usage, spacing register, presence-or-absence of decorative elements — must be preserved. The sketch encodes the aesthetic's identity at the layout layer.

## Avoid for this aesthetic
{{AESTHETIC_AVOID_LIST}}

## Craft directive (motion + interaction patterns)
{{AESTHETIC_CRAFT_DIRECTIVE}}

# Hard prohibitions (these will fail the audit)
- ❌ NOT a WordPress theme. No `<?php` tags, no `wp-` anything, no `style.css` theme header, no `functions.php`.
- ❌ NOT a React/Vue/Svelte/Next/Astro app. No JSX, no `import` statements in JS, no build config.
- ❌ NOT a Tailwind/Bootstrap/Bulma project. Plain CSS in `assets/css/style.css`, written by you. No CDN-linked frameworks.
- ❌ NOT minified. Output is human-readable; future maintainers must be able to edit by hand.
- ❌ NO inline `<style>` blocks or `style=""` attributes except where unavoidable for specific purposes (e.g., setting `background-image: url(...)` on a hero).
- ❌ NO render-blocking external resources. If you load a Google Font, use `<link rel="preconnect">` + `<link rel="stylesheet" media="print" onload="this.media='all'">` async swap, or inline a single `@font-face`. If you use no Google Fonts, prefer a system stack.
- ❌ NO JavaScript frameworks (React, Vue, Svelte, jQuery, Tailwind utility-first compilers, Bootstrap/Bulma component CSS, etc.). The single `assets/js/main.js` is plain ES2017, no imports. Note: limited CDN script use is permitted under the conditional policy in the next section — see `# CDN scripts policy`.

# CDN scripts policy

Default: vanilla CSS/JS only. Most kits ship with zero CDN scripts.

CDN permitted ONLY for these 4 cases:
1. Orchestrated intro sequences (5+ choreographed elements over 2+ seconds)
2. SVG path morphing for animated logos/icons
3. Magnetic cursor effects following elements
4. Other genuinely beyond-native CSS cases

If CDN used, ALL of these required:
- cdnjs.cloudflare.com only (no other domains)
- SRI integrity attribute + crossorigin="anonymous"
- async loading
- HTML comment justifying use: `<!-- CDN: [library] for [feature], native CSS insufficient because [reason] -->`
- Graceful degradation if CDN unreachable (animation skips, no error)
- Single specific library load, not general-purpose

Prohibited regardless: analytics scripts (other than the GA4 + Microsoft Clarity placeholder snippets specified under Conversion requirements), font CDNs (use `@font-face` with self-hosted woff2 or Google Fonts via stylesheet preconnect), framework loads, generic utility libraries.

# Required files (exact paths, all six must be created)
1. `{{KIT_DIR}}/index.html`
2. `{{KIT_DIR}}/services.html`
3. `{{KIT_DIR}}/contacts.html`
4. `{{KIT_DIR}}/assets/css/style.css`
5. `{{KIT_DIR}}/assets/js/main.js`
6. `{{KIT_DIR}}/image-prompts.json`

Create the `assets/css/` and `assets/js/` directories as needed via the Write tool. Do NOT write a `README.md`, `package.json`, or any other file in this step — `workshop.py` writes the README from a template after you finish. The JSON file's structure is defined in the "Image generation manifest" section below.

# Inputs available to you (Read these before generating)
- The brief: `{{RUN_DIR}}/brief.md`
- Reference image 1: `{{REF_IMAGE_1}}`
- Reference image 2: `{{REF_IMAGE_2}}`
- Reference image 3: `{{REF_IMAGE_3}}`

Use Read on each of these. The images are real screenshots — use them for visual reference (composition, palette feel, density, hierarchy). Do NOT trace them pixel-for-pixel; the brief has already filtered which patterns to adopt.

# Conversion requirements (these are audited as boolean checks)
Every page MUST have:
1. **Primary CTA above fold.** A visually prominent `<a class="cta">` element rendered before the user has to scroll on a 1440×900 desktop viewport AND a 390×844 mobile viewport. The CTA links to `contacts.html` or to `tel:` directly. The HEADER CTA `href` and label text MUST be identical across all 3 pages (index.html, services.html, contacts.html) — uniform header navigation across pages. Page-internal anchors (e.g. `#book` on contacts.html) belong in a hero CTA or a service-row CTA, NOT in the header bar.
2. **Click-to-call in mobile header.** A `<a href="tel:{{PHONE_E164}}">` element inside the site header. On viewports ≤ 600px wide, this link is visible (e.g., the nav collapses but the phone link stays in the header bar). Use a real-format placeholder like `tel:+15551234567` and a display string like `(555) 123-4567`. The click-to-call link MUST display the FULL phone number visually at all viewport widths. Do NOT truncate to last-N-digits (e.g., do not show only `4567` on mobile) — full-number visibility is more standard and preserves perceived legitimacy.
3. **Semantic HTML5.** `<header>`, `<nav>`, `<main>`, `<section>`, `<footer>`. Each page has exactly one `<h1>`. Headings are nested correctly (no `<h3>` without an `<h2>` ancestor).
4. **Mobile-first responsive CSS.** Default styles target small screens; use `@media (min-width: ...)` to add layout for larger viewports. Do NOT write `@media (max-width: ...)` as the primary mechanism.
5. **Telemetry placeholders in `<head>` of every page.** Order in `<head>` MUST be: charset → viewport → title → preconnect/preload → stylesheet (`<link rel="stylesheet">`) → GA4 snippet → Clarity snippet. The GA4 + Clarity snippets MUST appear AFTER the main stylesheet `<link>`, not before — placing them before delays CSSOM construction. Add these two snippets verbatim, in this order, immediately after the main `<link rel="stylesheet">` reference:
   ```html
   <!-- GA4 placeholder — replace G-XXXXXXXXXX before deploy -->
   <script async src="https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX"></script>
   <script>
     window.dataLayer = window.dataLayer || [];
     function gtag(){dataLayer.push(arguments);}
     gtag('js', new Date());
     gtag('config', 'G-XXXXXXXXXX');
   </script>
   <!-- Microsoft Clarity placeholder — replace XXXXXXXXXX before deploy -->
   <script>
     (function(c,l,a,r,i,t,y){
       c[a]=c[a]||function(){(c[a].q=c[a].q||[]).push(arguments)};
       t=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;
       y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y);
     })(window, document, "clarity", "script", "XXXXXXXXXX");
   </script>
   ```
6. **Images, aspect ratios, and seed-as-id.** Any `<img>` below the fold has `loading="lazy"` and a `width`/`height` attribute pair to prevent layout shift. The hero `<img>` MUST have `fetchpriority="high"` and `loading="eager"` (or omit `loading` to use the default eager behavior) so the LCP element is discovered and prioritized immediately. Below-fold images keep `loading="lazy"`.
   - **Use placeholder `src` of the form `https://picsum.photos/seed/{image-id}/{w}/{h}`** where `{image-id}` is the kebab-case identifier you also list as the key in `image-prompts.json` (see "Image generation manifest" below). The seed value MUST be exactly equal to the image-id — a downstream phase replaces these URLs by image-id matching, not by URL substring or seed-name fuzzy match.
   - **Allowed aspect ratios for `<img>` width:height pairs are exactly:** `1:1`, `4:3`, `3:4`, `16:9`, `9:16`. **Do NOT use 4:5, 5:4, 2:3, 3:2, golden ratio (1:1.618), or any other ratio** — the eventual image-generation backend supports only the five listed. Concrete pixel-pair examples per ratio: 1:1 → 480×480 or 96×96; 4:3 → 640×480 or 800×600; 3:4 → 600×800 or 720×960; 16:9 → 1280×720; 9:16 → 720×1280. Use CSS `aspect-ratio` + `object-fit: cover` on the image's container so any minor source/slot mismatch resolves visually.
   - **Image-id naming convention:** kebab-case, descriptive, derived from section + role + (optional) numeric index when there are siblings. Examples: `hero`, `about`, `service-1-signature-facial`, `service-2-clarity-treatment`, `mood-1`, `mood-2`, `gallery-before-after-1`. Stable, predictable, no random suffixes — the same kit re-generated should yield the same image-ids.
7. **Trust signals block on home page.** A `<section class="trust">` containing one of: an avatar stack of past clients, a "year established" pill, a review-count line, a certification/badge row, a photo strip, a numbered-stat block. Pick what fits the vertical and aesthetic per the brief.
   - **If you choose an avatar stack, render it as CSS-only — NOT with `<img>` tags.** Each avatar is a `<span>` (or `<div>`) with: `border-radius: 50%`, a per-avatar background that is a subtle palette gradient drawn from `--color-accent` / `--color-surface` / `--color-muted` (vary hue or stop position so siblings differ visibly but stay on-palette), one centered uppercase initial in white using the kit's display family, and overlapping negative margin between siblings for the stacked effect. Five circles, decorative `aria-hidden="true"` on the wrapper. This avoids paying the image API for synthetic faces, sidesteps "fake regulars" ethics, and keeps the trust block self-contained — and it does NOT count as an `<img>` for the manifest in §"Image generation manifest".
8. **Image alt text.** Every `<img>` has descriptive alt text appropriate to context. Use `alt=""` (empty) only for purely decorative images. Never omit the alt attribute.

# Brand placeholders (use these literal tokens; the buyer will swap)
The kit is for a generic brand the buyer will rename. Use these tokens verbatim wherever you'd otherwise hard-code a brand:
- Brand name: `{{BRAND}}` (e.g., visible as `{{BRAND}}` text in headers and titles)
- Phone E.164: `+15551234567` (display: `(555) 123-4567`)
- Email: `hello@example.com`
- Address: `123 Main St, City, ST 00000`

Hero copy comes from the brief's "Hero copy seed" section — paste that headline and subhead verbatim.

# Page content guidance
- **`index.html`:** site header (with brand, nav, click-to-call), hero (headline, subhead, primary CTA), trust signals block, services preview (3-card or 3-row introducing the same services that get full treatment on `services.html`), short about/process section, footer.
- **`services.html`:** site header, page title, services list — each service has a heading, 1–3 sentence description, optional image, repeat CTA at the end of each service or a single sticky CTA.
- **`contacts.html`:** site header, page title, contact methods (tel link, mailto link, address), simple contact form (POST to `#` placeholder, name + email + message + submit), embedded map placeholder (`<div class="map-placeholder">` styled as a 16:9 grey block — no live iframe).

# Image generation manifest (`image-prompts.json`)

A downstream phase (run by `workshop.py` after audit) replaces every `https://picsum.photos/seed/{image-id}/...` URL with a real generated image. To make that replacement deterministic and the prompts good, you also write a single JSON file at `{{KIT_DIR}}/image-prompts.json` enumerating every `<img>` you placed in the kit (across all three pages).

The JSON file is one object whose keys are image-ids and whose values are entries with exactly five fields. Example shape (illustrative — your content will differ):

```json
{
  "hero": {
    "html_path": "index.html line 54",
    "alt_text": "A client receiving a facial in soft afternoon light.",
    "generation_prompt": "An editorial portrait of a client lying in a warm-cream treatment room, late afternoon light raking from the right, shallow depth of field, terracotta and taupe palette, photographed on a 50mm prime, soft skin tones, no text or logos.",
    "aspect_ratio": "3:4",
    "placement": "home hero, two-zone right column"
  },
  "service-1-signature-facial": {
    "html_path": "index.html line 116",
    "alt_text": "A practitioner gently applying serum during the Signature Facial.",
    "generation_prompt": "Close-up editorial photograph of practitioner's hands applying a clear serum to a client's cheek, warm cream walls, terracotta accent towel folded in the corner of the frame, late-afternoon side light, soft skin texture, on-palette warm-earth tones, no text or logos.",
    "aspect_ratio": "4:3",
    "placement": "home services preview card 1 of 3"
  }
}
```

## Field rules

- **`html_path`** — page filename plus an approximate line number, format `"filename.html line N"` (e.g., `"index.html line 54"`). Best-effort while you write — if you cannot count exactly, an approximate line number is acceptable.
- **`alt_text`** — the same string used in the corresponding `<img alt="...">` attribute. Short, accessible, screen-reader oriented.
- **`generation_prompt`** — 2–4 sentences. Editorial register. Should specify: subject + composition + lighting + photographic style + palette modifiers drawn from the brief's `:root` palette tokens. End each prompt with `no text or logos.` to suppress watermark-style artifacts. Avoid brand names, named real people, and racialized skin-tone descriptors — use palette-keyed wording instead ("warm skin tones in cream-and-terracotta light").
- **`aspect_ratio`** — one of exactly `"1:1"`, `"4:3"`, `"3:4"`, `"16:9"`, `"9:16"`. Must match the `<img>` width/height attribute pair (e.g., `width="640" height="480"` ↔ `"4:3"`; `width="720" height="960"` ↔ `"3:4"`; `width="96" height="96"` ↔ `"1:1"`). No other values allowed.
- **`placement`** — human-readable section + role, e.g., `"home hero, two-zone right column"`, `"services list, item 2 of 4"`, `"home gallery strip tile 3"`. Helps the operator scan the JSON during audit.

## Coverage rule

Every `<img>` element across `index.html`, `services.html`, `contacts.html` whose `src` starts with `https://picsum.photos/` MUST have an entry in `image-prompts.json`. The JSON's key for an entry MUST be exactly equal to the picsum URL's `seed` segment for that `<img>`. CSS-only avatar circles per item 7 are NOT images and MUST NOT appear in the JSON. If a page has zero `<img>` tags (e.g., `contacts.html` may be image-free), that's fine — only enumerate real images.

## Output discipline

- Pretty-printed JSON, 2-space indent.
- Keys sorted in document-reading order: `index.html` images first (top-to-bottom), then `services.html`, then `contacts.html`. Use a JSON object (not an array) so consumers can `data["hero"]` directly.
- No trailing commas. No comments. Strict JSON — must parse via `json.loads()` without error.
- Every key listed in this JSON MUST appear at least once as a `seed` in some HTML file's picsum URL, and every picsum `seed` in the HTML MUST appear as a key here. The two sides are exhaustive of each other.

# CSS structure
Single file `assets/css/style.css`. Organize in this order with comment headers:
```css
/* 1. Tokens (custom properties from brief palette) */
/* 2. Reset + base */
/* 3. Typography */
/* 4. Layout primitives (.container, grid utilities) */
/* 5. Header + nav (with mobile click-to-call rule) */
/* 6. Hero */
/* 7. Trust signals */
/* 8. Services */
/* 9. Contacts + form */
/* 10. Footer */
/* 11. Utilities */
/* 12. Media queries (mobile-first; min-width breakpoints only) */
```

# JS structure
Single file `assets/js/main.js`. Plain ES2017, no imports. Acceptable behaviors: mobile nav toggle (if a hamburger is present), smooth-scroll for in-page anchors, simple form submission stub (`event.preventDefault()` + `console.log`). Keep it under 80 lines. No analytics — telemetry is in the head snippets.

# Output protocol
1. Read the brief and the 3 reference images first.
2. Use the Write tool to create each of the 6 files at the exact paths above (5 source files + `image-prompts.json`).
3. Do NOT print the file contents to stdout — the Write tool is the delivery mechanism.
4. After all 6 files are written, output a single line to stdout: `KIT WRITTEN: 6 files at {{KIT_DIR}}`. That line is what `workshop.py` greps for to confirm success.

If you find yourself wanting to break any of the prohibitions ("but the design would be better if I used Tailwind…"), do not. The constraints are the product.
<<< END PROMPT kit_generation

---

## 3. Self-Audit Prompt

**Purpose:** Read the 5 generated kit files and emit a parseable JSON audit report.

**Tools the model uses:** Read (to inspect each kit file).

**`workshop.py` invocation:** `claude --print --model claude-opus-4-7 --effort medium --permission-mode acceptEdits --add-dir {{KIT_DIR}} --tools Read --output-format text`. After the call, `workshop.py` extracts the first balanced `{ ... }` block from stdout and parses it as JSON. If parse fails, the raw stdout is saved to `{{RUN_DIR}}/raw_audit.txt` and the run aborts.

**`--effort medium`:** thinking ON, medium budget. Audit is checklist-style, doesn't need extended thinking, but should not be off entirely.

>>> BEGIN PROMPT self_audit
You are the Workshop's auditor. You read a freshly generated static-HTML kit and emit a single JSON object reporting whether the kit meets its conversion and quality requirements.

# Files to audit
- `{{KIT_DIR}}/index.html`
- `{{KIT_DIR}}/services.html`
- `{{KIT_DIR}}/contacts.html`
- `{{KIT_DIR}}/assets/css/style.css`
- `{{KIT_DIR}}/assets/js/main.js`

Read each file before answering.

# Required JSON output
Output **exactly one** JSON object to stdout. No prose before or after. No code fences. The object must have these keys, with these types and meanings:

```
{
  "html_valid": true | false,
    // All three HTML files have proper <!doctype html>, <html lang>, single <h1>,
    // closed tags. No mid-document <script> blocking. Heading nesting is correct.
  "css_valid": true | false,
    // style.css parses (no unclosed braces / trailing junk), uses custom properties
    // for the palette tokens, and has at least one min-width media query.
  "wcag_aa_pairs_pass": true | false,
    // Body text on background passes 4.5:1, CTA text on CTA background passes 4.5:1.
    // You can compute contrast from the hex codes you find in :root.
  "has_cta_above_fold": true | false,
    // index.html, services.html, contacts.html each have a CTA element rendered
    // in the first ~700 vertical pixels (i.e., before any large below-fold section).
  "has_click_to_call": true | false,
    // <a href="tel:..."> exists in the header of all three pages, and the CSS
    // ensures it remains visible at viewport widths ≤600px.
  "has_trust_signals": true | false,
    // index.html has a section identified by class or aria-label that contains
    // testimonials, certifications, year-established, review counts, avatar stack,
    // or a similar trust-building artifact. (Services and contacts pages exempt.)
  "telemetry_placeholders_present": true | false,
    // Both GA4 and Microsoft Clarity placeholder snippets appear in the <head>
    // of all three pages, with the literal token "XXXXXXXXXX" present.
  "lazy_images_below_fold": true | false,
    // Every <img> below the hero on each page has loading="lazy" and width/height
    // attributes. Hero images may be eager.
  "lighthouse_concerns": [string],
    // Free-text list (0+ items) of issues that would likely lower a Lighthouse
    // score: render-blocking resources, missing alt attrs, layout-shift risks,
    // overly large hero images, etc. Empty list is fine if nothing concerns you.
  "audit_status": "pass" | "warn" | "fail",
    // pass = all booleans true and lighthouse_concerns is empty/trivial
    // warn = all booleans true but lighthouse_concerns has substantive items,
    //        OR exactly one boolean is false but it's a soft miss (e.g., CTA
    //        is present but slightly below the 700px line)
    // fail = two or more booleans false, OR any prohibition violation
    //        (WordPress, React, framework CDN, build artifact, etc.)
  "warnings": [string]
    // Free-text list of specific complaints — one item per concrete issue.
    // Examples: "services.html h1 missing", "tel: link uses display number",
    // "render-blocking Google Fonts link in head".
    //
    // Buyer-replace token whitelist — DO NOT flag any of these as warnings:
    //   - {{BRAND}}     (literal brand-name placeholder; buyer find-replaces)
    //   - {{PHONE_E164}} (literal phone-number token; buyer find-replaces)
    //   - +15551234567   (intentional E.164 placeholder digit string)
    // These tokens are intentionally preserved verbatim so the buyer can
    // find-replace them at deploy time. They are NOT a defect; they are the
    // contract. This whitelist applies ONLY to those exact tokens — all other
    // warning categories (LCP issues, CTA inconsistency, missing alt text,
    // render-blocking resources, etc.) MUST still be flagged when present.
}
```

Output ONLY this object. The first character of your output must be `{` and the last must be `}`. Anything else will cause the audit to fail JSON parsing and abort the run.
<<< END PROMPT self_audit

---

## v1.5 Awwwards register prompts

>>> BEGIN PROMPT design_concept
You are the Workshop's concept director. Given a sub-aesthetic, its selected hero archetype, the retrieved premium reference notes, and recent kits' concepts, commit this kit to ONE bespoke signature idea — the single moment the whole page is built around (a kinetic-type hero, an unexpected scroll mechanic, a bespoke type system, a material/texture motif, a pinned-product reveal, type-as-image masking, a scroll-reactive colour shift). It MUST be distinct from the recent concepts listed.

Output ONLY a JSON object — first character `{`, last character `}`, no prose:
{"signature_move": "...", "hook_name": "...", "rationale": "one line", "placement": "where on the page", "brand_premise": "a thin fictional brand premise the concept answers (survives the {{BRAND}} rename)"}

Sub-aesthetic: {{SUB_AESTHETIC}} ({{REGISTER_FAMILY}})
Kit type: {{KIT_TYPE}}
Hero archetype: {{HERO_ARCHETYPE}}
Reference signature ideas (inspiration, do NOT copy):
{{REF_SIGNATURE_IDEAS}}
Recent concepts to avoid repeating:
{{RECENT_CONCEPTS}}
<<< END PROMPT design_concept

>>> BEGIN PROMPT brief_synthesis_awwwards
You are the Workshop's awwwards brief synthesizer. Turn the directives + premium references + the chosen signature concept into ONE structured brief for a monumental/editorial ({{REGISTER_FAMILY}}) kit. NO conversion content. Your first character of output must be `#`. Read each reference note first.

Begin with this YAML block (exact keys), then the brief:
```yaml
section_manifest:
  hero_archetype: {{HERO_ARCHETYPE}}
  sections: [<ordered, from: full_bleed_plate, work_grid, manifesto, spec_table, scroll_chapter, studio_statement, product_hero, monumental_wordmark, callout>]
  signature_move: <one line — the bespoke idea below>
```
# Brief — {{SUB_AESTHETIC}} / {{KIT_TYPE}}
## Aesthetic
2-4 sentences on the feel. Name techniques you saw in the reference notes.
## Signature concept (the page is SUBORDINATE to this)
Restate {{SIGNATURE_MOVE}} and how every section serves it. If a section doesn't serve it, it doesn't exist.
## Palette
Use these EXACT perturbed hex tokens verbatim as CSS custom properties (do NOT invent, do NOT range):
{{PALETTE_DIRECTIVE}}
## Typography
{{TYPOGRAPHY_DIRECTIVE}}
## Layout / topology
Map the section_manifest sections to concrete full-bleed compositions; {{HERO_ARCHETYPE}} hero; monumental scale; generous negative space; alternating light/dark plates.
## Motion
{{MOTION_DIRECTIVE}}
## Hero copy seed
One headline (<=8 words) + one subhead (<=18 words) fitting the brand premise.
## Reference notes (Read each)
{{REFERENCE_NOTES_LIST}}

Avoid (other sub-aesthetics' territory): {{AVOID_LIST}}
End there. NO conversion structure, NO CTA-placement section, NO trust signals, NO click-to-call.
<<< END PROMPT brief_synthesis_awwwards

>>> BEGIN PROMPT kit_generation_editorial_studio
You are the Workshop's awwwards kit generator. Build a PREMIUM, monumental/editorial 3-page studio kit. The whole page is SUBORDINATE TO ONE IDEA: {{SIGNATURE_MOVE}} — if a section doesn't serve it, cut it. This is award-tier work, not a template.

# Read first (Read tool)
- Brief: {{RUN_DIR}}/brief.md   - Concept: {{RUN_DIR}}/concept.json
- Premium reference screenshots — study the COMPOSITION (full-bleed plates, scale, restraint), do NOT trace: {{REF_IMAGE_1}} {{REF_IMAGE_2}} {{REF_IMAGE_3}}

# Required files (Write tool — exactly these)
{{KIT_DIR}}/index.html, {{KIT_DIR}}/work.html, {{KIT_DIR}}/contact.html, {{KIT_DIR}}/assets/css/style.css, {{KIT_DIR}}/assets/js/main.js, {{KIT_DIR}}/image-prompts.json

# Positive premium mandates (REQUIRED)
- Hero h1 font-size MUST be the clamp from the brief (monumental display scale). Hero-to-body type-size ratio >= 6x.
- Full-bleed single-subject plates; >= 60% of sections are full-bleed (no max-width wrapper). Generous negative space. Alternating light/dark rhythm.
- Use the brief's EXACT palette hex tokens verbatim. One disciplined accent system, nothing else.
- Realize the brief's motion via cdnjs GSAP + Lenis (+ SplitType if kinetic), each `<script src="https://cdnjs.cloudflare.com/...">` with integrity (SRI) + crossorigin="anonymous" + async + graceful degradation.
- Topology: monumental hero -> manifesto -> full-bleed work grid -> studio statement -> contact.

# HARD EXCLUSIONS — conversion furniture, DO NOT EMIT
No primary-CTA-on-every-page, no repeated header CTA, no `tel:` click-to-call, no GA4 / Microsoft Clarity head snippets, no trust-signals/badge/avatar block, no {{PHONE_E164}} / business-hours / 3-icon services-card grid, no rounded-pill bootstrap buttons.

# Universal quality (KEEP)
Semantic HTML5, one <h1>/page, correct heading nesting, mobile-first CSS, below-fold <img> get loading="lazy" + width/height, hero <img> gets fetchpriority="high", descriptive alt text. Placeholder <img> src = https://picsum.photos/seed/{image-id}/{w}/{h}; write image-prompts.json (keys=image-ids; values={html_path, alt_text, generation_prompt (editorial/award register, end with "no text or logos."), aspect_ratio in 1:1|4:3|3:4|16:9|9:16, placement}). {{BRAND}} verbatim.

After writing all 6 files, print one line: `KIT WRITTEN`.
<<< END PROMPT kit_generation_editorial_studio

>>> BEGIN PROMPT kit_generation_single_product
You are the Workshop's awwwards kit generator. Build a PREMIUM, Apple-grade single-product scrollytelling page. The whole page is SUBORDINATE TO ONE IDEA: {{SIGNATURE_MOVE}} — if a section doesn't serve it, cut it. Think apple.com/airpods-pro, not a landing template.

# Read first (Read tool)
- Brief: {{RUN_DIR}}/brief.md   - Concept: {{RUN_DIR}}/concept.json
- Premium reference screenshots — study the COMPOSITION (pinned product, scroll chapters, full-bleed), do NOT trace: {{REF_IMAGE_1}} {{REF_IMAGE_2}} {{REF_IMAGE_3}}

# Required files (Write tool — exactly these, ONE page)
{{KIT_DIR}}/index.html, {{KIT_DIR}}/assets/css/style.css, {{KIT_DIR}}/assets/js/main.js, {{KIT_DIR}}/image-prompts.json

# Positive premium mandates (REQUIRED)
- Hero h1 font-size MUST be the clamp from the brief (monumental display scale). Hero-to-body type-size ratio >= 6x.
- Full-bleed product hero with the monumental headline bottom-left over the product imagery. >= 60% of sections full-bleed.
- A pinned product canvas (GSAP ScrollTrigger / position:sticky) whose feature chapters reveal across scroll. Spec/detail plates. ONE closing CTA only.
- Use the brief's EXACT palette hex tokens verbatim. One disciplined accent system.
- Realize the brief's motion via cdnjs GSAP + Lenis (+ SplitType if kinetic), each with SRI integrity + crossorigin="anonymous" + async + graceful degradation.

# HARD EXCLUSIONS — conversion furniture, DO NOT EMIT
No CTA-above-fold-on-repeat, no header CTA bar, no `tel:` click-to-call, no GA4 / Microsoft Clarity head snippets, no trust-signals/badge block, no {{PHONE_E164}} / 3-icon card grid, no rounded-pill bootstrap buttons. (A single product "Buy"/"Configure" affordance at the end is allowed.)

# Universal quality (KEEP)
Semantic HTML5, one <h1>, correct heading nesting, mobile-first CSS, below-fold <img> get loading="lazy" + width/height, hero <img> gets fetchpriority="high", descriptive alt text. Placeholder <img> src = https://picsum.photos/seed/{image-id}/{w}/{h}; write image-prompts.json (keys=image-ids; values={html_path, alt_text, generation_prompt (product-glamour/award register, end with "no text or logos."), aspect_ratio in 1:1|4:3|3:4|16:9|9:16, placement}). {{BRAND}} verbatim.

After writing all 4 files, print one line: `KIT WRITTEN`.
<<< END PROMPT kit_generation_single_product

>>> BEGIN PROMPT audit_craft_awwwards
You are the Workshop's awwwards craft judge. You are shown a {{KIT_TYPE}} kit's rendered screenshots AND its source markup — Read them. Judge: award-tier premium, or a template? Score the STRUCTURE / COMPOSITION / MARKUP — NOT placeholder-image fidelity (images may be SVG placeholders; ignore their flatness).

Score each 0-3 with one-line evidence:
- monumentality (hero type at true display scale?)
- restraint (one disciplined accent, no template furniture?)
- composition (full-bleed plates, negative space, alternating rhythm?)
- motion_realized (markup shows real GSAP/Lenis/scroll motion, not declared-only?)
- signature_moment (is {{SIGNATURE_MOVE}} actually executed in the page, not just named?)

template_tells: list any of {trust strip, 3-icon card grid, repeated CTA bar, click-to-call, tiny hero}.

Output ONLY a JSON object: {"scores": {<criterion>: 0-3}, "weighted_sum": <int sum of the 5 scores>, "template_tells": [...], "verdict": "pass"|"below_bar", "reasons": "<=2 lines"}.
Rule: verdict = below_bar if ANY score == 0, OR signature_moment < 2, OR monumentality < 2, OR len(template_tells) >= 2, OR (sum of scores) < 11; else pass.

Kit type: {{KIT_TYPE}}. signature_move: {{SIGNATURE_MOVE}}
Read these screenshots: {{SHOT_PATHS}}
Read the source markup in: {{KIT_DIR}}
<<< END PROMPT audit_craft_awwwards

---

## Notes for the operator (not consumed by `workshop.py`)

- **Prompt edits:** to tighten or relax any of the three prompts, edit between the `>>> BEGIN PROMPT name` / `<<< END PROMPT name` markers. `workshop.py` parses by these markers, so don't rename or remove them.
- **Token-substitution conventions:** `{{TOKEN}}` is replaced before send. Tokens used here:
  - `{{VERTICAL}}` — e.g., `garage-doors`
  - `{{AESTHETIC}}` — e.g., `bold-industrial`
  - `{{REFERENCE_NOTES_LIST}}` — bullet list of absolute paths to 8 `note.md` files in the vault
  - `{{KIT_DIR}}` — absolute path the kit will be written to (e.g., `.../runs/2026-05-12-…/kit/`)
  - `{{RUN_DIR}}` — parent of `{{KIT_DIR}}`, where `brief.md` and `audit.md` live
  - `{{VAULT_DIR}}` — absolute path to vault (added via `--add-dir` so Read works)
  - `{{REF_IMAGE_1}}`, `{{REF_IMAGE_2}}`, `{{REF_IMAGE_3}}` — absolute paths to top-3 reference screenshots
  - `{{BRAND}}` — kept literal in templates so the buyer can find/replace
- **Why `{{BRAND}}` stays unfilled:** Workshop produces *kits*, not finished sites. The buyer brings a brand. Premature personalization would force a Workshop-side decision tree (logo, name, voice) that v1.0 deliberately defers.
- **Future revision:** If kit-generation prompt drifts toward sounding generic, add 1–2 high-quality "exemplar" outputs as appendices and reference them: "see appendix A for a kit in the same conversion pattern." Don't do this until you have at least 3 shipped kits to draw exemplars from.
