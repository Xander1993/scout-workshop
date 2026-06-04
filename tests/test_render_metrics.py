import sys, pathlib, pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import render_metrics as rm

RUNS = pathlib.Path("/opt/scout-workshop/workshop/runs")


def _kit(glob):
    hits = sorted(RUNS.glob(glob))
    if not hits:
        pytest.skip(f"no real kit matching {glob}")
    return hits[-1]


def test_editorial_kit_passes_hero_and_tells():
    # The Rev-1 regression: the editorial kit's monumental wordmark is an SVG
    # <text>, not <h1>. Bbox-based hero must read it as monumental (>=4x), and
    # the premium kit must carry NO template tells.
    m = rm.render_metrics(_kit("*editorial-studio*/kit"))
    assert m["hero_scale_ratio"] >= 4, m
    assert m["template_tells"] == [], m


def test_single_product_kit_no_tells_and_real_hero():
    m = rm.render_metrics(_kit("*single-product*/kit"))
    assert m["template_tells"] == [], m
    assert m["hero_scale_ratio"] >= 3, m


def test_planted_generic_tells_fire(tmp_path):
    # Hyphenated conventional class names (service-card / cta-button) are the
    # NATURAL drift of our own generator. Exact-token matching used to miss them;
    # substring matching must catch them. This is the "gate has teeth" proof.
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><section>'
        '<div class="service-card">a</div><div class="service-card">b</div>'
        '<div class="feature-card">c</div>'
        '<a class="cta-button" href="#">Buy</a><a class="cta-button" href="#">Get</a>'
        '<a href="tel:+1">call</a>'
        '<div class="trust-badge">x</div>'
        '</section></body></html>', encoding="utf-8")
    m = rm.render_metrics(tmp_path)
    assert "card-grid" in m["template_tells"], m
    assert "repeated-cta" in m["template_tells"], m
    assert "click-to-call" in m["template_tells"], m
    assert "trust/badge" in m["template_tells"], m
