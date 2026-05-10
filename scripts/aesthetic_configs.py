"""Workshop v1.2 — per-aesthetic configuration for differentiated kit generation.

Resolves the differentiation flatness identified in Phase 0 investigation
(four shipped beauty kits had palette tokens <5% divergent across briefs)
by providing aesthetic-direction-specific palette ranges, typography stacks,
layout sketches, image-gen prompt prefixes, and explicit "avoid" lists that
prevent each aesthetic from drifting into the others' territory.

Each config is consumed in three places:
  1. brief_synthesis prompt (workshop.py:synthesize_brief) — palette_directive,
     typography_directive, layout_directive, avoid become the brief synthesizer's
     authoritative input. References become compositional inspiration only.
  2. kit_generation prompt (workshop.py:generate_kit) — layout_sketch_css and
     craft_directive land in the prompt as concrete patterns the model can
     adapt. avoid is repeated for safety; prior_kits_palettes is appended at
     call time as anti-similarity context.
  3. generate_kit_images.py — image_prefix replaces the v1.1 hardcoded
     GENERATION_PROMPT_PREFIX so generated images visually match the aesthetic.

Lookup normalizes "-vN" suffixes used for regeneration runs ("modern-minimal-v2"
resolves to "modern-minimal") so the queue can carry distinct run identifiers
(driving directory naming + git tags) without duplicating configs.

Palette ranges deliberately avoid pinned hexes — the model picks within the
range, which (a) preserves diversity across multiple runs of the same aesthetic
in v1.3 exploration mode, and (b) makes aesthetic_direction a constraint rather
than a recipe. The 4-aesthetic seed below is the v1.2 anchor set; new aesthetics
are added by appending to CONFIGS, no other code change required.
"""
from __future__ import annotations

import logging
import re
from textwrap import dedent
from typing import Any

log = logging.getLogger("workshop.aesthetic_configs")


def _d(s: str) -> str:
    """dedent + strip — keeps source-file indentation readable while emitting
    flush-left text for embedding in prompts."""
    return dedent(s).strip()


# ─────────────────────────────────────────────────────────────────────
# 1. restrained-luxury-warm
# ─────────────────────────────────────────────────────────────────────

