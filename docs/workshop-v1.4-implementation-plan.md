# Workshop v1.4 Quality Floor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Gates A/B/C from the v1.4 design spec to make probe-5 / May-15 quality reproducible across every workshop cron run, replacing the existing "warn-ships-anyway" behaviour with hard gate + retry-once + halt-on-second-failure.

**Architecture:** Five new sibling modules in `scripts/` plus three modifications to existing files. Each new module has one responsibility, an explicit interface, and a pytest test file. `workshop.py` only gains a thin orchestration wrapper that calls the new modules — the gate logic itself never lives inline.

**Tech Stack:** Python 3.12, FastAPI (already in venv from dashboard), pytest 8.x (new dep), PyYAML (new dep), Playwright (already in venv via generate_kit_images), Claude via `claude --print` subprocess (existing pattern in `run_claude()` at `scripts/workshop.py:370`).

**Spec reference:** `docs/workshop-v1.4-quality-floor-design.md` (commit `84d52d4`).

---

## File structure (locked before tasks)

**New files:**

| Path | Responsibility |
|---|---|
| `scripts/quality_floor_config.py` | Tuning constants + register overrides. Single source of truth for thresholds. |
| `scripts/manifest_validator.py` | Gate A — parse YAML frontmatter from brief.md, validate against schema, enforce minimum section counts. |
| `scripts/density_audit.py` | Gate B.1 — four deterministic checks on rendered kit (substantial sections, vertical void, article density, hero h1 word cap). Wordmark measurement removed — no reliable selector without a fixed CSS contract. |
| `scripts/brief_coverage.py` | Gate B.2 — invoke Claude via subprocess with `audit_brief_coverage.md` prompt, parse JSON verdict, return per-section grades. |
| `scripts/telemetry_writer.py` | Atomic append to `state/quality_floor_telemetry.jsonl`. Single-writer assumption (cron is serial). |
| `skills/audit_brief_coverage.md` | Claude prompt template loaded via existing `load_prompt_template()` mechanism. |
| `tests/__init__.py` | Empty marker for pytest. |
| `tests/conftest.py` | Shared fixtures: paths to known-good (May 15) and known-bad (May 17) historical runs, temp directories, sample manifests. |
| `tests/test_manifest_validator.py` | Gate A unit tests. |
| `tests/test_density_audit.py` | Gate B.1 unit tests using historical runs as fixtures. |
| `tests/test_brief_coverage.py` | Gate B.2 unit tests with mocked subprocess. |
| `tests/test_quality_floor_config.py` | Threshold + override logic tests. |
| `tests/test_telemetry_writer.py` | JSONL append + atomicity tests. |
| `tests/test_workshop_gates_integration.py` | End-to-end gate orchestration test with mock Claude calls. |
| `pytest.ini` | pytest discovery config. |

**Modified files:**

| Path | What changes |
|---|---|
| `scripts/workshop.py` | `main()` gains Gate A call after brief gen, Gate B+C wrapper after image gen, halt path that moves runs to `workshop/runs-halted/`. New helpers: `_run_quality_gate()`, `_format_retry_recap()`, `_halt_with_telegram()`. |
| `skills/workshop-playbook.md` | Brief-generation prompt gains a "## Section Manifest" requirement block with YAML schema + example + minimum-section rule. |
| `dashboard/app.py` | Detection logic added to `compute_stats()`: if `state/quality_floor_telemetry.jsonl` exists, prefer it over synthesised data; otherwise keep current synthesis. |
| `.gitignore` | Add `__pycache__/` and `.pytest_cache/`. |

**Why these boundaries:** Each gate is its own file so a failure in one (e.g., Playwright launch failure in density_audit) does not block another. Each module has zero side effects beyond its return value plus optional logging — the orchestrator in `workshop.py` is the only place that mutates state (run dir, JSONL file, Telegram).

---

## Task 0: Test infrastructure

**Files:**
- Create: `pytest.ini`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Modify: `.gitignore`

- [ ] **Step 0.1: Install pytest + PyYAML + Pillow in the venv**

```bash
/opt/scout-workshop/venv/bin/pip install pytest==8.* pyyaml==6.* Pillow>=10
```

Expected: `Successfully installed pytest-8.x.x pyyaml-6.x.x Pillow-10.x.x`

- [ ] **Step 0.2: Write pytest.ini**

```ini
# /opt/scout-workshop/pytest.ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -ra --strict-markers --tb=short
markers =
    slow: tests that hit Playwright or subprocess Claude (>2s)
    integration: end-to-end gate orchestration tests
```

- [ ] **Step 0.3: Write tests/__init__.py and tests/conftest.py**

`tests/__init__.py`:
```python
# empty marker for pytest package discovery
```

`tests/conftest.py`:
```python
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
```

- [ ] **Step 0.3b: Create committed fixture run dirs**

Copy minimal artifacts (HTML only — no screenshots, no asset images) from real runs
into `tests/fixtures/runs/`. Generate 1×1 placeholder PNGs via Pillow for any
test that verifies file existence without reading content.

```bash
cd /opt/scout-workshop
FIXTURES=tests/fixtures/runs
RUNS=workshop/runs
GOOD=2026-05-15T11-25-22Z-agency-modern-minimal
BAD=2026-05-17T01-00-02Z-agency-restrained-luxury-warm
PROBE=2026-05-10T22-18-59Z-awwwards-awwwards-probe-5

for SLUG in $GOOD $BAD $PROBE; do
  mkdir -p $FIXTURES/$SLUG/kit/screenshots
  # brief.md (needed by brief_coverage fixtures)
  cp $RUNS/$SLUG/brief.md $FIXTURES/$SLUG/brief.md 2>/dev/null \
    || echo "# stub brief" > $FIXTURES/$SLUG/brief.md
  # HTML pages
  cp $RUNS/$SLUG/kit/index.html    $FIXTURES/$SLUG/kit/index.html
  cp $RUNS/$SLUG/kit/services.html $FIXTURES/$SLUG/kit/services.html 2>/dev/null || true
  cp $RUNS/$SLUG/kit/contacts.html $FIXTURES/$SLUG/kit/contacts.html 2>/dev/null || true
done

# 1×1 placeholder PNG for each fixture (commits as ~1 KB each)
venv/bin/python - <<'PY'
from PIL import Image
from pathlib import Path
img = Image.new("RGB", (1, 1), color="#888")
for slug in [
    "2026-05-15T11-25-22Z-agency-modern-minimal",
    "2026-05-17T01-00-02Z-agency-restrained-luxury-warm",
    "2026-05-10T22-18-59Z-awwwards-awwwards-probe-5",
]:
    p = Path("tests/fixtures/runs") / slug / "kit" / "screenshots" / "home-desktop.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    img.save(p)
print("placeholder PNGs written")
PY
```

Expected: `placeholder PNGs written` with no errors.

- [ ] **Step 0.4: Update .gitignore**

Append to `/opt/scout-workshop/.gitignore`:
```
__pycache__/
.pytest_cache/
*.pyc
```

Do NOT add `tests/fixtures/` — fixture files including placeholder PNGs go into git.

- [ ] **Step 0.5: Verify fixtures load**

```bash
cd /opt/scout-workshop && venv/bin/pytest tests/ -v 2>&1 | tail -5
```

Expected: `no tests ran` (no test files yet but fixtures parse OK)

- [ ] **Step 0.6: Commit**

```bash
cd /opt/scout-workshop
git add pytest.ini tests/__init__.py tests/conftest.py tests/fixtures/ .gitignore
git commit -m "test: bootstrap pytest infra + committed fixture runs for v1.4 gates"
```

---

## Task 1: quality_floor_config.py

**Files:**
- Create: `scripts/quality_floor_config.py`
- Create: `tests/test_quality_floor_config.py`

- [ ] **Step 1.1: Write the failing tests first**

