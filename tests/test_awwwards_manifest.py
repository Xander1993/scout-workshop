import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import awwwards_manifest as am
import pytest

# Mirrors the real brief.md format (a ```yaml section_manifest fence, then a ```css palette fence).
_REAL_BRIEF = """```yaml
section_manifest:
  hero_archetype: monumental_wordmark
  sections: [monumental_wordmark, full_bleed_plate, manifesto, work_grid, studio_statement]
  signature_move: a pinned terracotta wordmark whose counters become a window onto a clay reel
```
# Brief — warm-earth / editorial-studio
## Palette
```css
:root { --color-bg: #F0E9D6; }
```
"""


def test_parses_real_format_and_grabs_yaml_not_css():
    m = am.parse_manifest(_REAL_BRIEF)
    assert m["hero_archetype"] == "monumental_wordmark"
    assert m["sections"][0] == "monumental_wordmark" and "work_grid" in m["sections"]
    assert "clay reel" in m["signature_move"]
    assert am.validate(m) == []


def test_missing_fence_raises():
    with pytest.raises(am.ManifestError):
        am.parse_manifest("# Brief with no yaml fence\njust prose")


def test_validate_flags_bad_enum():
    bad = {"hero_archetype": "banana", "sections": ["not_a_type"], "signature_move": "x"}
    errs = am.validate(bad)
    assert any("hero_archetype" in e for e in errs)
    assert any("unknown section types" in e for e in errs)
