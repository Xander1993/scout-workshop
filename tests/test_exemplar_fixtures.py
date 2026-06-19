"""Regression fixtures: lock the hand-rebuilt awwwards exemplars as known-good
kits. The exemplars are the quality target the worker redesigns toward, so they
must clear EVERY deterministic static gate at all times. This pins both sides of
the contract:

  * a future gate change that would start falsely flagging award-worthy work
    fails here (the gate got too strict / miscalibrated), and
  * an accidental edit that degrades an exemplar below the bar fails here too.

Only the deterministic gates are asserted (asset hygiene + rendered density /
hero / tells metrics); the LLM craft/codex review is out of scope for CI.
"""
import sys, pathlib, pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import asset_hygiene as ah
import render_metrics as rm
from quality_floor_config import QUALITY_FLOOR as Q

EXEMPLARS = pathlib.Path(__file__).resolve().parent.parent / "exemplars"

# (exemplar dir name, kit-type key for the per-type vertical-void ceiling).
# Every hand-rebuilt exemplar that reached SHIP is pinned here so a future gate
# change or accidental edit that would regress an award-worthy kit fails in CI.
FIXTURES = [
    ("casa-umbral-kinetic", "kinetic-experimental"),
    ("editorial-studio", "editorial-studio"),
    ("editorial-studio-warm-earth", "editorial-studio"),
    ("sun-baked-editorial-studio", "editorial-studio"),
    ("mid-century-foundry", "editorial-studio"),
    ("sun-baked-single-product", "single-product"),
    ("sun-baked-single-product-day", "single-product"),
    ("editorial-mid-century-kinetic", "kinetic-experimental"),
    ("sun-baked-kinetic", "kinetic-experimental"),
]


@pytest.mark.parametrize("name,kit_type", FIXTURES)
def test_exemplar_passes_asset_hygiene(name, kit_type):
    kit = EXEMPLARS / name
    if not kit.is_dir():
        pytest.skip(f"exemplar {name} not present")
    r = ah.check_assets(kit)
    assert r["ok"], r["violations"]


@pytest.mark.parametrize("name,kit_type", FIXTURES)
def test_exemplar_clears_render_floors(name, kit_type):
    kit = EXEMPLARS / name
    if not kit.is_dir():
        pytest.skip(f"exemplar {name} not present")
    m = rm.render_metrics_all(kit)
    void_max = Q["vertical_void_max_px"][kit_type]
    assert m["template_tells"] == [], m["template_tells"]
    assert m["hero_scale_ratio"] >= Q["hero_scale_min"], m
    assert m["hero_vh_ratio"] <= Q["hero_vh_max"], m
    assert m["void_ratio"] <= Q["void_ratio_max"], m
    assert m["ink_coverage"] >= Q["ink_coverage_min"], m
    assert m["max_vertical_void_px"] <= void_max, m
