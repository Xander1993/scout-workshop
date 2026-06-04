"""Awwwards craft judge (design §13) — Claude reads the rendered screenshots +
the source markup and returns a premium-vs-template verdict.

Dependency-injected (`run_claude`, `load_prompt_template`, `extract_json`) so this
module doesn't import workshop (which imports the gate) — no circular import.
"""
from __future__ import annotations
import json
from pathlib import Path


def run(run_dir, kit_dir, kit_type, concept, screenshots, *,
        run_claude, load_prompt_template, extract_json) -> dict:
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
    v.setdefault("verdict", "below_bar")
    (run_dir / "craft_verdict.json").write_text(json.dumps(v, indent=2), encoding="utf-8")
    return v
