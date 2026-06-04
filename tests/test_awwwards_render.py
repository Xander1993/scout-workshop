import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import awwwards_render as ar


def test_perturb_is_deterministic_and_bounded():
    base = "#B8462C"
    a = ar.perturb_hex(base, seed=0)
    b = ar.perturb_hex(base, seed=0)
    assert a == b
    assert a.startswith("#") and len(a) == 7
    assert ar.perturb_hex(base, seed=0) != ar.perturb_hex(base, seed=5)


def test_render_directives_has_palette_type_motion_photo():
    d = ar.render_directives("warm-earth", seed=1)
    assert "--color-bg" in d["palette_directive"] and "#" in d["palette_directive"]
    assert "clamp(" in d["typography_directive"]
    assert d["photography_prefix"]
    assert "GSAP" in d["motion_directive"] or "Lenis" in d["motion_directive"]
    assert d["register_family"] == "restrained-monumental"
