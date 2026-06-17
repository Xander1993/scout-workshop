import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import diversity_gate as dg


def test_damerau_levenshtein():
    assert dg._dl(["a", "b", "c"], ["a", "b", "c"]) == 0
    assert dg._dl(["a", "b"], ["b", "a"]) == 1      # transposition
    assert dg._dl(["a", "b", "c"], ["a", "c"]) == 1  # deletion


def test_distance_and_repeat():
    s1 = {"archetype": "monumental_wordmark", "sections": ["a", "b", "c"],
          "type_scale_bucket": "xl", "concept_bucket": "x"}
    assert dg.distance(s1, dict(s1)) == 0.0
    assert dg.is_repeat(s1, [dict(s1)])
    s3 = {"archetype": "product_canvas_pinned", "sections": ["p", "q"],
          "type_scale_bucket": "l", "concept_bucket": "y"}
    assert dg.distance(s1, s3) >= 0.35          # different archetype clears threshold
    assert not dg.is_repeat(s1, [s3])
    assert not dg.is_repeat(s1, [])             # first run never repeats


def test_signature_buckets():
    m = {"hero_archetype": "monumental_wordmark", "sections": ["manifesto", "work_grid"]}
    sig = dg.signature(m, {"hero_scale_ratio": 77.3}, {"hook_name": "Carved Wordmark"})
    assert sig["archetype"] == "monumental_wordmark"
    assert sig["type_scale_bucket"] == "xl3"
    assert sig["sections"] == ["manifesto", "work_grid"]


def test_xl_subbuckets_discriminate():
    m = {"hero_archetype": "x", "sections": ["a"]}

    def tsb(hsr):
        return dg.signature(m, {"hero_scale_ratio": hsr}, {})["type_scale_bucket"]

    # The old single "xl" (hsr>=12) is now sub-banded so monumental kits at very
    # different scales are not treated as the same type-scale.
    assert tsb(13) == "xl1"
    assert tsb(24) == "xl2"
    assert tsb(50) == "xl3"
    assert tsb(13) != tsb(50)
    # two kits in the same band still collapse
    assert tsb(13) == tsb(18)
    # lower bands unchanged
    assert tsb(8) == "l"
    assert tsb(5) == "m"
    assert tsb(2) == "s"


def test_semantic_concept_bucket():
    m = {"hero_archetype": "x", "sections": ["a"]}

    def cb(hook):
        return dg.signature(m, {"hero_scale_ratio": 13}, {"hook_name": hook})["concept_bucket"]

    # Trivial wording variants of the SAME concept collapse to one bucket
    # (case, punctuation, word order, stopwords) — the old exact-string hash
    # treated these as distinct.
    base = cb("Carved Wordmark")
    assert cb("carved wordmark.") == base
    assert cb("Wordmark, carved") == base
    assert cb("The Carved Wordmark") == base
    # genuinely different concepts stay distinct
    assert cb("Liquid Mercury Scroll") != base


def test_store_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(dg, "_STORE", tmp_path / "sig.json")
    dg.record({"archetype": "x"}, "restrained-monumental")
    assert len(dg.priors("restrained-monumental")) == 1
    assert dg.priors("other") == []