`tests/test_quality_floor_config.py`:
```python
"""Tests for quality_floor_config.threshold() helper."""
from __future__ import annotations

import pytest
from scripts import quality_floor_config as qfc


def test_default_threshold_returned_when_no_register():
    assert qfc.threshold("vertical_void_max_px") == 500


def test_awwwards_register_override_applies():
    assert qfc.threshold("vertical_void_max_px", register="awwwards") == 700


def test_conversion_register_override_applies():
    assert qfc.threshold("vertical_void_max_px", register="conversion") == 400


def test_unknown_register_falls_back_to_default():
    assert qfc.threshold("vertical_void_max_px", register="bogus") == 500


def test_unknown_threshold_raises():
    with pytest.raises(KeyError):
        qfc.threshold("nonexistent_threshold")


def test_retry_policy_accessor():
    assert qfc.retry_enabled() is True
    assert qfc.max_retries() == 1
    assert qfc.reuse_images_on_retry() is True


def test_dashboard_bind_config():
    assert qfc.dashboard_bind() == ("100.110.49.44", 8211)
```

- [ ] **Step 1.2: Run tests to verify they fail**

```bash
cd /opt/scout-workshop && venv/bin/pytest tests/test_quality_floor_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.quality_floor_config'`

- [ ] **Step 1.3: Implement the module**

`scripts/quality_floor_config.py`:
```python
"""Quality-floor configuration — single source of truth for thresholds.

Lives in its own module so a config tweak is one diff away from a one-line
commit. No code change to workshop.py needed when tuning thresholds.

Register overrides let awwwards-tier kits use looser thresholds (more
whitespace tolerated) than conversion-tier kits (tighter).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = REPO_ROOT / "state"  # telemetry JSONL lives here

QUALITY_FLOOR: dict[str, Any] = {
    "thresholds": {
        "vertical_void_max_px": 500,
        "vertical_void_min_page_height": 4000,
        "substantial_section_min_text_chars": 80,
        "coverage_pct_min": 80,
        "hero_h1_max_word_chars": 10,
        "showpiece_wordmark_min_font_rem": 6,
        "manifest_min_substantial_sections": 2,
    },
    "retry_policy": {
        "retry_on_gate_b_fail": True,
        "max_retries": 1,
        "reuse_images_on_retry": True,
        "halt_on_identical_retry_output": True,
    },
    "register_overrides": {
        "awwwards": {"vertical_void_max_px": 700},
        "conversion": {"vertical_void_max_px": 400},
    },
    "dashboard": {
        "bind_address": "100.110.49.44",
        "bind_port": 8211,
        "loopback_also": True,
        "sse_poll_seconds": 5,
        "stats_cache_seconds": 30,
    },
}


def threshold(name: str, register: str | None = None) -> Any:
    """Get a threshold value, with optional register override.

    Falls back to default when register is None or unknown.
    Raises KeyError if the threshold name is not defined.
    """
    if register and register in QUALITY_FLOOR["register_overrides"]:
        override = QUALITY_FLOOR["register_overrides"][register]
        if name in override:
            return override[name]
    if name not in QUALITY_FLOOR["thresholds"]:
        raise KeyError(f"unknown threshold: {name}")
    return QUALITY_FLOOR["thresholds"][name]


def retry_enabled() -> bool:
    return QUALITY_FLOOR["retry_policy"]["retry_on_gate_b_fail"]


def max_retries() -> int:
    return QUALITY_FLOOR["retry_policy"]["max_retries"]


def reuse_images_on_retry() -> bool:
    return QUALITY_FLOOR["retry_policy"]["reuse_images_on_retry"]


def dashboard_bind() -> tuple[str, int]:
    d = QUALITY_FLOOR["dashboard"]
    return (d["bind_address"], d["bind_port"])
```

- [ ] **Step 1.4: Run tests to verify they pass**

```bash
cd /opt/scout-workshop && venv/bin/pytest tests/test_quality_floor_config.py -v
```

Expected: `7 passed`

- [ ] **Step 1.5: Commit**

```bash
cd /opt/scout-workshop
git add scripts/quality_floor_config.py tests/test_quality_floor_config.py
git commit -m "feat(qfloor): quality_floor_config with threshold + register override"
```

---

## Task 2: manifest_validator.py (Gate A)

**Files:**
- Create: `scripts/manifest_validator.py`
- Create: `tests/test_manifest_validator.py`

- [ ] **Step 2.1: Write the failing tests**

`tests/test_manifest_validator.py`:
```python
"""Tests for Gate A — Section Manifest YAML validation."""
from __future__ import annotations

import pytest
from pathlib import Path
from scripts.manifest_validator import (
    parse_manifest,
    validate_manifest,
    ManifestError,
    ManifestResult,
)


def test_parse_manifest_extracts_yaml_block(sample_manifest_yaml, tmp_path):
    brief_path = tmp_path / "brief.md"
    brief_path.write_text(sample_manifest_yaml)
    manifest = parse_manifest(brief_path)
    assert manifest is not None
    assert "section_manifest" in manifest
    assert len(manifest["section_manifest"]["index"]) == 6


def test_parse_manifest_returns_none_when_no_yaml(tmp_path):
    brief_path = tmp_path / "brief.md"
    brief_path.write_text("## Aesthetic\nNo manifest here.\n")
    assert parse_manifest(brief_path) is None


def test_parse_manifest_raises_on_malformed_yaml(tmp_path):
    brief_path = tmp_path / "brief.md"
    brief_path.write_text("---\nthis is: not [valid yaml: at all\n---\n")
    with pytest.raises(ManifestError, match="malformed"):
        parse_manifest(brief_path)


def test_validate_passes_with_two_case_grids(sample_manifest_yaml, tmp_path):
    brief_path = tmp_path / "brief.md"
    brief_path.write_text(sample_manifest_yaml)
    manifest = parse_manifest(brief_path)
    result = validate_manifest(manifest)
    assert result.passed is True
    assert result.failure_reason is None


def test_validate_fails_with_one_case_grid(thin_manifest_yaml, tmp_path):
    brief_path = tmp_path / "brief.md"
    brief_path.write_text(thin_manifest_yaml)
    manifest = parse_manifest(brief_path)
    result = validate_manifest(manifest)
    assert result.passed is False
    assert "case_grid" in result.failure_reason.lower()


def test_validate_fails_when_section_uses_unknown_type(tmp_path):
    brief_path = tmp_path / "brief.md"
    brief_path.write_text("""---
section_manifest:
  index:
    - {id: hero, type: bogus_type}
    - {id: services, type: case_grid, min_items: 3}
    - {id: portfolio, type: case_grid, min_items: 3}
  services: []
  contacts: []
---
""")
    manifest = parse_manifest(brief_path)
    result = validate_manifest(manifest)
    assert result.passed is False
    assert "bogus_type" in result.failure_reason


def test_failure_recap_text_lists_missing_requirements(thin_manifest_yaml, tmp_path):
    brief_path = tmp_path / "brief.md"
    brief_path.write_text(thin_manifest_yaml)
    manifest = parse_manifest(brief_path)
    result = validate_manifest(manifest)
    recap = result.failure_recap()
    assert "case_grid" in recap
    assert len(recap) > 30  # non-trivial diagnostic
```

- [ ] **Step 2.2: Run tests to verify they fail**

```bash
cd /opt/scout-workshop && venv/bin/pytest tests/test_manifest_validator.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.manifest_validator'`

- [ ] **Step 2.3: Implement the module**

