import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import scout_lib


def test_payload_includes_structural_fields_when_present():
    fm = {"id": "x", "title": "T", "hero_archetype": "monumental_wordmark",
          "section_topology": ["full_bleed_plate"], "motion_signature": ["scroll_pin"],
          "signature_idea": "the idea"}
    p = scout_lib.frontmatter_to_payload(fm)
    assert p["hero_archetype"] == "monumental_wordmark"
    assert p["section_topology"] == ["full_bleed_plate"]
    assert p["motion_signature"] == ["scroll_pin"]
    assert p["signature_idea"] == "the idea"


def test_payload_omits_structural_fields_when_absent():
    assert "hero_archetype" not in scout_lib.frontmatter_to_payload({"id": "x", "title": "T"})
