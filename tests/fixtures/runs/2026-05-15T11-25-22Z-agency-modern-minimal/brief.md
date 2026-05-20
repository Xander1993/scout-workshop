# Brief — agency / modern-minimal

## Aesthetic
A disciplined poster-fold studio site in the lineage of Obys and Studio Namma — restraint reads as luxury, type does the work. The fold is a tightly-set wordmark over generous cool-white space, then a single high-contrast canvas below — the "wordmark fold + dramatic hero" pattern documented across the SOTD batch. Single saturated accent (Simonholm's red discipline applied to a cool-white ground rather than near-black), bottom-anchored sub-nav stripe, registered-mark micro-detail next to the brand. Greyscale dominance, zero ornamentation, hairline dividers — the value is in what is removed.

## Conversion structure
- **Primary CTA placement:** Floating dark CTA pill anchored bottom-right of the hero canvas (Studio Namma move), repeated as a sticky in-view CTA in the bottom toolbar on services + contacts. Above the fold on home, services, contacts.
- **Click-to-call:** Mobile header collapses to wordmark-left + tel: link as a small accent-coloured chip top-right; tappable 44px target. Same number repeats in the bottom-anchored sub-nav strip.
- **Trust signals block:** Numeric stats only — single horizontal row directly under hero (e.g. "120 PROJECTS · 14 AWARDS · EST. 2018"), set in display weight on a 1px hairline-bordered row. No avatars, no logos, no testimonials in the hero. A second row of award/year chips appears mid-page.
- **Lead-capture path:** Hero CTA pill → contacts page → mailto + tel + minimal 3-field form (name, email, project type). Services page repeats the dark-pill CTA at the end of each service row pointing to contacts.

## Palette
- `--color-bg`: `#FAFAFB`
- `--color-fg`: `#0F0F10`
- `--color-accent`: `#DC2626`
- `--color-muted`: `#D4D4D8`
- `--color-surface`: `#FFFFFF`

## Typography
- Family stack: `'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif` — Google Fonts, single family, two weights only (400 + 800) to avoid render-blocking. Variable `wght` axis available where supported via `font-variation-settings`.
- h1: `5.5rem` (clamp 3rem → 5.5rem), weight 800, `letter-spacing: -0.02em`
- h2: `2.25rem`, weight 700, optional ALL CAPS variant with `letter-spacing: 0.2em`
- h3: `1.25rem`, weight 700
- Body: `1rem`, weight 400, `line-height: 1.5`

## Layout patterns
- **Centered wordmark fold over cool-white** with registered-mark superscript glyph (Obys move) — agency name occupies the entire upper viewport, founder credit chips inline beneath in a horizontal row.
- **Below-fold high-contrast canvas slab** — full-bleed surface (#0F0F10) directly under the wordmark fold, holding either a CSS-clip-path geometric mark, a video reel, or a single editorial visual. The "quiet whitespace crashes into dramatic canvas" tension borrowed from T11 and Studio Namma.
- **Bottom-anchored horizontal sub-nav strip** inside the hero canvas (Simonholm pattern) — section labels (Work / Studio / Process / Contact) along the bottom edge as the contextual index, replacing a dropdown.
- **Alternating 12-column case-study rows** — title + meta in cols 1–4, full-bleed visual in cols 5–12, mirrored next row. 1px hairline divider between rows, ≥6rem section gap.
- **Numeric stats row + persistent overlay UI bar** holding the dark CTA pill (Studio375 / Silent House overlay vocabulary) — sits sticky at viewport bottom on desktop scroll past the fold.

## Hero copy seed
- Headline: **A studio for considered work.**
- Subhead: Brand systems, sites, and identities for founders who want restraint to do the heavy lifting.

## Three reference images
- `1.` Obys — cleanest expression of the centered-wordmark fold + registered-mark micro-detail + editorial restraint we are anchoring on.
- `2.` Studio Namma — wordmark-as-hero discipline plus the floating dark CTA pill anchored to a single canvas; visual reference for the bottom-right CTA placement.
- `3.` Simonholm.studio — bottom-anchored horizontal sub-nav strip and single-saturated-accent discipline (red against an otherwise greyscale ground) — exactly the accent role we want, inverted from dark to cool-white ground.