_RESTRAINED_LUXURY_WARM = {
    "name": "Restrained Luxury Warm",

    "palette_directive": _d("""
        Warm earth palette only. The terracotta/clay accent does ALL of the
        chromatic work; everything else is cream-on-cream.

        - --color-bg: low-contrast warm cream or stone, range #F0E5D0 — #FAF2E5.
          Pick ONE specific hex. Must NOT be pure white (#FFFFFF) or near-white.
        - --color-fg: deep umber / warm charcoal, range #2A1F18 — #3F2D20.
          Must contrast ≥4.5:1 against --color-bg.
        - --color-accent: a single terracotta / warm-clay tone, range
          #B25C3C — #D08854. Pick ONE specific hex. This is the only saturated
          color on the page.
        - --color-muted: a warm taupe at low saturation, range #B5A99A — #C9BBAB.
          Used for borders and secondary text only.
        - --color-surface: a slightly cooler or warmer cream than --color-bg,
          range #E8D9C3 — #F2EAE0. Cards and wells. Never #FFFFFF.

        No second accent color. No blue, no green, no rose. The page must read
        as a single warm-temperature palette.
    """),

    "typography_directive": _d("""
        Variable serif primary. Strongly recommended: Fraunces (variable axes
        for opsz, wght, SOFT, ital — exploit them). Acceptable alternative:
        Cormorant Garamond.

        - Headings: serif at weight 400 with the italic axis available for
          one-word emphasis inside h1 (the "Miso pattern" — italicize exactly
          ONE word per headline, never the whole headline).
        - Body: same family at 300–500 if it has both roman and italic cuts;
          otherwise pair with a humanist sans body (Inter Tight, IBM Plex Sans).
        - At most TWO weights loaded (e.g. 400 + 600). Variable axis covers
          intermediate weights without extra files.
        - Use font-variation-settings to interpolate weight on hover for the
          italic emphasis word — restrained, single-element transition only.

        No display sans-serif headlines. No grotesque headlines. No mixed-case
        playfulness — letterforms remain elegant and traditional.
    """),

    "layout_directive": _d("""
        Classical editorial hierarchy. Composition is balanced and deliberate
        — no asymmetry, no overlapping cards, no broken grids.

        - Two-zone hero (50/50 desktop): headline + subhead + CTA on left,
          colour-graded portrait on right.
        - A circular seal-badge element bridges the two zones — terracotta
          accent, ~110px, sitting at the visual midpoint as the chromatic anchor.
        - Generous vertical rhythm: ≥4rem between sections on desktop, ≥3rem
          on mobile. White space is a design element here.
        - Centered small-caps section titles introducing each block (the
          inverse of the loud-eyebrow pattern — quiet centered titles signal
          editorial register).
        - Right-rail sticky booking summary on /services desktop
          (grid-template-columns: minmax(0, 1fr) 320px; sticky inside the
          rail). Collapses below the main column on mobile.
        - Trust signals block (avatar stack + year-established + review count)
          one section below the hero, before services.
    """),

    "layout_sketch_css": _d("""
        /* Signature hero — two-zone with seal-badge bridge */
        .hero {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 3rem;
          align-items: center;
          position: relative;
          min-height: 70vh;
          padding: 5rem 2rem;
        }
        .hero__text { padding-right: 1rem; }
        .hero__portrait {
          width: 100%;
          aspect-ratio: 3 / 4;
          object-fit: cover;
          border-radius: 4px;
        }
        .hero__seal {
          position: absolute;
          left: 50%; top: 50%;
          transform: translate(-50%, -50%);
          width: 112px; height: 112px;
          border-radius: 50%;
          background: var(--color-accent);
          color: var(--color-bg);
          display: grid; place-items: center;
          font-size: 0.7rem;
          letter-spacing: 0.18em;
          text-transform: uppercase;
          z-index: 2;
          box-shadow: 0 8px 24px rgba(58, 42, 31, 0.12);
        }
        @media (max-width: 760px) {
          .hero { grid-template-columns: 1fr; }
          .hero__seal { display: none; }
        }
    """),

    "image_prefix": _d("""
        Editorial wellness photography, warm cream and terracotta palette,
        soft natural side-lighting, considered self-care aesthetic, no clinical
        signaling, no medical apparel, matte film finish, subtle organic grain.
        No text, no logos, no watermarks.
    """).replace("\n", " "),

    "avoid": [
        "cool blues, greys, or icy whites (that is modern-minimal's territory)",
        "pink, rose, or blush palette (that is editorial-feminine's territory)",
        "sage green or stone palette (that is natural-organic's territory)",
        "sans-serif as primary headline typography",
        "sharp geometric edges, hard clip-path shapes, or geometric grids",
        "asymmetric, overlapping, or broken-grid composition",
        "glassmorphism (does not match restrained register)",
        "uppercase headlines with extreme letter-spacing",
    ],

    "craft_directive": _d("""
        Restraint is the luxury signal. Use motion sparingly and only where it
        reinforces the editorial register.

        Acceptable craft moves:
        - Gentle hero-portrait parallax via animation-timeline: scroll() —
          ≤30px translateY range, no rotation.
        - font-variation-settings interpolation on the italic emphasis word
          on hover (e.g. "wght" 400 → 500 over 0.4s ease).
        - Soft fade-in on services cards via animation-timeline: view() with
          opacity transition only (no transform — no fade-up-from-below).
        - A single barely-perceptible drop-shadow softening on cards on hover.

        Avoid:
        - Rotation, scale, or clip-path reveals (too theatrical).
        - Glassmorphism / backdrop-filter (wrong register).
        - Multi-element choreographed sequences.
        - Stagger effects.
    """),
}


# ─────────────────────────────────────────────────────────────────────
# 2. editorial-feminine
# ─────────────────────────────────────────────────────────────────────