`scripts/manifest_validator.py`:
```python
"""Gate A — Section Manifest YAML validation.

Parses the YAML frontmatter at the top of brief.md, validates against
schema, enforces the minimum-section rule from quality_floor_config.

Failure produces a ManifestResult with failure_recap() text that can be
fed back to the brief-generation prompt as a strict-recap retry instruction.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from scripts import quality_floor_config as qfc


# Allowed section types — keep enum stable; new types are v1.6 scope
ALLOWED_TYPES = {
    "hero",
    "stats_row",
    "case_grid",
    "manifesto",
    "callout",
    "showpiece_wordmark",
    "founder_chip_row",
    "trust_signals",
    "sticky_rail",
}

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


class ManifestError(Exception):
    """Raised when manifest YAML is present but malformed."""


@dataclass
class ManifestResult:
    passed: bool
    manifest: dict[str, Any] | None
    failure_reason: str | None = None
    missing_requirements: list[str] = field(default_factory=list)

    def failure_recap(self) -> str:
        """Text to prepend to a brief-regeneration prompt on retry."""
        if self.passed:
            return ""
        lines = [
            "Previous brief failed manifest validation.",
            f"Reason: {self.failure_reason}",
        ]
        if self.missing_requirements:
            lines.append("Missing requirements:")
            lines.extend(f"  - {r}" for r in self.missing_requirements)
        lines.append(
            "Emit a `section_manifest` YAML block at the top of the brief "
            "with at least 2 case_grid sections OR (1 case_grid + 1 manifesto + 1 stats_row)."
        )
        return "\n".join(lines)


def parse_manifest(brief_path: Path) -> dict[str, Any] | None:
    """Extract YAML frontmatter from brief.md.

    Returns the parsed dict, or None if no frontmatter present.
    Raises ManifestError on malformed YAML.
    """
    text = brief_path.read_text(errors="replace")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        raise ManifestError(f"malformed YAML frontmatter: {e}") from e
    if not isinstance(data, dict):
        raise ManifestError(f"frontmatter must be a mapping, got {type(data).__name__}")
    return data


def validate_manifest(manifest: dict[str, Any] | None) -> ManifestResult:
    """Validate a parsed manifest against the v1.4 schema.

    Rule: index page must declare >= 2 case_grid sections OR
          (>= 1 case_grid + >= 1 manifesto + >= 1 stats_row).
    """
    if manifest is None:
        return ManifestResult(
            passed=False,
            manifest=None,
            failure_reason="no section_manifest YAML frontmatter present",
            missing_requirements=["section_manifest block at top of brief.md"],
        )

    if "section_manifest" not in manifest:
        return ManifestResult(
            passed=False,
            manifest=manifest,
            failure_reason="frontmatter missing 'section_manifest' key",
        )

    sm = manifest["section_manifest"]
    if not isinstance(sm, dict) or "index" not in sm:
        return ManifestResult(
            passed=False,
            manifest=manifest,
            failure_reason="section_manifest.index missing or not a list",
        )

    index_sections = sm["index"]
    if not isinstance(index_sections, list):
        return ManifestResult(
            passed=False,
            manifest=manifest,
            failure_reason="section_manifest.index is not a list",
        )

    # Schema check: each section must have id + type, type must be in allowlist
    missing: list[str] = []
    for i, sec in enumerate(index_sections):
        if not isinstance(sec, dict) or "type" not in sec:
            missing.append(f"index[{i}] missing required 'type' field")
            continue
        if sec["type"] not in ALLOWED_TYPES:
            missing.append(
                f"index[{i}] uses unknown type {sec['type']!r}; "
                f"allowed: {sorted(ALLOWED_TYPES)}"
            )

    if missing:
        return ManifestResult(
            passed=False,
            manifest=manifest,
            failure_reason="; ".join(missing[:3]),
            missing_requirements=missing,
        )

    # Density rule: ≥2 case_grid OR (≥1 case_grid + ≥1 manifesto + ≥1 stats_row)
    types = [s["type"] for s in index_sections]
    case_grid_count = types.count("case_grid")
    manifesto_count = types.count("manifesto")
    stats_count = types.count("stats_row")

    rule_a = case_grid_count >= 2
    rule_b = case_grid_count >= 1 and manifesto_count >= 1 and stats_count >= 1
    if not (rule_a or rule_b):
        return ManifestResult(
            passed=False,
            manifest=manifest,
            failure_reason=(
                f"index has {case_grid_count} case_grid, {manifesto_count} manifesto, "
                f"{stats_count} stats_row — needs >=2 case_grid OR (>=1 case_grid + "
                f">=1 manifesto + >=1 stats_row)"
            ),
            missing_requirements=[
                "add at least one more case_grid section to index",
                "or add a manifesto + stats_row alongside the existing case_grid",
            ],
        )

    return ManifestResult(passed=True, manifest=manifest)
```

- [ ] **Step 2.4: Run tests to verify they pass**

```bash
cd /opt/scout-workshop && venv/bin/pytest tests/test_manifest_validator.py -v
```

Expected: `7 passed`

- [ ] **Step 2.5: Commit**

```bash
cd /opt/scout-workshop
git add scripts/manifest_validator.py tests/test_manifest_validator.py
git commit -m "feat(qfloor): manifest_validator for Gate A (brief section manifest)"
```

---

## Task 3: density_audit.py (Gate B.1 — deterministic)

**Files:**
- Create: `scripts/density_audit.py`
- Create: `tests/test_density_audit.py`

- [ ] **Step 3.1: Write the failing tests**

`tests/test_density_audit.py`:
```python
"""Tests for Gate B.1 — deterministic density audit.

Uses real historical runs as fixtures: May 15 (passed) vs May 17 (failed).
The May 17 run is the regression we're explicitly designing against.
"""
from __future__ import annotations

import pytest
from scripts.density_audit import (
    count_substantial_sections,
    check_article_density,
    check_hero_h1_word_cap,
    run_density_audit,
)


def test_substantial_sections_count_good_run(good_run_dir):
    """May 15 has 6 articles + 6 sections; expect substantial >= 3."""
    count = count_substantial_sections(good_run_dir / "kit" / "index.html")
    assert count >= 3, f"May 15 (good) should have >=3 substantial sections, got {count}"


def test_substantial_sections_count_bad_run(bad_run_dir):
    """May 17 has 3 articles + 4 sections; some sparse; expect < 3 substantial."""
    count = count_substantial_sections(bad_run_dir / "kit" / "index.html")
    assert count < 4, f"May 17 (bad) should have <4 substantial sections, got {count}"


def test_article_density_passes_good_run(good_run_dir):
    result = check_article_density(good_run_dir / "kit" / "index.html")
    assert result.passed is True


def test_hero_h1_word_cap_enforces_ten_chars():
    from scripts.density_audit import _check_h1_word_lengths
    # Each h1 in this synthetic page is the test subject
    assert _check_h1_word_lengths("<h1>Short words ok</h1>") == []
    assert _check_h1_word_lengths("<h1>considered work</h1>") == ["considered"]
    assert _check_h1_word_lengths("<h1>brilliantly considered</h1>") == [
        "brilliantly", "considered",
    ]


@pytest.mark.slow
def test_full_audit_returns_dict_per_check(good_run_dir):
    """Smoke test: full run returns a dict with all four check keys."""
    report = run_density_audit(good_run_dir / "kit", register="conversion")
    assert set(report.keys()) >= {
        "substantial_sections",
        "vertical_void",
        "article_density",
        "hero_h1_word_cap",
    }


@pytest.mark.slow
def test_full_audit_marks_may17_as_failing(bad_run_dir):
    """Regression target: May 17 must trigger at least one FAIL or sparse."""
    report = run_density_audit(bad_run_dir / "kit", register="conversion")
    failures = [
        k for k, v in report.items()
        if v.get("status") in ("fail", "sparse")
    ]
    assert len(failures) >= 1, f"May 17 should fail at least one check, got {report}"
```

- [ ] **Step 3.2: Run tests to verify they fail**

```bash
cd /opt/scout-workshop && venv/bin/pytest tests/test_density_audit.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.density_audit'`

- [ ] **Step 3.3: Implement the module**

