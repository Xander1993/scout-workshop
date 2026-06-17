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


def test_pinned_runway_not_counted_as_void(tmp_path):
    # A pinned-hero scroll runway: the hero is position:fixed inside a tall [data-pin]
    # section the page scrolls through. That ~3000px is intentional scroll-distance,
    # not dead space. The gap from the pinned block to the next section must NOT read
    # as a void once we subtract the [data-pin] overlap.
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body>'
        '<section data-pin style="height:3000px;position:relative">'
        '  <h1 style="position:fixed;top:40px;font-size:120px">Cast a longer shadow</h1>'
        '</section>'
        '<section><p>The shadow resolves at last, far below the hero runway.</p></section>'
        '</body></html>', encoding="utf-8")
    m = rm.render_metrics(tmp_path)
    assert m["max_vertical_void_px"] < 800, m


def test_real_empty_section_still_flagged(tmp_path):
    # Same ~3000px gap but with NO pin marker — this is a genuinely sparse/broken
    # page. The gate must still measure it well past the 2400px ceiling.
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body>'
        '<section><p>Top of page.</p></section>'
        '<section style="height:3000px"></section>'
        '<section><p>Bottom of page, after a huge empty plate.</p></section>'
        '</body></html>', encoding="utf-8")
    m = rm.render_metrics(tmp_path)
    assert m["max_vertical_void_px"] > 2400, m


def test_proportional_void_ratio_and_low_ink_on_sparse_page(tmp_path):
    # A page that is mostly empty: two short lines straddling a 3500px blank band.
    # The proportional void RATIO (sum-of-gaps / page_height) must read near 1.0 and
    # the screenshot ink-coverage must read near 0 — both well past their gate floors.
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body style="margin:0;background:#fff">'
        '<p>Just one short line at the very top.</p>'
        '<div style="height:3500px"></div>'
        '<p>And one short line far below the void.</p>'
        '</body></html>', encoding="utf-8")
    m = rm.render_metrics(tmp_path)
    assert m["void_ratio"] > 0.60, m
    assert m["ink_coverage"] < 0.05, m


def test_oversized_hero_flagged_by_vh_ceiling(tmp_path):
    # A headline several screens tall (2200px at a 900px viewport ≈ 2.4vh) overflows
    # the screen — a broken monumental wordmark. The uncapped hero_vh_ratio must catch
    # it (>2.0), where the one-sided hero_scale_ratio FLOOR never could.
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body style="margin:0;background:#fff">'
        '<h1 style="height:2200px;font-size:200px;margin:0;line-height:1">Big</h1>'
        '<p>tail copy below the monstrous wordmark.</p>'
        '</body></html>', encoding="utf-8")
    m = rm.render_metrics(tmp_path)
    assert m["hero_vh_ratio"] > 2.0, m


def test_render_metrics_all_takes_worst_case(tmp_path):
    # A clean index plus a sparse secondary page: render_metrics_all must surface the
    # WORST density across every page/viewport, so an empty secondary page cannot hide.
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body style="margin:0;background:#fff">'
        '<h1 style="font-size:120px;margin:0">Studio Vela</h1>'
        '<p>First paragraph of real body copy on the landing page.</p>'
        '<p>Second paragraph keeps the page content-driven and dense.</p>'
        '<p>Third paragraph, no oversized empty bands here at all.</p>'
        '</body></html>', encoding="utf-8")
    (tmp_path / "about.html").write_text(
        '<!doctype html><html><body style="margin:0;background:#fff">'
        '<p>Lonely top line.</p><div style="height:3500px"></div>'
        '<p>Lonely bottom line.</p></body></html>', encoding="utf-8")
    m = rm.render_metrics_all(tmp_path)
    assert "about.html" in m["pages_measured"] and "index.html" in m["pages_measured"], m
    assert m["void_ratio"] > 0.60, m          # worst (about.html) wins
    assert m["ink_coverage"] < 0.05, m        # worst (about.html) wins
    assert m["hero_scale_ratio"] >= 4, m      # base stays anchored to index @ desktop


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
