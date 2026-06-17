import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import craft_judge as cj


def _boom(*a, **k):
    raise AssertionError("run_claude should not be called")


def test_no_screenshots_is_below_bar_without_calling_claude(tmp_path):
    v = cj.run(tmp_path, tmp_path / "kit", "single-product", {"signature_move": "x"}, [],
               run_claude=_boom, load_prompt_template=lambda n: "T", extract_json=lambda s: s)
    assert v["verdict"] == "below_bar" and v["reasons"] == "no-screenshots"
    assert (tmp_path / "craft_verdict.json").exists()


def test_parses_judge_json_and_writes_verdict(tmp_path):
    fake = ('{"scores":{"monumentality":3,"restraint":3,"composition":3,'
            '"motion_realized":3,"signature_moment":3},"verdict":"pass","template_tells":[]}')
    v = cj.run(tmp_path, tmp_path / "kit", "editorial-studio", {"signature_move": "y"},
               ["/s/home.png"],
               run_claude=lambda p, **k: fake,
               load_prompt_template=lambda n: "{{KIT_TYPE}} {{SIGNATURE_MOVE}} {{SHOT_PATHS}} {{KIT_DIR}}",
               extract_json=lambda s: s)
    assert v["verdict"] == "pass"
    assert (tmp_path / "craft_verdict.json").exists()


def test_enforce_floor_overrides_self_contradicting_pass():
    # The model says "pass" but scored a 0 — the code-enforced §13 floor must veto.
    assert cj._enforce_floor({"verdict": "pass", "template_tells": [], "scores": {
        "monumentality": 3, "restraint": 3, "composition": 3,
        "motion_realized": 0, "signature_moment": 3}}) == "below_bar"


def test_enforce_floor_vetoes_below_weighted_min_and_low_signature():
    # 2+2+2+2+2 = 10 < 11 → veto, even with no zeros.
    assert cj._enforce_floor({"template_tells": [], "scores": {
        "monumentality": 2, "restraint": 2, "composition": 2,
        "motion_realized": 2, "signature_moment": 2}}) == "below_bar"
    # signature_moment 1 < floor of 2 → veto.
    assert cj._enforce_floor({"template_tells": [], "scores": {
        "monumentality": 3, "restraint": 3, "composition": 3,
        "motion_realized": 3, "signature_moment": 1}}) == "below_bar"
    # two judge-reported tells → veto.
    assert cj._enforce_floor({"template_tells": ["card-grid", "repeated-cta"], "scores": {
        "monumentality": 3, "restraint": 3, "composition": 3,
        "motion_realized": 3, "signature_moment": 3}}) == "below_bar"


def test_enforce_floor_passes_clean_premium():
    assert cj._enforce_floor({"template_tells": [], "scores": {
        "monumentality": 3, "restraint": 2, "composition": 3,
        "motion_realized": 3, "signature_moment": 3}}) == "pass"


def test_enforce_floor_vetoes_empty_page_density():
    # Clean craft scores, but the deterministic density signal says the rendered
    # page is mostly empty / under-inked / hero-overflowing → density veto, so the
    # craft verdict can no longer read "pass" on a structurally empty page.
    base = {"template_tells": [], "scores": {
        "monumentality": 3, "restraint": 3, "composition": 3,
        "motion_realized": 3, "signature_moment": 3}}
    assert cj._enforce_floor({**base, "density": {"void_ratio": 0.9}}) == "below_bar"
    assert cj._enforce_floor({**base, "density": {"ink_coverage": 0.01}}) == "below_bar"
    assert cj._enforce_floor({**base, "density": {"hero_vh_ratio": 3.0}}) == "below_bar"


def test_enforce_floor_passes_with_healthy_density():
    base = {"template_tells": [], "scores": {
        "monumentality": 3, "restraint": 3, "composition": 3,
        "motion_realized": 3, "signature_moment": 3}}
    assert cj._enforce_floor({**base, "density": {
        "void_ratio": 0.4, "ink_coverage": 0.2, "hero_vh_ratio": 1.3}}) == "pass"
    # absent density (e.g. render_metrics failed) must not spuriously veto
    assert cj._enforce_floor(base) == "pass"


def test_run_threads_density_into_verdict(tmp_path):
    fake = ('{"scores":{"monumentality":3,"restraint":3,"composition":3,'
            '"motion_realized":3,"signature_moment":3},"verdict":"pass","template_tells":[]}')
    v = cj.run(tmp_path, tmp_path / "kit", "editorial-studio", {}, ["/s/home.png"],
               run_claude=lambda p, **k: fake,
               load_prompt_template=lambda n: "x",
               extract_json=lambda s: s,
               density={"void_ratio": 0.95})
    assert v["verdict"] == "below_bar"


def test_bad_json_falls_back_to_below_bar(tmp_path):
    v = cj.run(tmp_path, tmp_path / "kit", "editorial-studio", {}, ["/s/home.png"],
               run_claude=lambda p, **k: "not json",
               load_prompt_template=lambda n: "x",
               extract_json=lambda s: (_ for _ in ()).throw(ValueError("no json")))
    assert v["verdict"] == "below_bar"
