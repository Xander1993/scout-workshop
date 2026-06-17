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


def _ref(hero, topo, sig=""):
    return {"hero_archetype": hero, "section_topology": topo, "signature_idea": sig}


def test_structural_tokens_excludes_palette():
    r = _ref("monumental_wordmark", ["hero", "ledger"], "tide ledger")
    toks = ar.structural_tokens({**r, "palette": {"accent": "#FF0000"}})
    assert "hero:monumental_wordmark" in toks
    assert {"sec:hero", "sec:ledger"} <= toks
    assert {"sig:tide", "sig:ledger"} <= toks
    assert not any(t.startswith("palette") or "#" in t for t in toks)


def test_mmr_first_pick_is_most_relevant():
    a = _ref("split_editorial", ["a"], "alpha")
    b = _ref("monumental_wordmark", ["b"], "beta")
    out = ar.mmr_select([(a, 0.4), (b, 0.9)], k=1)
    assert out == [b]


def test_mmr_dedups_structural_near_duplicates():
    # Three refs: top two are structurally identical, the third is distinct but
    # slightly lower relevance. MMR must surface the distinct ref over the dup.
    dup1 = {**_ref("monumental_wordmark", ["hero", "ledger", "grid"], "tide"), "title": "one"}
    dup2 = {**_ref("monumental_wordmark", ["hero", "ledger", "grid"], "tide"), "title": "two"}
    diff = {**_ref("split_editorial", ["hero", "manifesto"], "ember"), "title": "three"}
    out = ar.mmr_select([(dup1, 0.95), (dup2, 0.92), (diff, 0.80)], k=2)
    assert out[0] is dup1            # most relevant first
    assert diff in out               # diverse pick beats the near-duplicate
    assert dup2 not in out           # structural near-duplicate suppressed


def test_mmr_respects_k_and_empty():
    assert ar.mmr_select([], k=4) == []
    a = _ref("a", ["x"], "one")
    b = _ref("b", ["y"], "two")
    c = _ref("c", ["z"], "three")
    out = ar.mmr_select([(a, 0.9), (b, 0.8), (c, 0.7)], k=2)
    assert len(out) == 2 and a in out
