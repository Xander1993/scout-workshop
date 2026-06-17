"""Tuning knobs for the v1.5 awwwards quality gates. Live-editable; no code change to tune."""

QUALITY_FLOOR = {
    "diversity_reject_below": 0.34,      # diversity_gate.is_repeat threshold
    "hero_scale_min": 4,                 # render_metrics.hero_scale_ratio floor
    "hero_vh_max": 2.0,                  # hero CEILING: uncapped hero height in viewport
                                         # units. Real heroes measure <=1.4vh (full-bleed
                                         # photo) — anything past 2.0vh is a wordmark/
                                         # headline overflowing several screens (broken).
    "template_tells_max": 1,             # >this many rendered tells → genericness fail
    "vertical_void_max_px": {            # ALWAYS-ON density ceiling (~2.6x the 900px
        "editorial-studio": 2400,        # capture viewport). A gap larger than this is
        "single-product": 2400,          # a broken/sparse page; both real premium kits
        "kinetic-experimental": 1600,    # measure <=1300px, so they clear it comfortably.
    },                                   # (kinetic is STRICTER, not looser: legit pin runways
                                         #  are [data-pin]-excluded, so any remaining >1600px gap
                                         #  is a genuinely empty/oversized section — flag it.)
    "void_ratio_max": 0.60,              # PROPORTIONAL density floor: sum-of-gaps / page_height.
                                         # Catches the "mostly empty page" the single-gap ceiling
                                         # misses (real premium kits measure <=0.47 across all
                                         # viewports; a ~70%-empty page reads >0.6).
    "ink_coverage_min": 0.05,            # screenshot ink-coverage veto: fraction of full-page
                                         # pixels carrying ink. Real kits >=0.13; a near-blank
                                         # cream void scores ~0, so 0.05 is a safe broken-page floor.
    # ----- craft judge §13 floor (was prompt-prose only; now code-enforced) -----
    "craft_weighted_min": 11,            # sum of the 5 craft scores must reach this
    "craft_signature_min": 2,            # signature_moment hard floor
    "craft_monumentality_min": 2,        # monumentality hard floor
    "craft_tells_veto_at": 2,            # judge-reported template_tells >= this → veto
    "retry": {
        "max": 1,
        "disable_palette_perturb_on_retry": True,
        "reuse_images": True,
    },
    "run_budget_s": 5400,                # wall-clock budget; checked BEFORE a retry
}
