import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import genericness_proxy as gp

_TEMPLATE_HTML = """<!doctype html><html><body>
<header><nav></nav></header>
<section class="hero"><h1>Welcome</h1></section>
<section class="trust"><div class="avatar"></div></section>
<section class="services"><div class="card">1</div><div class="card">2</div><div class="card">3</div></section>
<a class="cta" href="contact.html">Book</a><a class="cta" href="tel:+15551234567">Call</a>
</body></html>"""
_TEMPLATE_CSS = "body{font-size:1rem}h1{font-size:2rem}"

_PREMIUM_HTML = """<!doctype html><html><body>
<section class="hero-plate"><h1>NAMMA</h1></section>
<section class="manifesto-bleed"><p>...</p></section>
<section class="work-plate"><img></section>
</body></html>"""
_PREMIUM_CSS = "body{font-size:1rem}.hero-plate h1{font-size:clamp(3.5rem, 16vw, 12rem)}.hero-plate{width:100vw}"


def _mk(tmp, html, css):
    kd = tmp / "kit"
    (kd / "assets" / "css").mkdir(parents=True)
    (kd / "index.html").write_text(html)
    (kd / "assets" / "css" / "style.css").write_text(css)
    return kd


def test_template_kit_flagged(tmp_path):
    s = gp.score_kit(_mk(tmp_path, _TEMPLATE_HTML, _TEMPLATE_CSS))
    assert s["verdict"] == "template-leaning"
    assert any("trust" in t for t in s["template_tells"])
    assert any("card grid" in t for t in s["template_tells"])
    assert s["hero_body_ratio"] < 4


def test_premium_kit_passes(tmp_path):
    s = gp.score_kit(_mk(tmp_path, _PREMIUM_HTML, _PREMIUM_CSS))
    assert s["verdict"] == "premium-leaning"
    assert s["template_tells"] == []
    assert s["hero_body_ratio"] >= 6        # clamp max 12rem / 1rem body
    assert s["bleed_ratio"] >= 0.5
