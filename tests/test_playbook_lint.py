import pathlib, re

PLAYBOOK = (pathlib.Path(__file__).resolve().parent.parent / "skills" / "scout-playbook.md").read_text()
WORKSHOP_PLAYBOOK = (pathlib.Path(__file__).resolve().parent.parent / "skills" / "workshop-playbook.md").read_text()


def test_craft_prompt_drops_placeholder_flatness_exemption():
    # Images are now substituted for real ones BEFORE the craft gate (asset-hygiene
    # gate), so the judge must no longer be told to ignore placeholder-image flatness.
    assert "ignore their flatness" not in WORKSHOP_PLAYBOOK
    assert "images may be SVG placeholders" not in WORKSHOP_PLAYBOOK


def test_awwwards_dereference_directive_present():
    assert "Visit site" in PLAYBOOK
    assert "dereference" in PLAYBOOK.lower()
    assert "do not capture the awwwards.com listing" in PLAYBOOK.lower()


def test_fullpage_screenshot_enabled():
    # quote-agnostic: matches both \"fullPage\": true and "fullPage": true
    assert re.search(r'fullPage\\?"\s*:\s*true', PLAYBOOK)
    assert not re.search(r'fullPage\\?"\s*:\s*false', PLAYBOOK)


def test_playbook_declares_structural_fields():
    for f in ("hero_archetype", "section_topology", "motion_signature", "signature_idea"):
        assert f in PLAYBOOK, f"playbook missing {f}"


def test_playbook_has_diversified_sources():
    pl = PLAYBOOK.lower()
    assert "godly" in pl and "product page" in pl
    assert "across archetypes" in pl or "spread" in pl
