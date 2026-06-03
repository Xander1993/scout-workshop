import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import structural_schema as ss

PLAYBOOK = (pathlib.Path(__file__).resolve().parent.parent / "skills" / "scout-playbook.md").read_text()


def test_every_enum_value_is_offered_in_playbook():
    missing = [v for group in (ss.HERO_ARCHETYPES, ss.SECTION_TYPES, ss.MOTION_SIGNATURES)
               for v in group if v not in PLAYBOOK]
    assert missing == [], f"enum values not in playbook (validator would reject scout output): {missing}"
