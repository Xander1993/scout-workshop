import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import assets_gate as ag


def test_defined_lib_global_passes(tmp_path):
    # A script whose global IS defined after load → gate passes.
    (tmp_path / "gsap.min.js").write_text("window.gsap = {registerPlugin(){}};", encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><h1>ok</h1>'
        '<script src="gsap.min.js" defer></script></body></html>', encoding="utf-8")
    r = ag.check_runtime(tmp_path, port=8231)
    assert r["ok"], r
    assert r["undefined_libs"] == [], r


def test_missing_lib_global_fails(tmp_path):
    # The script loads (200) but never defines window.Lenis → dead motion → fail.
    (tmp_path / "lenis.min.js").write_text("var unrelated = 1;", encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><h1>x</h1>'
        '<script src="lenis.min.js" defer></script></body></html>', encoding="utf-8")
    r = ag.check_runtime(tmp_path, port=8232)
    assert not r["ok"], r
    assert "Lenis" in r["undefined_libs"], r


def test_404_script_fails(tmp_path):
    # Referenced library file does not exist → 404 + undefined global → fail.
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><h1>x</h1>'
        '<script src="split-type.min.js" defer></script></body></html>', encoding="utf-8")
    r = ag.check_runtime(tmp_path, port=8233)
    assert not r["ok"], r
    assert r["failed_resources"], r
    assert "SplitType" in r["undefined_libs"], r


def test_no_external_scripts_passes(tmp_path):
    # A kit with no external libs has nothing to fail on.
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><h1>hi</h1>'
        '<script>console.log("inline ok")</script></body></html>', encoding="utf-8")
    r = ag.check_runtime(tmp_path, port=8234)
    assert r["ok"], r


def test_scroll_trap_fails(tmp_path):
    # Content is far taller than the viewport, but html,body{height:100%} plus
    # overflow-x:hidden on the root pins the document to one viewport so it cannot
    # scroll — the exact "Lenis loaded without its required CSS" failure. Every
    # library global is fine (none referenced here), so only the scroll-reachability
    # check can catch it.
    (tmp_path / "index.html").write_text(
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><style>'
        '*{box-sizing:border-box;margin:0;padding:0}'
        'html,body{height:100%}html,body{overflow-x:hidden}'
        'section{min-height:1200px;display:block}'
        '</style></head><body>'
        '<section>A</section><section>B</section>'
        '<section>C</section><section>D</section>'
        '</body></html>', encoding="utf-8")
    r = ag.check_runtime(tmp_path, port=8235)
    assert r["scroll_broken"], r
    assert not r["ok"], r


def test_at_rest_motion_detected_on_animated_page(tmp_path):
    # A CSS animation that runs on load (no scroll/interaction) → the page visibly
    # changes between two at-rest frames → at_rest_motion True. This is the signal a
    # kinetic-experimental kit MUST satisfy (it must move on load).
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head><meta charset="utf-8"><style>'
        '@keyframes slide{from{transform:translateX(0)}to{transform:translateX(400px)}}'
        '.box{width:300px;height:300px;background:#c0392b;'
        'animation:slide 1s linear infinite alternate}'
        '</style></head><body><div class="box"></div></body></html>', encoding="utf-8")
    r = ag.check_runtime(tmp_path, port=8241)
    assert r["at_rest_motion"] is True, r


def test_static_page_has_no_at_rest_motion(tmp_path):
    # A static page does not change between at-rest frames → at_rest_motion False.
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head><meta charset="utf-8"></head>'
        '<body><h1>static</h1><p>nothing moves here</p></body></html>', encoding="utf-8")
    r = ag.check_runtime(tmp_path, port=8242)
    assert r["at_rest_motion"] is False, r


def test_scrollable_page_passes(tmp_path):
    # Same tall content WITHOUT the height clamp scrolls normally → not flagged
    # (guards against the scroll check false-positiving on a healthy long page).
    (tmp_path / "index.html").write_text(
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><style>'
        '*{box-sizing:border-box;margin:0;padding:0}'
        'html{height:100%}'
        'section{min-height:1200px;display:block}'
        '</style></head><body>'
        '<section>A</section><section>B</section>'
        '<section>C</section><section>D</section>'
        '</body></html>', encoding="utf-8")
    r = ag.check_runtime(tmp_path, port=8236)
    assert not r["scroll_broken"], r
    assert r["ok"], r
