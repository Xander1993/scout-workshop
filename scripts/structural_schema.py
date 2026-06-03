"""Single source of truth for v1.5 structural reference/kit schema.

Consumed by scout_lib (Qdrant payload), ingest_daemon (embedding text +
runtime validation), workshop.py (retrieval/diversity), and the scout
playbook (which the LLM follows when writing notes).

PHASE-1 OBLIGATION: SECTION_TYPES must be reconciled with the Gate-A
section_manifest ALLOWED_TYPES when that gate is built. They are NOT in
lockstep today (Gate-A is not yet on disk). tests/test_enum_parity.py
guards drift between THIS module and the playbook only.
"""
from __future__ import annotations

HERO_ARCHETYPES = (
    "monumental_wordmark", "full_bleed_photo_hero", "split_editorial",
    "kinetic_type", "product_canvas_pinned", "immersive_canvas",
)
SECTION_TYPES = (
    "full_bleed_plate", "work_grid", "manifesto", "spec_table",
    "scroll_chapter", "studio_statement", "product_hero",
    "monumental_wordmark", "trust_signals", "case_grid", "callout", "stats_row",
)
MOTION_SIGNATURES = (
    "splittype_stagger", "scroll_pin", "lenis_smooth",
    "parallax", "webgl_canvas", "none",
)
STRUCTURAL_FIELDS = ("hero_archetype", "section_topology", "motion_signature", "signature_idea")


def validate_structural(fm: dict) -> list[str]:
    """Return human-readable problems with a note's structural fields.

    Empty list == valid. Missing fields are NOT errors (legacy notes lack
    them); this validates the SHAPE of fields that ARE present, so callers
    can warn on malformed scout output without rejecting legacy notes.
    """
    errs: list[str] = []
    ha = fm.get("hero_archetype")
    if ha is not None and ha not in HERO_ARCHETYPES:
        errs.append(f"hero_archetype {ha!r} not in {HERO_ARCHETYPES}")
    st = fm.get("section_topology")
    if st is not None:
        if not isinstance(st, list):
            errs.append("section_topology must be a list")
        elif [s for s in st if s not in SECTION_TYPES]:
            errs.append(f"section_topology has unknown types: {[s for s in st if s not in SECTION_TYPES]}")
    ms = fm.get("motion_signature")
    if ms is not None:
        if not isinstance(ms, list):
            errs.append("motion_signature must be a list")
        elif [m for m in ms if m not in MOTION_SIGNATURES]:
            errs.append(f"motion_signature has unknown tags: {[m for m in ms if m not in MOTION_SIGNATURES]}")
    si = fm.get("signature_idea")
    if si is not None and (not isinstance(si, str) or not si.strip()):
        errs.append("signature_idea must be a non-empty string when present")
    return errs