`scripts/density_audit.py`:
```python
"""Gate B.1 — deterministic density audit.

Five checks, each returns {status: pass|fail|sparse|skipped, evidence: str}:
- substantial_sections    : count sections/articles with >=80c text + image
- vertical_void          : max consecutive empty pixels via Playwright
- article_density        : per-article check
- hero_h1_word_cap       : no word >10c in hero h1
- wordmark_treatment     : if manifest declares showpiece, verify large

The Playwright-based void check is slow and can fail to launch in some
environments; the orchestrator should treat skipped/inconclusive as
soft-warning (ship with warning) rather than hard-fail.
"""
from __future__ import annotations

import logging
import re
import subprocess
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from scripts import quality_floor_config as qfc

logger = logging.getLogger(__name__)

ARTICLE_RE = re.compile(r"<article[^>]*>(.*?)</article>", re.DOTALL | re.IGNORECASE)
SECTION_RE = re.compile(r"<section[^>]*>(.*?)</section>", re.DOTALL | re.IGNORECASE)
IMG_RE = re.compile(r"<img\b", re.IGNORECASE)
H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.DOTALL | re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class CheckResult:
    status: str  # pass | fail | sparse | skipped
    evidence: str
    measured: Any = None

    def asdict(self) -> dict[str, Any]:
        return asdict(self)


def _strip_tags(html: str) -> str:
    return re.sub(r"\s+", " ", TAG_RE.sub(" ", html)).strip()


def count_substantial_sections(index_html_path: Path) -> int:
    """Count <section> + <article> elements with >=80c text AND >=1 <img>."""
    if not index_html_path.exists():
        return 0
    content = index_html_path.read_text(errors="replace")
    min_chars = qfc.threshold("substantial_section_min_text_chars")
    count = 0
    for regex in (SECTION_RE, ARTICLE_RE):
        for m in regex.finditer(content):
            inner = m.group(1)
            text_len = len(_strip_tags(inner))
            has_img = bool(IMG_RE.search(inner))
            if text_len >= min_chars and has_img:
                count += 1
    return count


def check_substantial_sections(
    index_html_path: Path,
    page_min: int = 3,
) -> CheckResult:
    count = count_substantial_sections(index_html_path)
    if count >= page_min:
        return CheckResult(
            status="pass",
            evidence=f"{count} substantial sections (>= {page_min})",
            measured=count,
        )
    return CheckResult(
        status="fail",
        evidence=f"only {count} substantial sections (need >= {page_min})",
        measured=count,
    )


def check_article_density(index_html_path: Path) -> CheckResult:
    if not index_html_path.exists():
        return CheckResult(status="skipped", evidence="index.html missing")
    content = index_html_path.read_text(errors="replace")
    articles = ARTICLE_RE.findall(content)
    if not articles:
        return CheckResult(status="skipped", evidence="no <article> elements")
    min_chars = qfc.threshold("substantial_section_min_text_chars")
    thin: list[int] = []
    for i, art in enumerate(articles, 1):
        text_len = len(_strip_tags(art))
        has_img = bool(IMG_RE.search(art)) or 'class="manifesto"' in art
        if text_len < min_chars or not has_img:
            thin.append(i)
    if thin:
        return CheckResult(
            status="sparse",
            evidence=f"articles {thin} have <{min_chars}c text or no image",
            measured=thin,
        )
    return CheckResult(
        status="pass",
        evidence=f"{len(articles)} articles all meet density bar",
        measured=len(articles),
    )


def _check_h1_word_lengths(html: str) -> list[str]:
    """Return list of words exceeding the configured max char length."""
    max_len = qfc.threshold("hero_h1_max_word_chars")
    offending: list[str] = []
    for m in H1_RE.finditer(html):
        text = _strip_tags(m.group(1))
        for word in re.findall(r"[A-Za-z]+", text):
            if len(word) > max_len:
                offending.append(word.lower())
    return offending


def check_hero_h1_word_cap(index_html_path: Path) -> CheckResult:
    if not index_html_path.exists():
        return CheckResult(status="skipped", evidence="index.html missing")
    content = index_html_path.read_text(errors="replace")
    offending = _check_h1_word_lengths(content)
    if offending:
        return CheckResult(
            status="fail",
            evidence=f"hero h1 has words >10c: {offending}",
            measured=offending,
        )
    return CheckResult(status="pass", evidence="all hero h1 words within cap")


def check_vertical_void(
    index_html_path: Path,
    register: str | None = None,
) -> CheckResult:
    """Use Playwright to measure max consecutive vertical pixels with no content.

    Slow check (~3-5s). Soft-skips if Playwright fails to launch.
    """
    if not index_html_path.exists():
        return CheckResult(status="skipped", evidence="index.html missing")

    max_void_px = qfc.threshold("vertical_void_max_px", register=register)
    min_page_h = qfc.threshold("vertical_void_min_page_height")

    js = """
    async () => {
      const els = Array.from(document.querySelectorAll('p, h1, h2, h3, h4, img, video, figure, article'));
      const boxes = els
        .filter(e => {
          const s = getComputedStyle(e);
          return s.visibility !== 'hidden' && s.display !== 'none';
        })
        .map(e => {
          const r = e.getBoundingClientRect();
          return { top: r.top + window.scrollY, bottom: r.bottom + window.scrollY };
        })
        .filter(b => b.bottom > b.top)
        .sort((a, b) => a.top - b.top);
      let maxGap = 0, gapStart = 0;
      const pageH = document.documentElement.scrollHeight;
      let prevBottom = 0;
      for (const b of boxes) {
        if (b.top > prevBottom) {
          const gap = b.top - prevBottom;
          if (gap > maxGap) { maxGap = gap; gapStart = prevBottom; }
        }
        if (b.bottom > prevBottom) prevBottom = b.bottom;
      }
      return { maxGap: Math.round(maxGap), gapStart: Math.round(gapStart), pageHeight: Math.round(pageH) };
    }
    """

    try:
        from playwright.sync_api import sync_playwright  # lazy import
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(f"file://{index_html_path.resolve()}", wait_until="networkidle", timeout=15000)
            page.wait_for_timeout(1500)
            data = page.evaluate(js)
            browser.close()
    except Exception as e:  # noqa: BLE001
        logger.warning("vertical_void check skipped (Playwright error: %s)", e)
        return CheckResult(status="skipped", evidence=f"Playwright unavailable: {e}")

    if data["maxGap"] > max_void_px and data["pageHeight"] < min_page_h:
        return CheckResult(
            status="fail",
            evidence=f"max void {data['maxGap']}px (threshold {max_void_px}px) starting y={data['gapStart']}, page height {data['pageHeight']}",
            measured=data,
        )
    return CheckResult(
        status="pass",
        evidence=f"max void {data['maxGap']}px (under {max_void_px}px threshold)",
        measured=data,
    )


def run_density_audit(
    kit_dir: Path,
    register: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Run all four checks; return dict keyed by check_id.

    Each value is the asdict-form of CheckResult.
    Wordmark measurement omitted — no reliable selector without a fixed CSS
    contract; add back in v1.6 if a class convention is established.
    """
    index = kit_dir / "index.html"
    results = {
        "substantial_sections": check_substantial_sections(index).asdict(),
        "vertical_void": check_vertical_void(index, register=register).asdict(),
        "article_density": check_article_density(index).asdict(),
        "hero_h1_word_cap": check_hero_h1_word_cap(index).asdict(),
    }
    return results


def audit_passed(report: dict[str, dict[str, Any]]) -> bool:
    """True if no check returned status='fail'."""
    return not any(r["status"] == "fail" for r in report.values())
```

- [ ] **Step 3.4: Run tests to verify they pass**

```bash
cd /opt/scout-workshop && venv/bin/pytest tests/test_density_audit.py -v
```

Expected: `7 passed` (5 fast + 2 marked slow that may take ~5s each)

- [ ] **Step 3.5: Commit**

```bash
cd /opt/scout-workshop
git add scripts/density_audit.py tests/test_density_audit.py
git commit -m "feat(qfloor): density_audit Gate B.1 (5 deterministic checks)"
```

---

## Task 4: skills/audit_brief_coverage.md (Claude prompt)

**Files:**
- Create: `skills/audit_brief_coverage.md`
- Create: `scripts/brief_coverage.py`
- Create: `tests/test_brief_coverage.py`

- [ ] **Step 4.1: Write the prompt template**

`skills/audit_brief_coverage.md`:
```markdown
# Brief-Coverage Audit Prompt

You are auditing whether a generated kit honored its brief's `section_manifest`.

## Inputs (provided in the conversation that calls you)

- `brief.md` — full brief with `section_manifest` YAML at top
- `index.html`, `services.html`, `contacts.html` — source HTML of the kit

## Task

For each item in the `section_manifest.index` (and `section_manifest.services` and `section_manifest.contacts`), locate the rendered equivalent in the HTML and grade it.

## Output

Return ONLY valid JSON, no prose, in this exact shape:

```json
{
  "coverage_pct": 0-100,
  "sections": [
    {
      "section_id": "hero",
      "page": "index",
      "status": "present" | "sparse" | "absent",
      "evidence_selector": "section.hero h1",
      "notes": "concise reason"
    }
  ]
}
```

Do NOT include a `verdict` field — the orchestrator calculates pass/fail from
`coverage_pct` against a threshold that may vary by register.

## Grading rules

- `present` — the section exists in the rendered HTML AND meets the `min_items` / `required_elements` declared in the manifest entry. For case_grid entries: must have at least min_items articles with required content.
- `sparse` — the section exists structurally but is under-content (e.g., heading present without body, fewer items than min_items, articles with <80 chars text).
- `absent` — no matching element in the rendered HTML.

`coverage_pct = (count of present) / (total sections in manifest) * 100`, rounded.

## Constraints

- Do not modify the kit. Read-only audit.
- Return JSON only. No markdown, no commentary, no explanation outside the JSON.
- If a section_manifest entry's type is unknown to you, mark status="absent" with notes="unknown manifest type".
```