_EDITORIAL_FEMININE = {
    "name": "Editorial Feminine",

    "palette_directive": _d("""
        Soft pink / rose / blush palette as the dominant warmth, with cream
        and one strong dark contrast.

        - --color-bg: cream-blush, range #FDF6F4 — #F8E6E1. Pick ONE hex.
          Must read as warm-cool (cream tinted toward pink), NOT warm-cream.
        - --color-fg: deep aubergine / wine, range #2A1A24 — #3F2A30.
          Provides the "strong dark contrast" against soft bg.
        - --color-accent: dusty rose / muted blush at moderate saturation,
          range #C77A8A — #A85A6A. Pick ONE hex.
        - --color-muted: soft mauve at low saturation, range #C5B0B5 — #D6C2C7.
        - --color-surface: a paler version of bg or near-white, range
          #FFFFFF — #FCF1ED. Cards lift off the blush with subtle elevation.
        - Optional --color-ink: nearly black with a violet undertone for
          high-contrast headline accent (#1A1218 — #221820).

        The page must read as feminine warmth without going pastel-childish —
        the deep aubergine fg + dusty rose accent provides editorial weight.
    """),

    "typography_directive": _d("""
        High-contrast serif/sans pairing for magazine register.

        - Display headings: dramatic serif with strong italic personality.
          Recommended: Playfair Display (variable, opsz axis), Cormorant
          Garamond (italic styles), or Canela if available. Use 500–700 weight
          range; italic cuts for hero headlines.
        - Body: clean grotesque sans at 400/500. Recommended: Inter, IBM Plex
          Sans, or system sans. Body must NOT be the same family as headings —
          the contrast between dramatic-serif and grotesque-sans is the
          typographic identity.
        - Headlines may be very large (h1 4–5rem desktop) — magazine register
          forgives bold display type.
        - Use font-variation-settings on h1 italic for scroll-driven weight
          shifts (300 → 700 across the first viewport).
    """),

    "layout_directive": _d("""
        Asymmetric magazine layout. At least ONE major section MUST use an
        overlapping, broken-grid, or rotated-element composition — that's the
        signature move that separates editorial-feminine from the other three
        aesthetics.

        - Hero: NOT a 50/50 split. Use a 3-column grid with overlapping image
          + product cards at intentional non-grid angles.
        - Service cards: stagger their vertical positions (alternating
          margin-top offsets) so the row reads as a magazine spread, not a
          grid.
        - Use negative margins and rotated transforms on at least one
          decorative element per page.
        - Imagery dominates over typography in proportion (60/40 image-to-
          text ratio across the home page).
        - Trust signals block: numeric-stat-driven (large display numerals
          for "400+ guests" / "98% return rate"), not avatar-stack.
    """),

    "layout_sketch_css": _d("""
        /* Signature hero — asymmetric overlapping cluster */
        .hero {
          display: grid;
          grid-template-columns: 0.9fr 1.3fr 0.5fr;
          grid-template-rows: auto auto;
          grid-template-areas:
            "headline portrait product"
            "subhead  portrait product"
            "trust    portrait .";
          gap: 1.5rem 2rem;
          padding: 4rem 2rem;
          position: relative;
        }
        .hero__headline { grid-area: headline; align-self: end; }
        .hero__subhead  { grid-area: subhead; max-width: 36ch; }
        .hero__trust    { grid-area: trust; }
        .hero__portrait {
          grid-area: portrait;
          aspect-ratio: 3 / 4;          /* one of the 5 allowed by kit_generation */
          object-fit: cover;
          border-radius: 6px;
          margin-top: -2rem;            /* breaks grid baseline intentionally */
          z-index: 1;
        }
        .hero__product {
          grid-area: product;
          aspect-ratio: 1 / 1;
          object-fit: cover;
          border-radius: 6px;
          transform: rotate(-3deg) translateY(2rem);
          margin-left: -3rem;          /* overlaps portrait */
          box-shadow: 0 16px 32px rgba(42, 26, 36, 0.18);
          z-index: 2;
        }
        @media (max-width: 760px) {
          .hero {
            grid-template-columns: 1fr;
            grid-template-areas:
              "headline" "portrait" "product" "subhead" "trust";
          }
          .hero__product { transform: rotate(-2deg); margin-left: 1rem; }
        }

        /* Staggered services — broken grid */
        .services-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 2rem;
        }
        .services-grid > :nth-child(2) { margin-top: 4rem; }
        .services-grid > :nth-child(3) { margin-top: 1.5rem; }
    """),

    "image_prefix": _d("""
        Editorial fashion photography, soft pink and dusty-rose palette with
        cream and deep aubergine contrast, magazine-quality composition,
        asymmetric layered framing, considered femininity, late-afternoon
        natural light, no warm-earth terracotta tones, no clinical setting.
        No text, no logos, no watermarks.
    """).replace("\n", " "),

    "avoid": [
        "warm-earth terracotta or clay accent palette (that is restrained-luxury-warm's territory)",
        "sage green or natural-stone palette (that is natural-organic's territory)",
        "cool whites, pure greys, or icy palette (that is modern-minimal's territory)",
        "classical balanced composition (50/50 splits, centered hierarchy)",
        "geometric grids with sharp edges or zero ornamentation",
        "single-family serif end-to-end (the sans/serif contrast is the identity)",
        "avatar-stack social proof (use numeric display stats instead)",
    ],

    "craft_directive": _d("""
        Magazine motion: theatrical, image-forward, but tasteful.

        Required craft moves (at least 3 of these in the kit):
        - Scroll-triggered staggered card reveals via animation-timeline:
          view() — opacity 0→1 + translateY 24px→0, with per-card
          --animation-delay calculated from :nth-child via custom properties.
        - Overlapping product card with slight rotation transform AND a
          backdrop-filter glass-card overlay where image meets text.
        - Variable-font weight transition on h1 italic across scroll —
          font-variation-settings: "wght" var(--w); --w starts at 700 and
          interpolates to 300 across the first viewport via animation-timeline:
          scroll(root).
        - container queries on .services-grid so cards reflow gracefully when
          embedded in different parents.

        Optional:
        - View Transitions API page-to-page fade between index/services/contacts.
    """),
}


