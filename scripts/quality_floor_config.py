"""Tuning knobs for the v1.5 awwwards quality gates. Live-editable; no code change to tune."""

QUALITY_FLOOR = {
    "diversity_reject_below": 0.34,      # diversity_gate.is_repeat threshold
    "hero_scale_min": 4,                 # render_metrics.hero_scale_ratio floor
    "template_tells_max": 1,             # >this many rendered tells → genericness fail
    "vertical_void_max_px": {            # ALWAYS-ON density ceiling (~2.6x the 900px
        "editorial-studio": 2400,        # capture viewport). A gap larger than this is
        "single-product": 2400,          # a broken/sparse page; both real premium kits
    },                                   # measure <=1300px, so they clear it comfortably.
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
