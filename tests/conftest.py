"""Shared fixtures for v1.4 quality-floor tests.

Uses committed fixture runs (tests/fixtures/runs/) rather than live run dirs
so tests are reproducible on any machine without the full run history.
"""
from __future__ import annotations

from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "runs"

# Known-good run: May 15 modern-minimal landed at probe-5 quality
GOOD_RUN_SLUG = "2026-05-15T11-25-22Z-agency-modern-minimal"
# Known-bad run: May 17 had ~700px vertical void; thin services articles
BAD_RUN_SLUG = "2026-05-17T01-00-02Z-agency-restrained-luxury-warm"
# Validated awwwards-tier reference
PROBE5_SLUG = "2026-05-10T22-18-59Z-awwwards-awwwards-probe-5"


@pytest.fixture
def good_run_dir() -> Path:
    """Path to May 15 modern-minimal fixture (passed quality bar)."""
    p = FIXTURES_DIR / GOOD_RUN_SLUG
    assert p.exists(), f"missing fixture: {p}"
    return p


@pytest.fixture
def bad_run_dir() -> Path:
    """Path to May 17 restrained-luxury-warm fixture (failed quality bar)."""
    p = FIXTURES_DIR / BAD_RUN_SLUG
    assert p.exists(), f"missing fixture: {p}"
    return p


@pytest.fixture
def probe5_run_dir() -> Path:
    """Path to probe-5 awwwards fixture (validated reference)."""
    p = FIXTURES_DIR / PROBE5_SLUG
    assert p.exists(), f"missing fixture: {p}"
    return p


@pytest.fixture
def sample_manifest_yaml() -> str:
    """YAML manifest snippet a well-formed brief would emit."""
    return """---
section_manifest:
  index:
    - {id: hero, type: hero, required_elements: [h1, subhead, primary_cta, image]}
    - {id: trust, type: stats_row, required_elements: [eyebrow, stat_count_min_3]}
    - {id: services, type: case_grid, min_items: 3, item_requires: [image, h3, body_min_80c]}
    - {id: portfolio, type: case_grid, min_items: 3, item_requires: [image, h3, year]}
    - {id: footer_callout, type: callout, required_elements: [h2, body, secondary_cta]}
    - {id: wordmark, type: showpiece_wordmark, required_elements: [brand_token]}
  services: []
  contacts: []
---

## Aesthetic
Stub aesthetic body here.
"""


@pytest.fixture
def thin_manifest_yaml() -> str:
    """YAML manifest with only one case_grid — should fail Gate A."""
    return """---
section_manifest:
  index:
    - {id: hero, type: hero, required_elements: [h1, subhead, primary_cta]}
    - {id: services, type: case_grid, min_items: 3, item_requires: [image, h3, body_min_80c]}
  services: []
  contacts: []
---

## Aesthetic
Stub.
"""


@pytest.fixture
def tmp_run_dir(tmp_path) -> Path:
    """Empty temp dir that mimics a workshop run dir layout."""
    (tmp_path / "kit").mkdir()
    (tmp_path / "kit" / "screenshots").mkdir()
    (tmp_path / "kit" / "assets" / "images").mkdir(parents=True)
    return tmp_path
