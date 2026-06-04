"""Render an awwwards sub-aesthetic config into prompt-ready directives, and
retrieve premium references for a (sub_aesthetic, kit_type) from the corpus.

Palette perturbation here is COSMETIC run-to-run variation, NOT the premium or
diversity lever — structure (hero archetype + section topology + the per-run
signature concept) carries premium. Per design §11/§14 palette is a tie-breaker
(palette-rotation alone is the proven no-op). Keep it, don't trust it as variety.
"""
from __future__ import annotations
import colorsys
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aesthetic_configs import get_awwwards_config  # type: ignore


def _seeded_unit(seed: int, salt: str) -> float:
    h = hashlib.sha256(f"{seed}:{salt}".encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF  # 0..1


def perturb_hex(hex_str: str, seed: int) -> str:
    """Bounded deterministic HLS shift: H ±8°, L ±0.05, S ±0.05. On-aesthetic."""
    s = hex_str.lstrip("#")
    r, g, b = (int(s[i:i + 2], 16) / 255 for i in (0, 2, 4))
    h, l, sat = colorsys.rgb_to_hls(r, g, b)
    h = (h + (_seeded_unit(seed, "h") - 0.5) * (16 / 360)) % 1.0
    l = min(1.0, max(0.0, l + (_seeded_unit(seed, "l") - 0.5) * 0.10))
    sat = min(1.0, max(0.0, sat + (_seeded_unit(seed, "s") - 0.5) * 0.10))
    r, g, b = colorsys.hls_to_rgb(h, l, sat)
    return "#" + "".join(f"{int(round(c * 255)):02X}" for c in (r, g, b))


def render_directives(sub_aesthetic: str, seed: int, perturb: bool = True) -> dict:
    cfg = get_awwwards_config(sub_aesthetic)
    pal = cfg["palette"]
    # perturb=False (retry path): use the pinned palette verbatim — palette
    # perturbation is the proven no-op, so a retry varies STRUCTURE, not colour.
    _p = (lambda h: perturb_hex(h, seed)) if perturb else (lambda h: h.upper())
    bg = _p(pal["bg"])
    fg = _p(pal["fg"])
    accents = [_p(a) for a in pal["accents"]]
    supporting = [_p(c) for c in pal["supporting"]]
    palette_directive = (
        "Pinned palette (perturbed for this run — use these EXACT hexes as CSS tokens, do NOT range):\n"
        f"  --color-bg: {bg};\n  --color-fg: {fg};\n"
        f"  --color-accent: {accents[0]};\n"
        + "".join(f"  --color-accent-{i + 2}: {a};\n" for i, a in enumerate(accents[1:]))
        + "".join(f"  --color-support-{i + 1}: {c};\n" for i, c in enumerate(supporting))
        + "This is the only chromatic system on the page. No other accents."
    )
    typ = cfg["typography"]
    typography_directive = (
        f"Primary type class: {typ['primary']}. Hero h1 MUST use font-size: {typ['hero_h1_clamp']} "
        f"(monumental display scale, non-negotiable). Secondary: {typ['secondary']}. "
        "Tight tracking on display type; generous body line-height."
    )
    motion_directive = (
        "Realize this motion vocabulary with cdnjs GSAP + Lenis (+ SplitType where the concept calls "
        "for kinetic type), each with SRI integrity + crossorigin=anonymous + async + graceful "
        "degradation:\n- " + "\n- ".join(cfg["motion_vocabulary"])
    )
    return {
        "register_family": cfg["register_family"],
        "palette_directive": palette_directive,
        "typography_directive": typography_directive,
        "photography_prefix": cfg["photography_prefix"],
        "motion_directive": motion_directive,
        "avoid": cfg.get("avoid", []),
    }


# ----- retrieval -----------------------------------------------------------

_KIT_TYPE_RTYPES = {
    "single-product": {"product_marketing"},
    "editorial-studio": {"studio_site", "agency_portfolio", "product_marketing"},
}
# A kit-type also constrains the HERO archetype it may inherit. reference_type
# (e.g. product_marketing) is too coarse — a product-marketing site can still be
# wordmark-led (Marvell) and must NOT steer a single-product page into an
# editorial wordmark hero. Keying valid heroes off the kit-type is robust to
# such mis-tagging and keeps the two kit-types structurally distinct.
_KIT_TYPE_HEROES = {
    "single-product": {"full_bleed_photo_hero", "product_canvas_pinned"},
    "editorial-studio": {"monumental_wordmark", "split_editorial"},
}
_ALLOWED_SOURCES = {"curated", "awwwards"}


def filter_refs(pool: list[dict], kit_type: str) -> list[dict]:
    """Post-filter a candidate pool: premium sources only, never listing_frame,
    reference_type AND hero_archetype appropriate to the kit_type."""
    allow = _KIT_TYPE_RTYPES[kit_type]
    heroes = _KIT_TYPE_HEROES.get(kit_type)
    return [p for p in pool
            if p.get("source") in _ALLOWED_SOURCES
            and p.get("reference_type") != "listing_frame"
            and p.get("reference_type") in allow
            and (heroes is None or p.get("hero_archetype") in heroes)]


def art_direction_query(sub_aesthetic: str, kit_type: str) -> str:
    cfg = get_awwwards_config(sub_aesthetic)
    return (f"{cfg['register_family']} {cfg['typography']['primary']} {kit_type} "
            "monumental editorial premium award-winning website, full-bleed plates, "
            "restraint, scroll choreography, signature concept")


def retrieve_awwwards_refs(sub_aesthetic: str, kit_type: str, vault_index: dict, k: int = 4) -> list[dict]:
    """Semantic retrieval over the corpus, kit_type-filtered, reranked. Returns
    [{payload, note_path, image_path}], best first. Skips refs lacking
    hero_archetype (the structural ground truth the brief needs)."""
    import scout_lib as sl  # type: ignore
    q = art_direction_query(sub_aesthetic, kit_type)
    qvec = sl.embed(q)
    # Wide vector window (60), then rerank narrows to k. A sub-aesthetic whose
    # palette is far from a premium ref (e.g. sun-baked vs glossy Apple) ranks
    # those refs 30-60 in raw cosine; the reranker reorders them well once
    # they're candidates, so recall matters more than the initial cutoff.
    points = sl.qdrant_query(qvec, limit=60)
    pool = []
    for p in points:
        pl = dict(p.payload or {})
        pl["_point_id"] = str(p.id)
        pool.append(pl)
    filtered = filter_refs(pool, kit_type)
    if not filtered:
        return []
    docs = [
        f"{r.get('title','')} | {r.get('hero_archetype','')} | "
        f"{' '.join(r.get('section_topology') or [])} | {r.get('signature_idea','')} | "
        f"{' '.join(r.get('techniques') or [])}"
        for r in filtered
    ]
    reranked = sl.rerank(q, docs, top_n=min(k, len(docs)))
    ordered = [filtered[r["index"]] for r in reranked]
    out = []
    for r in ordered:
        if not r.get("hero_archetype"):
            continue
        entry = vault_index.get(r.get("_point_id")) or vault_index.get(r.get("id"))
        out.append({
            "payload": r,
            "note_path": entry[0] if entry else None,
            "image_path": entry[1] if entry else None,
        })
    return out
