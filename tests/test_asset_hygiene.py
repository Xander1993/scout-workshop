import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import asset_hygiene as ah


def _img(p):
    # a 1x1 transparent PNG so a referenced "real" image exists on disk
    p.write_bytes(bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000a49444154789c6300010000050001"))


def test_clean_kit_passes(tmp_path):
    _img(tmp_path / "hero.png")
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><h1>Atelier Voss</h1>'
        '<img src="hero.png" alt="studio"></body></html>', encoding="utf-8")
    r = ah.check_assets(tmp_path)
    assert r["ok"], r
    assert r["violations"] == [], r


def test_unsubstituted_token_fails(tmp_path):
    (tmp_path / "contact.html").write_text(
        '<!doctype html><html><body>'
        '<a href="mailto:studio@{{BRAND}}.studio">write</a></body></html>',
        encoding="utf-8")
    r = ah.check_assets(tmp_path)
    assert not r["ok"], r
    assert any("{{BRAND}}" in v for v in r["violations"]), r


def test_picsum_url_fails(tmp_path):
    (tmp_path / "work.html").write_text(
        '<!doctype html><html><body>'
        '<img src="https://picsum.photos/seed/plate/1800/1100"></body></html>',
        encoding="utf-8")
    r = ah.check_assets(tmp_path)
    assert not r["ok"], r
    assert any("picsum" in v.lower() for v in r["violations"]), r


def test_placeholder_text_svg_file_fails(tmp_path):
    (tmp_path / "plate.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
        '<text x="32" y="48">PLACEHOLDER</text></svg>', encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body>'
        '<img src="plate.svg" alt="proof"></body></html>', encoding="utf-8")
    r = ah.check_assets(tmp_path)
    assert not r["ok"], r
    assert any("plate.svg" in v for v in r["violations"]), r


def test_inline_placeholder_svg_fails(tmp_path):
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><figure>'
        '<svg viewBox="0 0 100 100"><text x="5" y="20">PLACEHOLDER</text></svg>'
        '</figure></body></html>', encoding="utf-8")
    r = ah.check_assets(tmp_path)
    assert not r["ok"], r
    assert any("PLACEHOLDER" in v.upper() for v in r["violations"]), r


def test_all_pages_scanned(tmp_path):
    # a defect on a NON-index page (services) must still fail the kit
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><h1>ok</h1></body></html>', encoding="utf-8")
    (tmp_path / "services.html").write_text(
        '<!doctype html><html><body>'
        '<img src="https://picsum.photos/seed/x/800/600"></body></html>',
        encoding="utf-8")
    r = ah.check_assets(tmp_path)
    assert not r["ok"], r
    assert any("services.html" in v for v in r["violations"]), r


def test_missing_local_image_fails(tmp_path):
    # an <img> pointing at a local file that does not exist on disk is a broken
    # image (browser renders a broken-image icon) — must fail the kit
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body>'
        '<img src="assets/hero.png" alt="studio"></body></html>',
        encoding="utf-8")
    r = ah.check_assets(tmp_path)
    assert not r["ok"], r
    assert any("assets/hero.png" in v and "missing" in v.lower()
               for v in r["violations"]), r


def test_present_local_image_passes(tmp_path):
    # the same reference passes once the file actually exists on disk
    (tmp_path / "assets").mkdir()
    _img(tmp_path / "assets" / "hero.png")
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body>'
        '<img src="assets/hero.png" alt="studio"></body></html>',
        encoding="utf-8")
    r = ah.check_assets(tmp_path)
    assert r["ok"], r


def test_missing_css_background_image_fails(tmp_path):
    # a background-image url() in an external stylesheet pointing at a local file
    # that does not exist on disk is a broken image — must fail the kit. The url()
    # is resolved relative to the CSS file's own directory ("../images/..").
    css = tmp_path / "assets" / "css"
    css.mkdir(parents=True)
    (css / "style.css").write_text(
        ".hero{background-image:url('../images/hero.png');}", encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head>'
        '<link rel="stylesheet" href="assets/css/style.css"></head>'
        '<body><div class="hero"></div></body></html>', encoding="utf-8")
    r = ah.check_assets(tmp_path)
    assert not r["ok"], r
    assert any("hero.png" in v and "missing" in v.lower()
               for v in r["violations"]), r


def test_present_css_background_image_passes(tmp_path):
    # the same reference passes once the file actually exists on disk
    css = tmp_path / "assets" / "css"
    css.mkdir(parents=True)
    (tmp_path / "assets" / "images").mkdir(parents=True)
    _img(tmp_path / "assets" / "images" / "hero.png")
    (css / "style.css").write_text(
        ".hero{background-image:url('../images/hero.png');}", encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><div class="hero"></div></body></html>',
        encoding="utf-8")
    r = ah.check_assets(tmp_path)
    assert r["ok"], r


