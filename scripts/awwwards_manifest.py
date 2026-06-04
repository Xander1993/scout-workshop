"""Parse + validate the section_manifest YAML out of an awwwards brief.md.

Phase 1a emits the manifest as a ```yaml fence at the top of brief.md but never
parses it; every Phase 1b gate (diversity signature, density, craft) needs it as
a validated dict. This module is that missing input. Hard-fail (ManifestError)
if absent/invalid — the gates depend on it.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from structural_schema import HERO_ARCHETYPES, SECTION_TYPES  # type: ignore


class ManifestError(ValueError):
    pass


# First ```yaml / ```yml fence (NOT the later ```css palette fence).
_YAML_FENCE = re.compile(r"```ya?ml\s*\n(.*?)\n```", re.DOTALL)


def parse_manifest(brief_text: str) -> dict:
    """Extract + load the section_manifest. Returns {hero_archetype, sections, signature_move}."""
    import yaml
    m = _YAML_FENCE.search(brief_text)
    if not m:
        raise ManifestError("no ```yaml section_manifest fence found in brief")
    try:
        data = yaml.safe_load(m.group(1))
    except Exception as e:  # noqa: BLE001
        raise ManifestError(f"section_manifest YAML parse failed: {e}") from e
    if isinstance(data, dict) and "section_manifest" in data:
        data = data["section_manifest"]
    if not isinstance(data, dict):
        raise ManifestError("section_manifest is not a mapping")
    return {
        "hero_archetype": data.get("hero_archetype"),
        "sections": data.get("sections") or [],
        "signature_move": data.get("signature_move", ""),
    }


def validate(m: dict) -> list[str]:
    """Return a list of problems; empty == valid."""
    errs: list[str] = []
    if m.get("hero_archetype") not in HERO_ARCHETYPES:
        errs.append(f"hero_archetype {m.get('hero_archetype')!r} not in {HERO_ARCHETYPES}")
    sections = m.get("sections")
    if not isinstance(sections, list) or not sections:
        errs.append("sections must be a non-empty list")
    else:
        bad = [s for s in sections if s not in SECTION_TYPES]
        if bad:
            errs.append(f"unknown section types: {bad}")
    return errs