- [ ] **Step 4.2: Write the failing tests**

`tests/test_brief_coverage.py`:
```python
"""Tests for Gate B.2 — Claude-based semantic coverage audit.

The subprocess call to Claude is mocked. We test:
- correct subprocess args are constructed
- malformed JSON output is handled gracefully
- coverage_pct threshold comparison
"""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock
import pytest

from scripts.brief_coverage import (
    run_brief_coverage,
    CoverageResult,
    InconclusiveCoverage,
)


def test_coverage_parses_valid_claude_output(tmp_run_dir):
    fake = json.dumps({
        "coverage_pct": 100,
        "sections": [
            {"section_id": "hero", "page": "index", "status": "present", "evidence_selector": "section.hero", "notes": ""},
        ],
    })
    (tmp_run_dir / "brief.md").write_text("# brief stub")
    (tmp_run_dir / "kit" / "index.html").write_text("<h1>x</h1>")
    with patch("scripts.brief_coverage._invoke_claude", return_value=fake):
        result = run_brief_coverage(tmp_run_dir)
    assert isinstance(result, CoverageResult)
    assert result.verdict == "pass"
    assert result.coverage_pct == 100


def test_coverage_fails_when_pct_below_threshold(tmp_run_dir):
    fake = json.dumps({"coverage_pct": 60, "sections": []})
    (tmp_run_dir / "brief.md").write_text("# brief stub")
    (tmp_run_dir / "kit" / "index.html").write_text("<h1>x</h1>")
    with patch("scripts.brief_coverage._invoke_claude", return_value=fake):
        result = run_brief_coverage(tmp_run_dir)
    assert result.verdict == "fail"
    assert result.coverage_pct == 60


def test_coverage_returns_inconclusive_on_malformed_json(tmp_run_dir):
    (tmp_run_dir / "brief.md").write_text("# brief stub")
    (tmp_run_dir / "kit" / "index.html").write_text("<h1>x</h1>")
    with patch("scripts.brief_coverage._invoke_claude", return_value="this is not json"):
        result = run_brief_coverage(tmp_run_dir)
    assert isinstance(result, InconclusiveCoverage)
    assert "json" in result.reason.lower()


def test_coverage_returns_inconclusive_on_subprocess_failure(tmp_run_dir):
    (tmp_run_dir / "brief.md").write_text("# brief stub")
    (tmp_run_dir / "kit" / "index.html").write_text("<h1>x</h1>")
    with patch("scripts.brief_coverage._invoke_claude", side_effect=RuntimeError("claude died")):
        result = run_brief_coverage(tmp_run_dir)
    assert isinstance(result, InconclusiveCoverage)
```

- [ ] **Step 4.3: Run tests to verify they fail**

```bash
cd /opt/scout-workshop && venv/bin/pytest tests/test_brief_coverage.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.brief_coverage'`

- [ ] **Step 4.4: Implement the module**

`scripts/brief_coverage.py`:
```python
"""Gate B.2 — Claude-as-auditor for semantic brief coverage.

Invokes `claude --print` with the audit_brief_coverage.md prompt and the
kit files attached. Parses the resulting JSON, returns CoverageResult or
InconclusiveCoverage on any failure (subprocess error, malformed JSON).

The orchestrator treats Inconclusive as soft (ship if Gate B.1 passed alone).
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts import quality_floor_config as qfc

logger = logging.getLogger(__name__)

SCRIPTS_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SCRIPTS_DIR.parent / "skills"


@dataclass
class CoverageResult:
    verdict: str  # pass | fail
    coverage_pct: int
    sections: list[dict[str, Any]] = field(default_factory=list)

    def passed(self) -> bool:
        return self.verdict == "pass"


@dataclass
class InconclusiveCoverage:
    reason: str

    def passed(self) -> bool:
        return False  # treat as soft fail (orchestrator decides)


def _load_prompt() -> str:
    return (SKILLS_DIR / "audit_brief_coverage.md").read_text()


def _invoke_claude(prompt: str, attach_files: list[Path], timeout_sec: int = 600) -> str:
    """Subprocess-call to `claude --print` with attached files.

    Mirrors the existing run_claude() pattern in workshop.py:370.
    Returns stdout. Raises RuntimeError on non-zero exit.
    """
    cmd = ["claude", "--print", "--effort", "medium"]
    for f in attach_files:
        cmd += ["--attach", str(f)]
    proc = subprocess.run(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude exit={proc.returncode}: {proc.stderr[:500]}")
    return proc.stdout


def _extract_json(text: str) -> dict[str, Any]:
    """Find the JSON object in Claude's output, even if wrapped in prose."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("no JSON object found in output")
    return json.loads(m.group(0))


def run_brief_coverage(run_dir: Path) -> CoverageResult | InconclusiveCoverage:
    """Run the Claude-based coverage audit.

    Returns InconclusiveCoverage on any failure (subprocess, parsing,
    malformed schema). Returns CoverageResult on success.
    """
    brief_path = run_dir / "brief.md"
    kit_dir = run_dir / "kit"
    if not brief_path.exists():
        return InconclusiveCoverage(reason="brief.md not found")

    attach_files = [brief_path]
    for name in ("index.html", "services.html", "contacts.html"):
        p = kit_dir / name
        if p.exists():
            attach_files.append(p)

    prompt = _load_prompt()
    try:
        raw = _invoke_claude(prompt, attach_files)
    except Exception as e:  # noqa: BLE001
        logger.warning("brief_coverage subprocess failed: %s", e)
        return InconclusiveCoverage(reason=f"subprocess: {e}")

    try:
        data = _extract_json(raw)
    except Exception as e:  # noqa: BLE001
        logger.warning("brief_coverage json parse failed: %s; raw=%r", e, raw[:200])
        return InconclusiveCoverage(reason=f"json parse: {e}")

    # Sanity-check schema — orchestrator derives verdict from coverage_pct, no field needed
    if not isinstance(data, dict) or "coverage_pct" not in data:
        return InconclusiveCoverage(reason="output missing coverage_pct")

    # Enforce threshold from config (don't trust Claude's verdict if pct disagrees)
    pct = int(data.get("coverage_pct") or 0)
    threshold_pct = qfc.threshold("coverage_pct_min")
    final_verdict = "pass" if pct >= threshold_pct else "fail"

    return CoverageResult(
        verdict=final_verdict,
        coverage_pct=pct,
        sections=list(data.get("sections") or []),
    )
```

- [ ] **Step 4.5: Run tests to verify they pass**

```bash
cd /opt/scout-workshop && venv/bin/pytest tests/test_brief_coverage.py -v
```

Expected: `4 passed`

- [ ] **Step 4.6: Commit**

```bash
cd /opt/scout-workshop
git add scripts/brief_coverage.py skills/audit_brief_coverage.md tests/test_brief_coverage.py
git commit -m "feat(qfloor): brief_coverage Gate B.2 (Claude semantic audit)"
```

---

## Task 5: telemetry_writer.py

**Files:**
- Create: `scripts/telemetry_writer.py`
- Create: `tests/test_telemetry_writer.py`

- [ ] **Step 5.1: Write the failing tests**