# ─────────────────────────────────────────────────────────────────────
# 3. natural-organic
# ─────────────────────────────────────────────────────────────────────

_NATURAL_ORGANIC = {
    "name": "Natural Organic",

    "palette_directive": _d("""
        Sage greens, warm stones, natural beiges, organic textures.

        - --color-bg: stone / oat / linen, range #ECE5DA — #F2EDE2. Pick ONE.
          Warmer than modern-minimal's whites; cooler than restrained-luxury-
          warm's cream.
        - --color-fg: earthy charcoal / dark olive, range #2C2A26 — #3A352F.
        - --color-accent: a sage or moss green, range #8FA284 — #A8B89A.
          Pick ONE. The accent is botanical, not bright.
        - --color-muted: warm stone gray, range #B5AC9F — #C5BCAE.
        - --color-surface: a slightly paler stone or off-white-with-warm-grey,
          range #F6F2EA — #FAF6EE.
        - Optional --color-bark: deep walnut for emphasis text or footer
          (#3D2F22 — #4F3F30).

        The palette must feel hand-mixed, not corporate. Avoid saturated
        accents — everything sits at low-medium saturation.
    """),

    "typography_directive": _d("""
        Humanist serif primary — softer and more textural than Fraunces.

        - Headings: humanist serif. Recommended: Lora (variable), Source Serif
          Pro, Merriweather, or Cardo. Use weights 400/600. The serifs should
          feel pen-drawn, not stencil-cut.
        - Body: humanist sans or system humanist stack. Recommended: Atkinson
          Hyperlegible, IBM Plex Sans, or system humanist (-apple-system,
          BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif).
        - Italic axis used for emphasis but the italic should feel calligraphic,
          not display-dramatic.
        - Optional: introduce a single SVG hand-drawn flourish or initial-cap
          decoration on the hero (paid character of craft).
    """),

    "layout_directive": _d("""
        Organic flow with off-grid imagery placement. The composition should
        feel arranged-by-hand, not laid-out-on-a-grid.

        - Hero: NOT a strict 50/50 column split. Instead, position headline +
          subhead absolutely within a relatively-positioned container, with
          imagery floating at off-grid percentages.
        - Backgrounds use subtle SVG noise/grain overlay (data-URI inlined,
          ≤2KB) for textural warmth.
        - Soft drop-shadows (large blur, low opacity) on cards — depth feels
          organic, not lifted.
        - Decorative botanical SVG elements (single-stroke leaf or sprig) used
          at corners or section transitions, low opacity.
        - Trust signals: written testimonial in serif italic with hand-rendered
          punctuation (em-dashes for attribution).
    """),

    "layout_sketch_css": _d("""
        /* Signature hero — organic flow, off-grid placement */
        .hero {
          position: relative;
          min-height: 80vh;
          padding: 8vh 6vw;
          background:
            url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Cfilter id='n'%3E%3CfeTurbulence baseFrequency='0.85' numOctaves='2'/%3E%3CfeColorMatrix values='0 0 0 0 0.18 0 0 0 0 0.16 0 0 0 0 0.12 0 0 0 0.04 0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
        }
        .hero__headline {
          position: absolute;
          top: 14vh; left: 6vw;
          max-width: 56%;
        }
        .hero__subhead {
          position: absolute;
          top: 38vh; left: 6vw;
          max-width: 32ch;
        }
        .hero__portrait {
          position: absolute;
          right: 6vw; top: 8vh;
          width: 38vw;
          aspect-ratio: 3 / 4;
          object-fit: cover;
          border-radius: 6px;
          box-shadow: 0 30px 80px -20px rgba(60, 50, 40, 0.18);
        }
        .hero__leaf {
          position: absolute;
          bottom: 8vh; left: 28vw;
          width: 96px; height: 96px;
          opacity: 0.55;
          /* SVG botanical sprig inline */
        }
        @media (max-width: 760px) {
          .hero { min-height: auto; padding: 4rem 1.5rem; }
          .hero__headline, .hero__subhead, .hero__portrait, .hero__leaf {
            position: static; width: 100%; max-width: none;
            margin-bottom: 2rem;
          }
        }
    """),

    "image_prefix": _d("""
        Botanical wellness photography, sage green and warm-stone palette, raw
        natural materials, hand-crafted aesthetic, plant-forward composition,
        diffuse natural light, organic textures (linen, wood, ceramic), no
        glossy commercial sheen, no clinical setting, no warm terracotta tones.
        No text, no logos, no watermarks.
    """).replace("\n", " "),

    "avoid": [
        "warm-earth terracotta or clay accent palette (that is restrained-luxury-warm's territory)",
        "soft pink, rose, or blush palette (that is editorial-feminine's territory)",
        "cool whites, pure greys, or icy palette (that is modern-minimal's territory)",
        "sharp modern lines, clip-path geometric reveals, or hard edges",
        "glossy commercial photography style",
        "high-saturation accents",
        "geometric grids — composition should feel arranged-by-hand",
    ],

    "craft_directive": _d("""
        Organic motion: slow, breath-paced, plant-like.

        Acceptable craft moves:
        - Gentle scale-up on natural-element images via animation-timeline:
          view() — scale 0.96 → 1.0 over the entry range, no opacity change.
        - Soft glassmorphism on overlay cards using backdrop-filter blur(16px)
          tinted with a sage-green semi-transparent surface.
        - Subtle CSS-driven "breathing" animation on a botanical SVG decorative
          element (scale 1.0 → 1.04 → 1.0 over 6s, infinite, ease-in-out).
        - Smooth scroll behavior on anchor links (scroll-behavior: smooth).
        - SVG noise/grain texture in backgrounds (already in layout sketch).

        Avoid:
        - Sharp transitions, instant snaps, or clip-path reveals.
        - High-tempo staggered sequences.
        - Bold variable-font weight axis swings.
    """),
}


