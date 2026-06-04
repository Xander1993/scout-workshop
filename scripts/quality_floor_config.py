"""Tuning knobs for the v1.5 awwwards quality gates. Live-editable; no code change to tune."""

QUALITY_FLOOR = {
    "diversity_reject_below": 0.34,      # diversity_gate.is_repeat threshold
    "hero_scale_min": 4,                 # render_metrics.hero_scale_ratio floor
    "template_tells_max": 1,             # >this many rendered tells → genericness fail
    "vertical_void_max_px": {            # density vertical_void ceiling, per kit_type
        "editorial-studio": 900,
        "single-product": 1600,          # one long page → larger gaps tolerated
    },
    "void_short_page_px": 4000,          # a gap is only a "void" if total page height < this
    "retry": {
        "max": 1,
        "disable_palette_perturb_on_retry": True,
        "reuse_images": True,
    },
    "run_budget_s": 5400,                # wall-clock budget; checked BEFORE a retry
}
