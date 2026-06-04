import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "dashboard"))
import app


def test_read_verdict_passed(tmp_path):
    (tmp_path / "verdict.json").write_text(json.dumps({
        "passed": True, "reasons": [],
        "craft": {"verdict": "pass", "scores": {"monumentality": 3, "signature_moment": 3}}}),
        encoding="utf-8")
    v = app.read_register_verdict(tmp_path)
    assert v is not None
    assert v["passed"] is True and v["flagged"] is False and v["craft_verdict"] == "pass"
    assert v["craft_scores"]["monumentality"] == 3


def test_read_verdict_flagged_by_suffix_and_sentinel(tmp_path):
    d = tmp_path / "2026-06-04T00-00-00Z-awwwards-sun-baked-single-product-flagged"
    d.mkdir()
    (d / "verdict.json").write_text(json.dumps({
        "passed": False, "reasons": ["craft below_bar: weak"],
        "craft": {"verdict": "below_bar", "scores": {}}}), encoding="utf-8")
    (d / "DO_NOT_DEPLOY").write_text("flagged", encoding="utf-8")
    v = app.read_register_verdict(d)
    assert v["passed"] is False and v["flagged"] is True
    assert "craft below_bar: weak" in v["reasons"]


def test_read_verdict_absent_is_none(tmp_path):
    assert app.read_register_verdict(tmp_path) is None


def test_read_verdict_corrupt_is_none(tmp_path):
    (tmp_path / "verdict.json").write_text("{ broken", encoding="utf-8")
    assert app.read_register_verdict(tmp_path) is None