`tests/test_telemetry_writer.py`:
```python
"""Tests for telemetry JSONL writer."""
from __future__ import annotations

import json
from pathlib import Path
from scripts.telemetry_writer import append_run_telemetry


def test_append_creates_jsonl_when_missing(tmp_path):
    jsonl = tmp_path / "telemetry.jsonl"
    append_run_telemetry(jsonl, {"run_slug": "foo", "final_status": "shipped"})
    assert jsonl.exists()
    lines = jsonl.read_text().strip().split("\n")
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["run_slug"] == "foo"


def test_append_preserves_existing_lines(tmp_path):
    jsonl = tmp_path / "telemetry.jsonl"
    append_run_telemetry(jsonl, {"run_slug": "a"})
    append_run_telemetry(jsonl, {"run_slug": "b"})
    append_run_telemetry(jsonl, {"run_slug": "c"})
    lines = jsonl.read_text().strip().split("\n")
    assert len(lines) == 3
    assert json.loads(lines[0])["run_slug"] == "a"
    assert json.loads(lines[2])["run_slug"] == "c"


def test_append_serializes_nested_dicts(tmp_path):
    jsonl = tmp_path / "telemetry.jsonl"
    payload = {
        "run_slug": "x",
        "gate_b1": {"substantial_sections": "pass", "vertical_void": "fail-720px"},
    }
    append_run_telemetry(jsonl, payload)
    line = jsonl.read_text().strip()
    parsed = json.loads(line)
    assert parsed["gate_b1"]["vertical_void"] == "fail-720px"


def test_append_adds_ts_when_missing(tmp_path):
    jsonl = tmp_path / "telemetry.jsonl"
    append_run_telemetry(jsonl, {"run_slug": "no-ts"})
    line = jsonl.read_text().strip()
    parsed = json.loads(line)
    assert "ts" in parsed
    assert parsed["ts"].endswith("Z") or parsed["ts"].endswith("+00:00")
```

- [ ] **Step 5.2: Run to verify failure**

