import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import awwwards_render as ar


def _pt(source, rtype, title):
    return {"source": source, "reference_type": rtype, "title": title}


def test_kit_type_reference_filter():
    pool = [_pt("curated", "product_marketing", "airpods"),
            _pt("curated", "studio_site", "namma"),
            _pt("awwwards", "listing_frame", "old"),
            _pt("dribbble", "salon_landing", "beauty")]
    sp = ar.filter_refs(pool, kit_type="single-product")
    assert [p["title"] for p in sp] == ["airpods"]
    ed = ar.filter_refs(pool, kit_type="editorial-studio")
    assert set(p["title"] for p in ed) == {"airpods", "namma"}


def test_art_direction_query_is_not_conversion():
    q = ar.art_direction_query("sun-baked", "single-product").lower()
    assert "monumental" in q and "premium" in q
    assert "cta" not in q and "click-to-call" not in q