def test_css_font_url_ignored(tmp_path):
    # a missing non-image url() (e.g. a @font-face .woff2) is out of scope for the
    # image-hygiene gate and must NOT be flagged as a broken image
    css = tmp_path / "assets" / "css"
    css.mkdir(parents=True)
    (css / "style.css").write_text(
        "@font-face{font-family:x;src:url('../fonts/x.woff2');}",
        encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><h1>ok</h1></body></html>', encoding="utf-8")
    r = ah.check_assets(tmp_path)
    assert r["ok"], r


def test_missing_img_srcset_fails(tmp_path):
    # an <img> whose srcset lists a local file missing on disk is a broken image
    _img(tmp_path / "hero.png")
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body>'
        '<img src="hero.png" srcset="hero.png 1x, hero-2x.png 2x" alt="studio">'
        '</body></html>', encoding="utf-8")
    r = ah.check_assets(tmp_path)
    assert not r["ok"], r
    assert any("hero-2x.png" in v and "missing" in v.lower()
               for v in r["violations"]), r


def test_missing_source_srcset_fails(tmp_path):
    # a <picture><source srcset> pointing at a missing local file is broken
    _img(tmp_path / "hero.png")
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><picture>'
        '<source srcset="hero.avif" type="image/avif">'
        '<img src="hero.png" alt="studio"></picture></body></html>',
        encoding="utf-8")
    r = ah.check_assets(tmp_path)
    assert not r["ok"], r
    assert any("hero.avif" in v and "missing" in v.lower()
               for v in r["violations"]), r


def test_present_responsive_images_pass(tmp_path):
    # img srcset + picture source all resolving on disk passes cleanly
    for n in ("hero.png", "hero-2x.png", "hero.avif"):
        _img(tmp_path / n)
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><picture>'
        '<source srcset="hero.avif" type="image/avif">'
        '<img src="hero.png" srcset="hero.png 1x, hero-2x.png 2x" alt="x">'
        '</picture></body></html>', encoding="utf-8")
    r = ah.check_assets(tmp_path)
    assert r["ok"], r


def _placeholder_svg(p):
    p.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
        '<text x="32" y="48">PLACEHOLDER</text></svg>', encoding="utf-8")


def test_placeholder_svg_via_img_srcset_fails(tmp_path):
    # an <img srcset> pointing at an existing-but-PLACEHOLDER svg is a placeholder
    _img(tmp_path / "hero.png")
    _placeholder_svg(tmp_path / "plate.svg")
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body>'
        '<img src="hero.png" srcset="plate.svg 1x" alt="studio">'
        '</body></html>', encoding="utf-8")
    r = ah.check_assets(tmp_path)
    assert not r["ok"], r
    assert any("plate.svg" in v and "PLACEHOLDER" in v.upper()
               for v in r["violations"]), r


def test_placeholder_svg_via_source_fails(tmp_path):
    # a <picture><source srcset> pointing at a PLACEHOLDER svg is a placeholder
    _img(tmp_path / "hero.png")
    _placeholder_svg(tmp_path / "plate.svg")
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><picture>'
        '<source srcset="plate.svg" type="image/svg+xml">'
        '<img src="hero.png" alt="studio"></picture></body></html>',
        encoding="utf-8")
    r = ah.check_assets(tmp_path)
    assert not r["ok"], r
    assert any("plate.svg" in v and "PLACEHOLDER" in v.upper()
               for v in r["violations"]), r


def test_placeholder_svg_via_css_url_fails(tmp_path):
    # a background-image url() in an external stylesheet pointing at an existing
    # PLACEHOLDER svg is a placeholder image — must fail the kit
    css = tmp_path / "assets" / "css"
    css.mkdir(parents=True)
    (tmp_path / "assets" / "images").mkdir(parents=True)
    _placeholder_svg(tmp_path / "assets" / "images" / "plate.svg")
    (css / "style.css").write_text(
        ".hero{background-image:url('../images/plate.svg');}", encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head>'
        '<link rel="stylesheet" href="assets/css/style.css"></head>'
        '<body><div class="hero"></div></body></html>', encoding="utf-8")
    r = ah.check_assets(tmp_path)
    assert not r["ok"], r
    assert any("plate.svg" in v and "PLACEHOLDER" in v.upper()
               for v in r["violations"]), r


