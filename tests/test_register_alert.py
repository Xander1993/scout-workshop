import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import workshop


def test_alert_text_pass(tmp_path):
    rd = tmp_path / "2026-06-04T00-00-00Z-awwwards-sun-baked-single-product"
    (rd / "kit" / "screenshots").mkdir(parents=True)
    (rd / "kit" / "screenshots" / "home-desktop.png").write_bytes(b"x")
    (rd / "verdict.json").write_text(json.dumps({
        "passed": True, "reasons": [],
        "craft": {"verdict": "pass", "scores": {
            "monumentality": 3, "restraint": 3, "composition": 3,
            "motion_realized": 3, "signature_moment": 3}},
        "rm": {"hero_scale_ratio": 59.5, "template_tells": []}}), encoding="utf-8")
    text, shot = workshop._register_alert_text(rd, "sun-baked", "single-product")
    assert "PREMIUM" in text and "sun-baked" in text and "single-product" in text
    assert "15/15" in text
    assert shot is not None and shot.name == "home-desktop.png"


def test_alert_text_flagged(tmp_path):
    rd = tmp_path / "2026-06-04T00-00-00Z-awwwards-warm-earth-editorial-studio-flagged"
    rd.mkdir(parents=True)
    (rd / "verdict.json").write_text(json.dumps({
        "passed": False, "reasons": ["craft below_bar: weak hero"],
        "craft": {"verdict": "below_bar", "scores": {}}}), encoding="utf-8")
    (rd / "DO_NOT_DEPLOY").write_text("x", encoding="utf-8")
    text, shot = workshop._register_alert_text(rd, "warm-earth", "editorial-studio")
    assert "FLAGGED" in text and "craft below_bar: weak hero" in text
    assert shot is None


def test_alert_text_missing_verdict_is_flagged(tmp_path):
    rd = tmp_path / "2026-06-04T00-00-00Z-awwwards-sun-baked-editorial-studio"
    rd.mkdir(parents=True)
    text, shot = workshop._register_alert_text(rd, "sun-baked", "editorial-studio")
    assert "FLAGGED" in text                     # no verdict.json → treat as not-shipped