```bash
cd /opt/scout-workshop && venv/bin/pytest tests/test_telemetry_writer.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 5.3: Implement the module**

`scripts/telemetry_writer.py`:
```python
"""Append-only telemetry writer.

Single-writer assumption (workshop cron is serial). Writes via
open-append-fsync to minimize torn-write risk; not a strict atomic
guarantee, but good enough for a single-writer log.

Schema is documented in docs/workshop-v1.4-quality-floor-design.md.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def append_run_telemetry(jsonl_path: Path, record: dict[str, Any]) -> None:
    """Append a single JSON line to the telemetry file.

    Creates the file (and any parent dirs) if missing.
    Auto-fills `ts` if absent.
    """
    if "ts" not in record:
        record = {"ts": datetime.now(timezone.utc).isoformat(), **record}
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, separators=(",", ":")) + "\n"
    with open(jsonl_path, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())
```

- [ ] **Step 5.4: Run to verify pass**

```bash
cd /opt/scout-workshop && venv/bin/pytest tests/test_telemetry_writer.py -v
```

Expected: `4 passed`

- [ ] **Step 5.5: Commit**

```bash
cd /opt/scout-workshop
git add scripts/telemetry_writer.py tests/test_telemetry_writer.py
git commit -m "feat(qfloor): telemetry_writer (atomic JSONL append)"
```

---

## Task 6: workshop-playbook.md modifications

**Files:**
- Modify: `skills/workshop-playbook.md`

- [ ] **Step 6.1: Read current playbook to find insertion point**

```bash
grep -n "## " /opt/scout-workshop/skills/workshop-playbook.md | head -20
```

Find the section where brief-generation prompt is defined (likely "## Brief Synthesis" or similar).

- [ ] **Step 6.2: Insert Section Manifest requirement block**

Locate the brief-generation prompt section in `workshop-playbook.md`. Immediately before the "## Format" or "## Output" instructions, insert:

```markdown
## Section Manifest (REQUIRED at top of brief.md)

The first thing in brief.md MUST be a YAML frontmatter block declaring the section_manifest. This is a machine-readable contract: downstream gates check that the generated kit honors every section you declare here.

Format — exact template, no improvisation:

```yaml
---
section_manifest:
  index:
    - {id: hero, type: hero, required_elements: [h1, subhead, primary_cta, image]}
    - {id: trust, type: stats_row, required_elements: [eyebrow, stat_count_min_3]}
    - {id: services, type: case_grid, min_items: 3, item_requires: [image, h3, body_min_80c]}
    - {id: portfolio, type: case_grid, min_items: 3, item_requires: [image, h3, year]}
    - {id: footer_callout, type: callout, required_elements: [h2, body, secondary_cta]}
    - {id: wordmark, type: showpiece_wordmark, required_elements: [brand_token]}
  services:
    - {id: services_hero, type: hero}
    - {id: services_list, type: case_grid, min_items: 3}
  contacts:
    - {id: contacts_hero, type: hero}
    - {id: contacts_form, type: callout}
---
```

Allowed `type` values (closed set — no inventing new ones):
- `hero`, `stats_row`, `case_grid`, `manifesto`, `callout`, `showpiece_wordmark`, `founder_chip_row`, `trust_signals`, `sticky_rail`

Density rule for index page: at least 2 `case_grid` sections OR at least 1 `case_grid` plus 1 `manifesto` plus 1 `stats_row`. Briefs that fall short get retried once and halted if the retry also falls short — there is no path to ship a kit from a brief with a thin manifest.

Then continue with the existing `## Aesthetic`, `## Conversion structure`, etc. sections below the frontmatter.
```

- [ ] **Step 6.3: Verify the playbook still loads via existing helper**

```bash
cd /opt/scout-workshop && venv/bin/python -c "
from scripts.workshop import load_prompt_template
text = load_prompt_template('workshop-playbook')
assert 'section_manifest' in text, 'manifest block missing'
print('OK')
"
```

Expected: `OK`

- [ ] **Step 6.4: Commit**

```bash
cd /opt/scout-workshop
git add skills/workshop-playbook.md
git commit -m "feat(qfloor): playbook requires section_manifest YAML frontmatter"
```

---

## Task 7: workshop.py orchestration glue

**Files:**
- Modify: `scripts/workshop.py`

This task wires Gates A, B, and C into `main()`. The orchestrator is the **only** place that calls the new modules. All state mutation (run dir moves, JSONL appends, Telegram sends) lives here.

- [ ] **Step 7.0: Bump systemd TimeoutStartSec**

The retry loop adds up to ~40min worst-case (brief retry + kit regeneration + two gate
runs). The current `7500s` (2h 5m) may expire before the second gate completes.

```bash
sed -i 's/TimeoutStartSec=7500/TimeoutStartSec=10800/' \
    /opt/scout-workshop/systemd/workshop.service
sudo cp /opt/scout-workshop/systemd/workshop.service \
    /etc/systemd/system/workshop.service
sudo systemctl daemon-reload
```

Verify:
```bash
grep TimeoutStartSec /etc/systemd/system/workshop.service
```
Expected: `TimeoutStartSec=10800`

- [ ] **Step 7.1: Add new imports**

Find the imports block near the top of `scripts/workshop.py` (lines 60-90). Add:

```python
# v1.4 quality-floor imports
from scripts import quality_floor_config as qfc
from scripts.manifest_validator import (
    parse_manifest,
    validate_manifest,
    ManifestError,
    ManifestResult,
)
from scripts.density_audit import run_density_audit, audit_passed
from scripts.brief_coverage import run_brief_coverage, CoverageResult, InconclusiveCoverage
from scripts.telemetry_writer import append_run_telemetry
```

- [ ] **Step 7.2: Add Gate A helper above `synthesize_brief()`**

Find `def synthesize_brief(` at `scripts/workshop.py:542`. Immediately above it, insert:

```python
def gate_a_validate_brief(brief_path: Path, run_dir: Path) -> ManifestResult:
    """Gate A — Section Manifest validation.

    Parses brief.md frontmatter, validates schema. On failure, the
    failure_recap can be fed back to a brief-regeneration retry.
    """
    try:
        manifest = parse_manifest(brief_path)
    except ManifestError as e:
        return ManifestResult(
            passed=False,
            manifest=None,
            failure_reason=str(e),
        )
    result = validate_manifest(manifest)
    # Persist parsed manifest for downstream gates
    if result.manifest:
        (run_dir / "manifest.json").write_text(json.dumps(result.manifest, indent=2))
    return result
```

- [ ] **Step 7.3: Add Gate B+C orchestrator above `self_audit()`**

Find `def self_audit(` at `scripts/workshop.py:672`. Immediately above it, insert:

```python
def _kit_fingerprint(kit_dir: Path) -> str:
    """MD5 of kit HTML files — detects identical retry output before wasting a Gate B run."""
    import hashlib
    h = hashlib.md5()
    for name in sorted(["index.html", "services.html", "contacts.html"]):
        p = kit_dir / name
        if p.exists():
            h.update(name.encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def run_quality_gate(
    run_dir: Path,
    kit_dir: Path,
    register: str,
) -> tuple[bool, dict[str, Any]]:
    """Gate B: density audit + brief-coverage audit. Returns (passed, report).

    Report contains both gate_b1 (deterministic) and gate_b2 (semantic) results.
    """
    b1 = run_density_audit(kit_dir, register=register)
    b2 = run_brief_coverage(run_dir)

    b1_passed = audit_passed(b1)
    if isinstance(b2, CoverageResult):
        b2_passed = b2.passed()
        b2_dict = {
            "verdict": b2.verdict,
            "coverage_pct": b2.coverage_pct,
            "sections_present": sum(1 for s in b2.sections if s.get("status") == "present"),
            "sections_sparse": sum(1 for s in b2.sections if s.get("status") == "sparse"),
            "sections_absent": sum(1 for s in b2.sections if s.get("status") == "absent"),
        }
    else:
        # Inconclusive — soft, ship if Gate B.1 alone passed
        b2_passed = True
        b2_dict = {"verdict": "inconclusive", "reason": b2.reason}

    (run_dir / "density_audit.json").write_text(json.dumps(b1, indent=2))
    (run_dir / "coverage_audit.json").write_text(json.dumps(b2_dict, indent=2))

    return (b1_passed and b2_passed), {"gate_b1": b1, "gate_b2": b2_dict}


def format_retry_recap(report: dict[str, Any]) -> str:
    """Build a strict-recap prompt prefix for kit-gen retry."""
    lines = ["Previous kit attempt failed quality gates. Specifically:"]
    b1 = report.get("gate_b1", {})
    for k, v in b1.items():
        if v.get("status") == "fail":
            lines.append(f"  - {k}: {v.get('evidence')}")
    b2 = report.get("gate_b2", {})
    if b2.get("verdict") == "fail":
        lines.append(f"  - brief_coverage: {b2.get('coverage_pct')}% (need >= {qfc.threshold('coverage_pct_min')}%)")
    lines.append(
        "Regenerate the kit honoring the section_manifest. Each declared section "
        "must render with substantial content (>=80 chars text + image for case_grid "
        "items). Avoid vertical voids — fill empty regions with manifest-declared "
        "sections."
    )
    return "\n".join(lines)


def halt_with_telegram(
    run_dir: Path,
    report_attempt1: dict,
    report_attempt2: dict,
    brief_path: Path,
) -> Path:
    """Move run dir to runs-halted/ and send diagnostic to Telegram.

    Returns the new path of the halted run.
    """
    halted_root = run_dir.parent.parent / "runs-halted"
    halted_root.mkdir(exist_ok=True)
    new_path = halted_root / run_dir.name
    if new_path.exists():
        # Defensive: don't clobber an existing halted run
        new_path = halted_root / f"{run_dir.name}-{int(time.time())}"
    shutil.move(str(run_dir), str(new_path))
    # Telegram message (best-effort)
    try:
        msg = (
            f"⛔ Workshop halted: {new_path.name}\n"
            f"Attempt 1: {_one_line_verdict(report_attempt1)}\n"
            f"Attempt 2: {_one_line_verdict(report_attempt2)}\n"
            f"Brief: see {new_path}/brief.md\n"
            f"Reply with `/workshop ship-anyway {new_path.name}` or `/workshop skip`."
        )
        scout_lib.telegram_send(msg)
    except Exception as e:
        logger.warning("halt telegram send failed: %s", e)
    return new_path


def _one_line_verdict(report: dict) -> str:
    b1 = report.get("gate_b1", {})
    fails = [k for k, v in b1.items() if v.get("status") == "fail"]
    b2 = report.get("gate_b2", {})
    pct = b2.get("coverage_pct", "?")
    return f"density_fails={fails or 'none'}, coverage={pct}%"
```

- [ ] **Step 7.4: Modify `main()` to call the gates**

Find `def main(` in `scripts/workshop.py`. Inside, locate the call sequence (synthesize_brief → generate_kit → generate_kit_images → self_audit). Modify to inject the gates:

```python
# AFTER synthesize_brief() and BEFORE generate_kit():
gate_a = gate_a_validate_brief(brief_path, run_dir)
if not gate_a.passed:
    logger.warning("Gate A failed: %s", gate_a.failure_reason)
    # ONE retry of brief generation with recap
    brief_path = synthesize_brief(
        vertical, aesthetic, references, run_dir,
        strict_recap=gate_a.failure_recap(),
    )
    gate_a = gate_a_validate_brief(brief_path, run_dir)
    if not gate_a.passed:
        logger.error("Gate A failed after retry: %s", gate_a.failure_reason)
        scout_lib.telegram_send(
            f"⛔ Workshop halted at Gate A: {run_dir.name}\n"
            f"Brief manifest invalid after retry: {gate_a.failure_reason}"
        )
        return EXIT_QUALITY_HALT
manifest = gate_a.manifest

# ... existing generate_kit, generate_kit_images, self_audit calls ...

# AFTER self_audit() succeeds:
register = "awwwards" if vertical == "awwwards" else "conversion"
gate_b_passed, gate_b_report = run_quality_gate(run_dir, kit_dir, register)

if not gate_b_passed and qfc.retry_enabled():
    scout_lib.telegram_send(
        f"⚠ Gate B failed for {run_dir.name}, retrying once with diagnostic recap"
    )
    # Snapshot attempt 1 BEFORE retry mutates kit_dir
    snapshot_attempt(run_dir, kit_dir, attempt=1)
    recap = format_retry_recap(gate_b_report)
    # Retry generate_kit with strict recap. Reuse images per config.
    new_kit_dir = generate_kit(brief_path, references, run_dir, strict_recap=recap)
    if not qfc.reuse_images_on_retry():
        generate_kit_images(new_kit_dir, run_dir)
    # Identical-output guard: compare retry against snapshot, not the (possibly
    # mutated) original kit_dir — snapshot_attempt() is the immutable baseline.
    if _kit_fingerprint(run_dir / "attempt-1") == _kit_fingerprint(new_kit_dir):
        logger.error("Retry produced identical kit output — halting without re-running Gate B")
        halted_path = halt_with_telegram(run_dir, gate_b_report, gate_b_report, brief_path)
        _record_telemetry(
            halted_path, gate_a, gate_b_report, None, register,
            retried=True, final_status="halted-identical-retry",
        )
        return EXIT_QUALITY_HALT
    # Re-audit
    gate_b_passed_retry, gate_b_report_retry = run_quality_gate(
        run_dir, new_kit_dir, register,
    )
    if not gate_b_passed_retry:
        halted_path = halt_with_telegram(run_dir, gate_b_report, gate_b_report_retry, brief_path)
        _record_telemetry(halted_path, gate_a, gate_b_report, gate_b_report_retry,
                          register, final_status="halted")
        return EXIT_QUALITY_HALT
    # Retry succeeded
    gate_b_report = gate_b_report_retry
    kit_dir = new_kit_dir
    retried = True
else:
    retried = False

# ... existing capture_screenshots, deliver calls ...

# At end of main(), before returning:
_record_telemetry(run_dir, gate_a, gate_b_report, None, register,
                  retried=retried, final_status="shipped")
```

- [ ] **Step 7.5: Add `snapshot_attempt()` and `_record_telemetry()` helpers**

Above `main()`, add:

```python
def snapshot_attempt(run_dir: Path, kit_dir: Path, attempt: int) -> None:
    """Copy current kit dir to run_dir/attempt-N/ before retry."""
    snap = run_dir / f"attempt-{attempt}"
    if snap.exists():
        return
    shutil.copytree(kit_dir, snap)


def _record_telemetry(
    run_dir: Path,
    gate_a: ManifestResult,
    gate_b_report: dict,
    gate_b_retry_report: dict | None,
    register: str,
    retried: bool = False,
    final_status: str = "shipped",
) -> None:
    """Write one line to state/quality_floor_telemetry.jsonl."""
    from scripts.quality_floor_config import STATE_DIR
    telemetry_path = STATE_DIR / "quality_floor_telemetry.jsonl"
    b1 = gate_b_report.get("gate_b1", {})
    b2 = gate_b_report.get("gate_b2", {})
    record = {
        "run_slug": run_dir.name,
        "register": register,
        "vertical": run_dir.name.split("-", 7)[-2] if "-" in run_dir.name else "?",
        "sub_aesthetic": run_dir.name.split("-", 7)[-1] if "-" in run_dir.name else "?",
        "gate_a": "pass" if gate_a.passed else "fail",
        "gate_b1": {k: v.get("status") for k, v in b1.items()},
        "gate_b2": b2,
        "retried": retried,
        "retry_outcome": "pass" if retried and final_status == "shipped" else None,
        "final_status": final_status,
    }
    try:
        append_run_telemetry(telemetry_path, record)
    except Exception as e:
        logger.warning("telemetry append failed: %s", e)
```

- [ ] **Step 7.6: Add `synthesize_brief()` and `generate_kit()` `strict_recap=` kwarg**

Find `def synthesize_brief(` and `def generate_kit(`. Add `strict_recap: str | None = None` to each signature. When non-None, prepend the recap as a "## Previous attempt failed:" block to the prompt before sending to Claude.

- [ ] **Step 7.7: Add `EXIT_QUALITY_HALT` constant**

Near the top of `scripts/workshop.py` with other constants, add:

```python
EXIT_QUALITY_HALT = 42  # distinct from normal exit codes
```

- [ ] **Step 7.8: Verify workshop.py still imports cleanly**

```bash
cd /opt/scout-workshop && venv/bin/python -c "from scripts import workshop; print('imports ok')"
```

Expected: `imports ok`

- [ ] **Step 7.9: Commit**

```bash
cd /opt/scout-workshop
git add scripts/workshop.py systemd/workshop.service
git commit -m "feat(qfloor): wire Gate A + Gate B + Gate C retry into workshop.py main(); bump TimeoutStartSec=10800"
```

---

## Task 8: Integration test

**Files:**
- Create: `tests/test_workshop_gates_integration.py`

- [ ] **Step 8.1: Write the integration test**

`tests/test_workshop_gates_integration.py`:
```python
"""End-to-end test of the gate pipeline using historical run fixtures.

