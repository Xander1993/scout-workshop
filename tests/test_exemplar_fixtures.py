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
import sys, re, json, pathlib, pytest
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


# image basenames referenced anywhere a kit can pull an asset from
_IMG_REF_RE = re.compile(r"[\w\-./]+\.(?:png|jpg|jpeg|webp|avif|svg)", re.I)
_SRC_SUFFIXES = (".html", ".css", ".js")


def _referenced_image_stems(kit: pathlib.Path) -> set[str]:
    """Every image basename (sans extension) referenced by the kit's
    html/css/js — i.e. every asset the kit actually renders."""
    stems: set[str] = set()
    for f in kit.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in _SRC_SUFFIXES:
            continue
        txt = f.read_text(encoding="utf-8", errors="ignore")
        for m in _IMG_REF_RE.findall(txt):
            stems.add(pathlib.PurePosixPath(m).stem)
    return stems


def _documented_image_stems(kit: pathlib.Path) -> set[str]:
    """Top-level keys of image-prompts.json — the documented provenance set."""
    return set(json.loads((kit / "image-prompts.json").read_text(encoding="utf-8")))


@pytest.mark.parametrize("name,kit_type", FIXTURES)
def test_exemplar_image_prompts_match_shipped_images(name, kit_type):
    """image-prompts.json must honestly document EXACTLY the images the kit
    renders: no stale entry for an image the redesign dropped, and no shipped
    image left with zero provenance record. Locks the hand-audited provenance
    of every exemplar so a future edit can't silently desync the two."""
    kit = EXEMPLARS / name
    if not kit.is_dir() or not (kit / "image-prompts.json").is_file():
        pytest.skip(f"exemplar {name} has no image-prompts.json")
    documented = _documented_image_stems(kit)
    referenced = _referenced_image_stems(kit)
    assert documented == referenced, {
        "documented_but_unreferenced": sorted(documented - referenced),
        "referenced_but_undocumented": sorted(referenced - documented),
    }


def test_provenance_check_detects_desync(tmp_path):
    """Self-test: the documented==referenced invariant must actually flag a
    stale extra and a missing entry (guards against a no-op checker)."""
    kit = tmp_path / "kit"
    kit.mkdir()
    (kit / "index.html").write_text(
        '<img src="assets/real-hero.png"><img src="assets/real-tile.png">',
        encoding="utf-8",
    )
    (kit / "image-prompts.json").write_text(
        json.dumps({"real-hero": {}, "stale-dropped": {}}), encoding="utf-8"
    )
    documented = _documented_image_stems(kit)
    referenced = _referenced_image_stems(kit)
    assert documented != referenced
    assert sorted(documented - referenced) == ["stale-dropped"]
    assert sorted(referenced - documented) == ["real-tile"]


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
