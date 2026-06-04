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
    fake = '{"scores":{"monumentality":3,"signature_moment":3},"verdict":"pass","template_tells":[]}'
    v = cj.run(tmp_path, tmp_path / "kit", "editorial-studio", {"signature_move": "y"},
               ["/s/home.png"],
               run_claude=lambda p, **k: fake,
               load_prompt_template=lambda n: "{{KIT_TYPE}} {{SIGNATURE_MOVE}} {{SHOT_PATHS}} {{KIT_DIR}}",
               extract_json=lambda s: s)
    assert v["verdict"] == "pass"
    assert (tmp_path / "craft_verdict.json").exists()


def test_bad_json_falls_back_to_below_bar(tmp_path):
    v = cj.run(tmp_path, tmp_path / "kit", "editorial-studio", {}, ["/s/home.png"],
               run_claude=lambda p, **k: "not json",
               load_prompt_template=lambda n: "x",
               extract_json=lambda s: (_ for _ in ()).throw(ValueError("no json")))
    assert v["verdict"] == "below_bar"