def test_placeholder_svg_via_css_mask_and_clip_path_fails(tmp_path):
    # a PLACEHOLDER svg referenced via mask-image / clip-path url() in an external
    # stylesheet (NOT just background-image) must also fail the kit — the url()
    # disk/placeholder check is property-agnostic, so every CSS url() image
    # channel is covered, not only background-image. Locks that coverage.
    css = tmp_path / "assets" / "css"
    css.mkdir(parents=True)
    (tmp_path / "assets" / "images").mkdir(parents=True)
    _placeholder_svg(tmp_path / "assets" / "images" / "mask.svg")
    (css / "style.css").write_text(
        ".hero{-webkit-mask-image:url('../images/mask.svg');"
        "mask-image:url('../images/mask.svg');"
        "clip-path:url('../images/mask.svg');}", encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head>'
        '<link rel="stylesheet" href="assets/css/style.css"></head>'
        '<body><div class="hero"></div></body></html>', encoding="utf-8")
    r = ah.check_assets(tmp_path)
    assert not r["ok"], r
    assert any("mask.svg" in v and "PLACEHOLDER" in v.upper()
               for v in r["violations"]), r


def test_present_nonplaceholder_svg_via_channels_passes(tmp_path):
    # a real (non-PLACEHOLDER) svg referenced via srcset/source/css passes
    css = tmp_path / "assets" / "css"
    css.mkdir(parents=True)
    (tmp_path / "assets" / "images").mkdir(parents=True)
    real = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            '<circle cx="5" cy="5" r="4"/></svg>')
    (tmp_path / "icon.svg").write_text(real, encoding="utf-8")
    (tmp_path / "assets" / "images" / "bg.svg").write_text(real, encoding="utf-8")
    (css / "style.css").write_text(
        ".hero{background-image:url('../images/bg.svg');}", encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head>'
        '<link rel="stylesheet" href="assets/css/style.css"></head>'
        '<body><picture><source srcset="icon.svg" type="image/svg+xml">'
        '<img src="icon.svg" srcset="icon.svg 1x" alt="x"></picture>'
        '<div class="hero"></div></body></html>', encoding="utf-8")
    r = ah.check_assets(tmp_path)
    assert r["ok"], r


def test_picsum_url_in_external_css_fails(tmp_path):
    # a picsum.photos background-image in an EXTERNAL stylesheet is a placeholder
    # image URL — the same defect the HTML scan catches, must also fail in *.css
    css = tmp_path / "assets" / "css"
    css.mkdir(parents=True)
    (css / "style.css").write_text(
        ".hero{background-image:url('https://picsum.photos/seed/x/1800/1100');}",
        encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head>'
        '<link rel="stylesheet" href="assets/css/style.css"></head>'
        '<body><div class="hero"></div></body></html>', encoding="utf-8")
    r = ah.check_assets(tmp_path)
    assert not r["ok"], r
    assert any("picsum" in v.lower() and "style.css" in v
               for v in r["violations"]), r


def test_unsubstituted_token_in_external_css_fails(tmp_path):
    # an unsubstituted template token left in an EXTERNAL stylesheet (e.g. a
    # content:"{{BRAND}}" or a token in a url()) must fail like the HTML scan
    css = tmp_path / "assets" / "css"
    css.mkdir(parents=True)
    (css / "style.css").write_text(
        '.brand::after{content:"{{BRAND}}";}', encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head>'
        '<link rel="stylesheet" href="assets/css/style.css"></head>'
        '<body><span class="brand"></span></body></html>', encoding="utf-8")
    r = ah.check_assets(tmp_path)
    assert not r["ok"], r
    assert any("{{BRAND}}" in v and "style.css" in v
               for v in r["violations"]), r


def test_clean_external_css_passes(tmp_path):
    # a normal external stylesheet with no picsum/token strings passes cleanly
    css = tmp_path / "assets" / "css"
    css.mkdir(parents=True)
    (css / "style.css").write_text(
        ".hero{color:#111;background:#faf6ef;}", encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head>'
        '<link rel="stylesheet" href="assets/css/style.css"></head>'
        '<body><div class="hero"></div></body></html>', encoding="utf-8")
    r = ah.check_assets(tmp_path)
    assert r["ok"], r


def test_data_uri_and_remote_real_images_pass(tmp_path):
    # data: URIs and a normal remote https image (not picsum) are not placeholders
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body>'
        '<img src="data:image/png;base64,iVBORw0KGgo=">'
        '<img src="https://images.example.com/hero.jpg"></body></html>',
        encoding="utf-8")
    r = ah.check_assets(tmp_path)
    assert r["ok"], r