# ─────────────────────────────────────────────────────────────────────
# 4. modern-minimal
# ─────────────────────────────────────────────────────────────────────

_MODERN_MINIMAL = {
    "name": "Modern Minimal",

    "palette_directive": _d("""
        Cool whites and pale greys with a single bold accent. NO warm cream,
        NO terracotta, NO sage, NO blush.

        - --color-bg: cool white or near-white, range #FAFAFB — #FFFFFF.
          Pick ONE. NOT warm-cream.
        - --color-fg: near-black with neutral or cool undertone, range
          #0F0F10 — #1F1F23. NOT a warm-charcoal.
        - --color-accent: pick ONE from:
          (a) deep black #050505 — #0A0A0A;
          (b) electric blue #2563EB — #1D4ED8;
          (c) saturated red #DC2626 — #B91C1C;
          (d) pure yellow #FACC15 — #EAB308 (sparingly, single dot/pill).
          Used for ONE element type (CTA + active link). Everything else
          is greyscale.
        - --color-muted: cool grey, range #D4D4D8 — #E4E4E7. Borders only.
        - --color-surface: pure white #FFFFFF or one shade darker (#F4F4F5).
          Cards lift via 1px borders, not shadows.

        Greyscale dominance: 95% bg/fg/muted, 5% accent.
    """),

    "typography_directive": _d("""
        Geometric variable sans-serif primary. NO serif. NO italic display
        type. The typographic identity is geometric precision.

        - Display + body: same family, exploit variable weight axis. All
          recommendations below are free + variable-axis + open-licensed —
          buyer never has to swap to a licensed family. Pick ONE family for
          the kit.
          Recommended: Inter (Rasmus Andersson; variable wght axis); Geist
          (Vercel, MIT licensed; clean modern grotesque); Manrope (variable;
          slightly humanist edge); Space Grotesk (variable; sharper terminals).
          IBM Plex Sans is acceptable. JetBrains Mono is acceptable for
          accent labels (uppercase metadata, version tags) only.
        - Headlines: large + bold (700–900 weight), tracked tight (-0.02em).
          Optional: ALL CAPS for h2/h3 with extreme letter-spacing (0.2em).
        - Body: 400 weight, 1.5 line-height.
        - Use font-variation-settings to interpolate "wght" axis across scroll
          for h1 (e.g. starts at 900, interpolates to 600 as user scrolls).
    """),

    "layout_directive": _d("""
        Geometric grid, generous negative space, sharp edges, zero
        ornamentation.

        - Hero: 12-column grid with thin 1px top border. Headline spans columns
          1–7, portrait/visual spans columns 8–12. Aspect ratios pinned, edges
          unrounded (border-radius: 0 or ≤2px).
        - All decorative shapes are clip-path geometric (polygons, hexagons),
          not organic curves.
        - Section dividers are 1px hairlines or clip-path polygon reveals on
          scroll — not blocks of color.
        - Trust signals: numeric stats only, set in display weight on a single
          horizontal row, no avatars.
        - Generous gaps (≥6rem between sections desktop). White space IS the
          ornament.
        - Container queries on cards so they reflow precisely at component
          breakpoints, not viewport breakpoints.
    """),

    "layout_sketch_css": _d("""
        /* Signature hero — strict 12-column geometric grid */
        .hero {
          display: grid;
          grid-template-columns: repeat(12, 1fr);
          grid-template-rows: minmax(70vh, auto);
          gap: 2rem;
          border-top: 1px solid var(--color-fg);
          padding: 4rem 2rem;
          align-items: end;
        }
        .hero__meta {
          grid-column: 1 / 4; grid-row: 1; align-self: start;
          font-size: 0.72rem; letter-spacing: 0.18em;
          text-transform: uppercase; font-weight: 500;
        }
        .hero__headline {
          grid-column: 1 / 8; grid-row: 1; align-self: end;
          font-size: clamp(2.5rem, 7vw, 6rem);
          font-weight: 800; letter-spacing: -0.02em; line-height: 0.92;
          font-variation-settings: "wght" var(--h1-w, 800);
        }
        .hero__visual {
          grid-column: 8 / 13; grid-row: 1;
          aspect-ratio: 3 / 4;
          background: var(--color-muted);
          object-fit: cover; border-radius: 0;
        }
        @media (max-width: 760px) {
          .hero { grid-template-columns: 1fr; }
          .hero__meta, .hero__headline, .hero__visual { grid-column: 1; }
        }

        /* Geometric clip-path section divider */
        .divider-clip {
          height: 4rem; background: var(--color-fg);
          clip-path: polygon(0 0, 100% 30%, 100% 100%, 0 70%);
        }

        /* Container query on card grid */
        .cards-host { container-type: inline-size; }
        .cards { display: grid; grid-template-columns: 1fr; gap: 1rem; }
        @container (min-width: 600px) { .cards { grid-template-columns: repeat(2, 1fr); } }
        @container (min-width: 900px) { .cards { grid-template-columns: repeat(3, 1fr); } }
    """),

    "image_prefix": _d("""
        Architectural minimalist photography, cool whites and pale greys with
        a single accent only, geometric composition, clean negative space,
        sharp directional light, NO warm tones, NO soft pinks, NO sage greens,
        NO organic texture, no clutter, brutalist or Bauhaus framing.
        No text, no logos, no watermarks.
    """).replace("\n", " "),

    "avoid": [
        "warm cream backgrounds — bg must be cool-white or pure white only",
        "terracotta, clay, or warm-earth accents (that is restrained-luxury-warm's territory)",
        "soft pink, rose, or blush palette (that is editorial-feminine's territory)",
        "sage green or natural-stone palette (that is natural-organic's territory)",
        "serif italic typography of any kind",
        "Fraunces, Playfair, Cormorant, Lora, or any serif family",
        "rounded card corners >2px",
        "drop-shadows on cards (use 1px borders instead)",
        "organic SVG textures (noise, grain, hand-drawn flourishes)",
        "asymmetric magazine composition or off-grid placement",
        "decorative seal-badges, ornamental flourishes, or hand-rendered punctuation",
    ],

    "craft_directive": _d("""
        Modern-minimal must demonstrate at least THREE native CSS scroll-driven
        animation effects. The kit must ship with ZERO CDN scripts.

        Required craft moves (3+ of these MUST appear in the kit):
        1. animation-timeline: scroll(root) on the hero h1 —
           font-variation-settings "wght" interpolates from 900 → 600 across
           the first viewport.
        2. animation-timeline: view() on services cards — opacity 0 → 1 +
           translateY 32px → 0, with stagger via per-card --animation-delay
           calculated from :nth-child * 80ms.
        3. clip-path reveal on a geometric section divider — clip-path:
           polygon() animates from collapsed-to-line to fully-visible across
           the entry range.
        4. container queries on the services grid so cards adapt to component
           context, not just viewport.

        Vanilla JS in main.js permitted (≤80 lines, no imports) for any
        IntersectionObserver fallback if a craft move requires it.
    """),
}


