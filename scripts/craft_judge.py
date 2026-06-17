"""Awwwards craft judge (design §13) — Claude reads the rendered screenshots +
the source markup and returns a premium-vs-template verdict.

Dependency-injected (`run_claude`, `load_prompt_template`, `extract_json`) so this
module doesn't import workshop (which imports the gate) — no circular import.
"""
from __future__ import annotations
import json
from pathlib import Path


_CRAFT_KEYS = ("monumentality", "restraint", "composition", "motion_realized", "signature_moment")


def _enforce_floor(v: dict) -> str:
    """The §13 floor, computed in code from the judge's numeric scores so a model
    that self-reports 'pass' while scoring a 0 (or below the weighted floor) is
    still vetoed. Thresholds live in quality_floor_config (live-tunable)."""
    from quality_floor_config import QUALITY_FLOOR as QF  # leaf module, no cycle
    scores = v.get("scores") or {}
    tells = v.get("template_tells") or []
    vals = [scores.get(k, 0) for k in _CRAFT_KEYS]
    v["weighted_sum"] = sum(vals)
    # Deterministic density veto: the craft judge was structurally blind to emptiness
    # (it only saw the model's self-reported scores), so a mostly-empty page could read
    # "pass". Wire the render-metric density signals in as a HARD veto so the craft
    # verdict can never say pass on a void/under-inked/hero-overflowing page. Absent
    # density (render_metrics failed) leaves the safe defaults → no spurious veto.
    dens = v.get("density") or {}
    density_veto = (dens.get("void_ratio", 0) > QF["void_ratio_max"]
                    or dens.get("ink_coverage", 1.0) < QF["ink_coverage_min"]
                    or dens.get("hero_vh_ratio", 0) > QF["hero_vh_max"])
    veto = (not scores
            or any(s == 0 for s in vals)
            or scores.get("signature_moment", 0) < QF["craft_signature_min"]
            or scores.get("monumentality", 0) < QF["craft_monumentality_min"]
            or len(tells) >= QF["craft_tells_veto_at"]
            or sum(vals) < QF["craft_weighted_min"]
            or density_veto)
    return "below_bar" if veto else "pass"


def run(run_dir, kit_dir, kit_type, concept, screenshots, *,
        run_claude, load_prompt_template, extract_json, density=None) -> dict:
    run_dir = Path(run_dir)
    if not screenshots:  # screenshots are load-bearing for the visual judge
        v = {"verdict": "below_bar", "reasons": "no-screenshots", "scores": {}, "template_tells": []}
        (run_dir / "craft_verdict.json").write_text(json.dumps(v, indent=2), encoding="utf-8")
        return v
    template = load_prompt_template("audit_craft_awwwards")
    prompt = (template
              .replace("{{KIT_TYPE}}", kit_type)
              .replace("{{SIGNATURE_MOVE}}", (concept or {}).get("signature_move", ""))
              .replace("{{SHOT_PATHS}}", " ".join(str(s) for s in screenshots))
              .replace("{{KIT_DIR}}", str(kit_dir)))
    out = run_claude(prompt, effort="medium", add_dirs=[Path(kit_dir)], tools="Read")
    try:
        v = json.loads(extract_json(out))
    except Exception as e:  # noqa: BLE001 — a broken judge must not crash the run
        v = {"verdict": "below_bar", "reasons": f"judge JSON parse failed: {e}",
             "scores": {}, "template_tells": []}
    # Recompute the §13 verdict from scores in code — never trust the model's
    # self-reported verdict (it can contradict its own rule). The deterministic
    # density signal is folded in as a HARD veto (see _enforce_floor).
    v["density"] = density or {}
    v["verdict"] = _enforce_floor(v)
    (run_dir / "craft_verdict.json").write_text(json.dumps(v, indent=2), encoding="utf-8")
    return v
