# Brief — agency / restrained-luxury-warm

## Aesthetic
A quiet, editorially-confident agency portfolio that reads as warm-paper restraint, not spa cliché. We lift the discipline of Obys (centered wordmark + founder-chip row + the registered-trademark micro-detail for editorial gravitas) and the paper-tone-bg / colossal-wordmark / tiny-credit-chip skeleton documented across Where Worlds Take Shape and T11 — but render it in warm cream and terracotta rather than monochrome or forest-green. Typography does almost all the work: a single variable serif (Fraunces) with the italic axis exploited for one word of emphasis per headline, the way the references use single-accent discipline. The terracotta seal-badge bridging the hero is our one chromatic note, occupying the same role yellow-pill or red-cord plays in the dark-mode references.

## Conversion structure
- **Primary CTA placement:** Top-right of header (terracotta pill, "Start a project") AND in the left zone of the two-zone hero, above the fold on home, services, and contacts. Persistent on scroll via a slim warm-cream sticky bar that surfaces the same pill after 600px of scroll.
- **Click-to-call:** Mobile header collapses nav into a hamburger but exposes a discrete terracotta phone-icon pill to the immediate left of the hamburger; the pill is a `tel:` link, not behind a menu. On desktop the phone number sits in the top-right as a small-caps inline link beside the CTA pill.
- **Trust signals block:** One section below the hero, before services. Composition: small-caps centered eyebrow ("Trusted since 2014"), an avatar stack of 5 client/founder portraits (terracotta ring borders), an inline year-established figure ("Est. 2014 · 60+ engagements · 4.9 ★ across 38 reviews"), and a single-line client logo wall in warm-taupe at low opacity beneath.
- **Lead-capture path:** Hero CTA → /contacts page → three side-by-side surfaces (tel: card, mailto: card, brief-form card) on the right-rail sticky pattern; the form has 4 fields max (name, company, budget select, project description) and posts to mailto: as a no-JS fallback.

## Palette
- `--color-bg`: `#F5EBD8`
- `--color-fg`: `#2F2218`
- `--color-accent`: `#C26A40`
- `--color-muted`: `#BFB1A0`
- `--color-surface`: `#ECDFC8`

Contrast: `#2F2218` on `#F5EBD8` ≈ 12.4:1 (well above AA 4.5:1).

## Typography
- **Family stack:** `'Fraunces', 'Cormorant Garamond', Georgia, serif` — single Google Fonts family, variable axes (opsz, wght, ital, SOFT). Two weights loaded: 400 + 600. Italic cut used for the single emphasis word per h1.
- **Heading scale:** h1 `4.5rem` (clamp 3rem → 4.5rem on mobile→desktop), h2 `2.75rem`, h3 `1.5rem`.
- **Body:** `1.0625rem / 1.65` line-height, weight 400, optical-size axis set via `font-variation-settings: "opsz" 14`.

## Layout patterns
- **Two-zone hero 50/50 desktop**: left column carries h1 + subhead + terracotta CTA pill + small-caps "Est. 2014" supertext; right column carries a warm-graded portrait crop (`filter: sepia(0.15) saturate(0.85)`). Stacks single-column on mobile, image above copy.
- **Circular terracotta seal-badge** (~110px, `border-radius: 50%`, `background: var(--color-accent)`) positioned at the visual midpoint of the hero via absolute placement on a relative hero container — it bridges the two zones as the page's single chromatic anchor, like the yellow Visit-Site pellet does for the awwwards references but warm and integrated, not overlaid.
- **Centered small-caps section titles** introducing each block (`text-transform: uppercase; letter-spacing: 0.18em; font-size: 0.8125rem;` in warm taupe) — the quiet inverse of loud eyebrows, signalling editorial register.
- **Alternating image-left/image-right service rows** below the trust block — three rows, each `display: grid; grid-template-columns: 1fr 1fr; gap: 4rem;` with vertical rhythm of ≥6rem between rows on desktop.
- **Sticky right-rail booking summary on /services desktop**: `grid-template-columns: minmax(0, 1fr) 320px;` with the rail using `position: sticky; top: 6rem;` inside its own column. The rail contains the brief estimate + CTA. Collapses below the main column on mobile.
- **Founder credit chip row** beneath the trust block (lifted from Obys / Studio375 dual-chip pattern but recoloured): warm-taupe rounded chips with a small avatar circle inside each, sitting on a single horizontal line on desktop.

## Hero copy seed
**Headline:** Brands that carry *weight*.
**Subhead:** An independent studio crafting identity systems, editorial sites, and considered digital work for companies that take the long view.

## Three reference images
- `1.` Where Worlds Take Shape — warm-earth palette validation (forest + sand from awwwards) plus the paper-tone-bg + colossal wordmark + tiny avatar-chip composition we are transposing to cream + terracotta.
- `2.` Obys — purest expression of editorial restraint (centered wordmark, founder-chip row, registered-trademark micro-detail); structural template for our hero header zone and credit-chip placement.
- `3.` T11 — Creative Entertainment Partner — quiet-whitespace-then-media reveal pattern below the fold, plus the single-credit-chip discipline that informs our trust signals row.

Note: I read 8 design reference markdown notes. None contain code or executable content — they are descriptive design notes (Awwwards / WordPress showcase write-ups). No malware analysis applicable.