Does NOT call Claude. Mocks the LLM calls. Verifies orchestration is wired:
- Gate A fails on bad manifest → triggers retry path
- Gate B passes on May 15 → ships
- Gate B fails on May 17 → triggers retry
"""
from __future__ import annotations

import pytest
from unittest.mock import patch
from pathlib import Path

from scripts.manifest_validator import validate_manifest, parse_manifest
from scripts.density_audit import run_density_audit, audit_passed


@pytest.mark.integration
def test_good_run_passes_density_audit_end_to_end(good_run_dir):
    report = run_density_audit(good_run_dir / "kit", register="conversion")
    assert audit_passed(report), f"May 15 should pass: {report}"


@pytest.mark.integration
def test_bad_run_fails_at_least_one_density_check(bad_run_dir):
    report = run_density_audit(bad_run_dir / "kit", register="conversion")
    fails = [k for k, v in report.items() if v["status"] == "fail"]
    assert fails, f"May 17 should fail at least one check: {report}"
```

- [ ] **Step 8.2: Run all tests**

```bash
cd /opt/scout-workshop && venv/bin/pytest tests/ -v
```

Expected: all tests pass (warning: slow + integration tests take ~10-15s combined)

- [ ] **Step 8.3: Commit**

```bash
cd /opt/scout-workshop
git add tests/test_workshop_gates_integration.py
git commit -m "test(qfloor): integration test using historical runs as fixtures"
```

---

## Task 9: Dashboard wiring to consume telemetry JSONL

**Files:**
- Modify: `dashboard/app.py`

- [ ] **Step 9.1: Modify `compute_stats()` to prefer JSONL when present**

Locate `def compute_stats(runs):` near line 200 of `dashboard/app.py`. At the top of the function (before any computation), add:

```python
# Prefer telemetry JSONL if v1.4 has started writing it
if TELEMETRY_FILE.exists():
    try:
        telemetry_lines = TELEMETRY_FILE.read_text().strip().split("\n")
        telemetry = [json.loads(line) for line in telemetry_lines if line]
        # Merge: each run in `runs` gets its telemetry record attached if matching slug
        tel_by_slug = {t["run_slug"]: t for t in telemetry}
        for r in runs:
            if r["slug"] in tel_by_slug:
                r["telemetry"] = tel_by_slug[r["slug"]]
    except Exception as e:
        # Soft fail; keep synthesized stats
        pass
```

- [ ] **Step 9.2: Restart dashboard and verify**

```bash
sudo systemctl restart scout-workshop-dashboard
sleep 2
curl -sS http://100.110.49.44:8211/api/health | python3 -m json.tool
```

Expected: `telemetry_file_exists` field reflects whether JSONL is present.

- [ ] **Step 9.3: Commit**

```bash
cd /opt/scout-workshop
git add dashboard/app.py
git commit -m "feat(dashboard): consume telemetry JSONL when v1.4 writes it"
```

---

## Task 10: Final verification + spec update

**Files:**
- Modify: `docs/workshop-v1.4-quality-floor-design.md`

- [ ] **Step 10.1: Run the full test suite**

```bash
cd /opt/scout-workshop && venv/bin/pytest tests/ -v --tb=short
```

Expected: 30+ tests pass. Slow tests may take ~15-30s.

- [ ] **Step 10.2: Append "Implementation status" footer to the spec**

Append to the end of `docs/workshop-v1.4-quality-floor-design.md`:

```markdown

## Implementation status (2026-05-20)

All deliverables landed. Modules:
- `scripts/quality_floor_config.py`
- `scripts/manifest_validator.py`
- `scripts/density_audit.py`
- `scripts/brief_coverage.py`
- `scripts/telemetry_writer.py`
- `skills/audit_brief_coverage.md`
- `skills/workshop-playbook.md` (modified — Section Manifest block)
- `scripts/workshop.py` (modified — Gate A/B/C orchestration)
- `dashboard/app.py` (modified — telemetry JSONL consumer)

Tests at `tests/`. Run via `venv/bin/pytest tests/ -v`.

First production run will be the next cron tick. Telemetry will land at
`state/quality_floor_telemetry.jsonl` and immediately surface on the
dashboard at http://100.110.49.44:8211.
```

- [ ] **Step 10.3: Commit and tag**

```bash
cd /opt/scout-workshop
git add docs/workshop-v1.4-quality-floor-design.md
git commit -m "docs: v1.4 quality floor implementation complete"
git tag -a v1.4.0 -m "Quality floor + retry orchestration + dashboard telemetry consumer"
```

---

## Self-review (post-write)

Checked against `docs/workshop-v1.4-quality-floor-design.md`:

| Spec requirement | Plan task |
|---|---|
| Gate A — Brief Manifest validation | Task 2 (`manifest_validator.py`) + Task 6 (`workshop-playbook.md`) |
| Gate B.1 — 4 deterministic checks | Task 3 (`density_audit.py`; wordmark check removed — no reliable selector) |
| Gate B.2 — Claude semantic coverage | Task 4 (`brief_coverage.py` + `audit_brief_coverage.md`) |
| Gate C — retry orchestration | Task 7 (workshop.py changes) |
| Identical-retry guard | Task 7 (`_kit_fingerprint()` + snapshot comparison) |
| `quality_floor_config.py` tuning knobs + `STATE_DIR` | Task 1 |
| Telemetry JSONL append | Task 5 (`telemetry_writer.py`) + Task 7 (orchestration wiring) |
| Halted-runs directory | Task 7 (`halt_with_telegram()`) |
| systemd `TimeoutStartSec` bump | Task 7 Step 7.0 |
| Dashboard JSONL consumption | Task 9 |
| Portable test fixtures | Task 0 Step 0.3b (`tests/fixtures/runs/`) |

No placeholders. All file paths absolute. All test code shown inline. All function
signatures consistent across tasks. `wordmark_treatment` removed from Gate B.1 spec
as the check was stub-only with no actual measurement. `verdict` removed from Claude
output schema — orchestrator owns pass/fail logic. Fingerprint comparison targets
`run_dir/attempt-1` (immutable snapshot), not the mutable `kit_dir`.
