import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import awwwards_render as ar


def _pt(source, rtype, title, hero=None):
    return {"source": source, "reference_type": rtype, "title": title,
            "hero_archetype": hero}


def test_kit_type_reference_filter():
    pool = [_pt("curated", "product_marketing", "airpods", "product_canvas_pinned"),
            _pt("curated", "studio_site", "namma", "monumental_wordmark"),
            _pt("awwwards", "listing_frame", "old", "monumental_wordmark"),
            _pt("dribbble", "salon_landing", "beauty", "full_bleed_photo_hero")]
    sp = ar.filter_refs(pool, kit_type="single-product")
    assert [p["title"] for p in sp] == ["airpods"]
    ed = ar.filter_refs(pool, kit_type="editorial-studio")
    assert set(p["title"] for p in ed) == {"namma"}  # product-led airpods excluded


def test_single_product_excludes_wordmark_hero():
    # A product_marketing site that is wordmark-led (Marvell) must NOT leak into
    # the single-product pool and steer its hero into an editorial wordmark.
    pool = [_pt("curated", "product_marketing", "marvell", "monumental_wordmark"),
            _pt("curated", "product_marketing", "apple-home", "full_bleed_photo_hero")]
    assert [p["title"] for p in ar.filter_refs(pool, kit_type="single-product")] == ["apple-home"]
    # ...but the wordmark site is still valid for editorial-studio.
    assert [p["title"] for p in ar.filter_refs(pool, kit_type="editorial-studio")] == ["marvell"]


def test_art_direction_query_is_not_conversion():
    q = ar.art_direction_query("sun-baked", "single-product").lower()
    assert "monumental" in q and "premium" in q
    assert "cta" not in q and "click-to-call" not in q