# ─────────────────────────────────────────────────────────────────────
# Default fallback (matches v1.1 hardcoded prefix; safe behavior for
# unknown aesthetics so workshop doesn't crash on a typo or new label)
# ─────────────────────────────────────────────────────────────────────

DEFAULT_CONFIG: dict[str, Any] = {
    "name": "Default (unknown aesthetic — fallback to v1.1 behavior)",
    "palette_directive": _d("""
        Pick palette from references' palette_hex arrays, refining for AA
        contrast against --color-bg. (This is v1.1 behavior — provided as a
        safety fallback for unknown aesthetic_direction values.)
    """),
    "typography_directive": _d("""
        Single Google Fonts family, at most two weights, with system-fallback
        stack to avoid render-blocking.
    """),
    "layout_directive": _d("""
        Two-zone hero, alternating service rows, sticky right-rail booking on
        /services, centered small section titles, horizontal closing strip.
    """),
    "layout_sketch_css": _d("""
        /* Use kit-template scaffold structure */
        .hero { display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; }
    """),
    "image_prefix": _d("""
        Editorial wellness photography for restrained luxury beauty clinic.
        Soft natural lighting, warm cinematic palette, contemporary lifestyle
        aesthetic. No clinical settings, no surgical equipment, no medical
        apparel — this is considered self-care, not medical procedure.
        Consistent matte film finish, subtle organic grain. No text, no logos,
        no watermarks.
    """).replace("\n", " "),
    "avoid": [],
    "craft_directive": _d("""
        Restrained motion. Single-element transitions only. No CDN scripts.
    """),
}


