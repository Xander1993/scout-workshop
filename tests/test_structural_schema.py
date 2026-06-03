import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import structural_schema as ss


def test_enums_present_and_typed():
    assert "monumental_wordmark" in ss.HERO_ARCHETYPES
    assert "product_canvas_pinned" in ss.HERO_ARCHETYPES
    assert "full_bleed_plate" in ss.SECTION_TYPES
    assert "scroll_pin" in ss.MOTION_SIGNATURES
    assert ss.STRUCTURAL_FIELDS == ("hero_archetype", "section_topology", "motion_signature", "signature_idea")


def test_validate_accepts_good_and_flags_bad():
    good = {"hero_archetype": "monumental_wordmark",
            "section_topology": ["full_bleed_plate", "manifesto"],
            "motion_signature": ["scroll_pin", "lenis_smooth"],
            "signature_idea": "wordmark dissolves into the photo on scroll"}
    assert ss.validate_structural(good) == []
    bad = {"hero_archetype": "banana", "section_topology": "not-a-list",
           "motion_signature": ["scroll_pin"], "signature_idea": ""}
    errs = ss.validate_structural(bad)
    assert any("hero_archetype" in e for e in errs)
    assert any("section_topology" in e for e in errs)
    assert any("signature_idea" in e for e in errs)
