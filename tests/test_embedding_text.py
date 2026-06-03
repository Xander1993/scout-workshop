import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import ingest_daemon


def test_embedding_text_includes_structural_fields():
    fm = {"title": "T", "hero_archetype": "monumental_wordmark",
          "section_topology": ["full_bleed_plate", "manifesto"],
          "motion_signature": ["scroll_pin", "lenis_smooth"],
          "signature_idea": "wordmark dissolves into photo", "techniques": ["a"]}
    text = ingest_daemon.build_embedding_text(fm, "body")
    assert "monumental_wordmark" in text and "full_bleed_plate" in text
    assert "scroll_pin" in text and "wordmark dissolves into photo" in text


def test_embedding_text_survives_malformed_list_items():
    # Reproduces the live crash: a YAML list item that parsed as a dict.
    fm = {"title": "T", "techniques": [{"show-dont-tell": "above the fold is work"}],
          "section_topology": [{"oops": "dict"}]}
    text = ingest_daemon.build_embedding_text(fm, "body")  # must NOT raise
    assert "show-dont-tell" in text