# ─────────────────────────────────────────────────────────────────────
# CONFIGS dict + lookup helpers
# ─────────────────────────────────────────────────────────────────────

CONFIGS: dict[str, dict[str, Any]] = {
    "restrained-luxury-warm": _RESTRAINED_LUXURY_WARM,
    "editorial-feminine":     _EDITORIAL_FEMININE,
    "natural-organic":        _NATURAL_ORGANIC,
    "modern-minimal":         _MODERN_MINIMAL,
}

# Strips a trailing "-vN" run-version suffix so queue identifiers
# ("modern-minimal-v2", "modern-minimal-v3") map to the same config base
# ("modern-minimal"). Keeps config keys 1:1 with aesthetic identity, not run.
_VERSION_SUFFIX_RE = re.compile(r"-v\d+$")


def normalize_aesthetic(name: str) -> str:
    """Strip trailing -vN suffix used for regeneration runs.

    >>> normalize_aesthetic("modern-minimal-v2")
    'modern-minimal'
    >>> normalize_aesthetic("editorial-feminine")
    'editorial-feminine'
    """
    return _VERSION_SUFFIX_RE.sub("", name)


def get_config(aesthetic_direction: str) -> dict[str, Any]:
    """Return the config dict for an aesthetic_direction.

    Normalizes -vN suffixes. Logs a warning and returns DEFAULT_CONFIG if the
    base aesthetic is unknown — workshop continues with v1.1 behavior rather
    than crashing on a typo or a new label that hasn't been configured yet.
    """
    base = normalize_aesthetic(aesthetic_direction)
    cfg = CONFIGS.get(base)
    if cfg is None:
        log.warning(
            "aesthetic_direction %r (normalized %r) has no config in CONFIGS; "
            "falling back to DEFAULT_CONFIG (v1.1 behavior)",
            aesthetic_direction, base,
        )
        return DEFAULT_CONFIG
    return cfg


