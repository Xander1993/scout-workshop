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
    assert sig["type_scale_bucket"] == "xl"
    assert sig["sections"] == ["manifesto", "work_grid"]


def test_store_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(dg, "_STORE", tmp_path / "sig.json")
    dg.record({"archetype": "x"}, "restrained-monumental")
    assert len(dg.priors("restrained-monumental")) == 1
    assert dg.priors("other") == []