def known_aesthetics() -> list[str]:
    """Sorted list of base aesthetic names with concrete configs."""
    return sorted(CONFIGS)


# ─────────────────────────────────────────────────────────────────────
# Schema validation (run at import time — fail fast on broken config)
# ─────────────────────────────────────────────────────────────────────

_REQUIRED_FIELDS = (
    "name",
    "palette_directive",
    "typography_directive",
    "layout_directive",
    "layout_sketch_css",
    "image_prefix",
    "avoid",
    "craft_directive",
)


def _validate_configs() -> None:
    """Sanity-check every config has the required fields and types.

    Catches dropped fields and typed-mismatched fields at import time so
    workshop.py doesn't fail mid-run with a KeyError when it goes to look
    up image_prefix or avoid.
    """
    for key, cfg in {**CONFIGS, "_DEFAULT_": DEFAULT_CONFIG}.items():
        for field in _REQUIRED_FIELDS:
            if field not in cfg:
                raise RuntimeError(
                    f"aesthetic_configs: {key!r} missing required field {field!r}"
                )
        if not isinstance(cfg["avoid"], list):
            raise RuntimeError(
                f"aesthetic_configs: {key!r} field 'avoid' must be a list, "
                f"got {type(cfg['avoid']).__name__}"
            )
        if not isinstance(cfg["image_prefix"], str) or not cfg["image_prefix"].strip():
            raise RuntimeError(
                f"aesthetic_configs: {key!r} field 'image_prefix' must be a "
                f"non-empty string"
            )


_validate_configs()


# ─────────────────────────────────────────────────────────────────────
# CLI for debugging — prints config for a given aesthetic
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":  # pragma: no cover
    import argparse
    import json

    p = argparse.ArgumentParser(
        description="Inspect a Workshop v1.2 aesthetic config."
    )
    p.add_argument(
        "aesthetic",
        nargs="?",
        help="aesthetic name (with optional -vN suffix); omit to list all",
    )
    args = p.parse_args()

    if args.aesthetic is None:
        print("Known aesthetics:")
        for name in known_aesthetics():
            print(f"  - {name}")
        print(f"\nDefault fallback for unknown: {DEFAULT_CONFIG['name']}")
    else:
        cfg = get_config(args.aesthetic)
        print(f"=== {args.aesthetic} → {cfg['name']} ===\n")
        for field in _REQUIRED_FIELDS:
            print(f"--- {field} ---")
            value = cfg[field]
            if isinstance(value, list):
                print(json.dumps(value, indent=2))
            else:
                print(value)
            print()
