# Workshop v1.5 — Phase 2 Implementation Plan (live cron flip to the premium register)

> **For agentic workers:** TDD, bite-sized steps, frequent commits. Each component ships working + tested on its own.

**Goal:** Make the dormant awwwards/premium register the workshop's LIVE weekly output — safely — by building the three prerequisites the Phase 1b audit flagged, then flipping the cron behind a final audit.

**Architecture:** A new `--register-weekly` entrypoint round-robins the ACTIVE sub-aesthetics × kit-types, calls the existing gated `run_awwwards_oneshot`, and alerts on the result. The dashboard learns to read `verdict.json` / `-flagged`. Only after all three land + a 4-agent audit do we change one `ExecStart` line. The conversion path stays runnable for instant rollback.

**Tech Stack:** Python 3 (stdlib + existing scout_lib), systemd, the existing Telegram delivery helper, the existing Flask-ish dashboard (`dashboard/app.py` + `static/`).

---

## Context the engineer needs

- The weekly cron is `systemd/workshop.service` → `ExecStart=/opt/scout-workshop/venv/bin/python /opt/scout-workshop/scripts/workshop.py` (NO args → conversion/anchor path). The unit at `/etc/systemd/system/workshop.service` is a symlink to that file. `workshop.timer` fires Sun 01:00 UTC. `MemoryMax=4G`, `TimeoutStartSec=7500`.
- `scripts/workshop.py`: `main()` (line ~1390) uses argparse; `--awwwards-oneshot SUB KIT` (nargs=2) → `run_awwwards_oneshot(sub, kit)` and early-returns (line ~1406). `--dry-run` exists. We ADD `--register-weekly`.
- `run_awwwards_oneshot(sub_aesthetic, kit_type) -> int` is the gated per-run entry: concept → brief → kit → images → screenshots → `run_quality_gate` → retry-once → `_finalize_awwwards_verdict` (PASS stays; else writes `DO_NOT_DEPLOY` + renames run dir to `…-flagged`). Returns 0 on a shipped kit (passed OR flagged), 1 only when attempt-0 produced no kit at all.
- `aesthetic_configs.AWWWARDS_CONFIGS`: 3 ACTIVE (`sun-baked`, `warm-earth`, `editorial-mid-century`; `vault_pending=False`; family `restrained-monumental`) and 2 PENDING (`acid-tech`, `cool-jewel`; `vault_pending=True`). `kit_types` is `None` → both kit-types (`editorial-studio`, `single-product`) apply.
- Kit-type list lives in `KIT_REQUIRED_FILES_BY_KIT_TYPE` (keys = the two kit-types).
- Telemetry: `state/quality_floor_telemetry.jsonl`. Diversity store: `state/structural_signatures.json`.
- The conversion path delivers via an existing `deliver(...)`/Telegram helper in `workshop.py` (reuse its mechanism for the alert).

---

## Component A — Register weekly iterator (`--register-weekly`)

**Files:**
- Modify: `scripts/workshop.py` (add `run_register_weekly()`, register `--register-weekly`, dispatch)
- Create: `scripts/register_schedule.py` (pure rotation logic — picks the next (sub, kit), no side effects beyond its state file)
- Test: `tests/test_register_schedule.py`

**Design:** Round-robin over the cross product of ACTIVE sub-aesthetics × kit-types, persisting a cursor in `state/register_queue.json` so each weekly run advances to a different (sub, kit). Skip `vault_pending`. If the chosen pair can't generate (corpus too thin → oneshot returns 1), advance to the next viable pair within the same invocation (bounded by the number of pairs, so a fully-starved set fails loudly once, not infinitely).

- [ ] **A1. Failing test — enumeration excludes pending + covers both kit-types**

```python
# tests/test_register_schedule.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import register_schedule as rs

def test_active_pairs_excludes_vault_pending():
    pairs = rs.active_pairs()
    subs = {p[0] for p in pairs}
    assert "sun-baked" in subs and "warm-earth" in subs and "editorial-mid-century" in subs
    assert "acid-tech" not in subs and "cool-jewel" not in subs       # vault_pending
    kits = {p[1] for p in pairs}
    assert kits == {"editorial-studio", "single-product"}
    assert len(pairs) == 6                                            # 3 active × 2 kit-types
```

- [ ] **A2. Run → FAIL** (`venv/bin/pytest tests/test_register_schedule.py -v`) — `register_schedule` missing.

- [ ] **A3. Implement enumeration**

```python
# scripts/register_schedule.py
"""Pure rotation logic for the weekly register cron — pick the next (sub_aesthetic,
kit_type) to generate. No generation side effects; only its own cursor file."""
from __future__ import annotations
import json
from pathlib import Path

KIT_TYPES = ("editorial-studio", "single-product")
_STATE = Path("/opt/scout-workshop/state/register_queue.json")


def active_pairs() -> list[tuple]:
    from aesthetic_configs import AWWWARDS_CONFIGS as A
    subs = [k for k, v in A.items() if not v.get("vault_pending")]
    return [(s, k) for s in sorted(subs) for k in KIT_TYPES]


def _load(state_path: Path) -> dict:
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {"cursor": -1, "history": []}


def next_pair(state_path: Path = _STATE) -> tuple:
    """Advance the round-robin cursor and return the next (sub, kit). Persists."""
    pairs = active_pairs()
    if not pairs:
        raise RuntimeError("no active sub-aesthetics — corpus all vault_pending")
    st = _load(state_path)
    cursor = (int(st.get("cursor", -1)) + 1) % len(pairs)
    st["cursor"] = cursor
    pair = pairs[cursor]
    st.setdefault("history", []).append(list(pair))
    st["history"] = st["history"][-50:]
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(st, indent=2), encoding="utf-8")
    return pair
```

- [ ] **A4. Run → PASS.**

- [ ] **A5. Failing test — cursor rotates + persists across calls**

```python
def test_next_pair_rotates_and_persists(tmp_path):
    sp = tmp_path / "q.json"
    seen = [rs.next_pair(sp) for _ in range(7)]
    pairs = rs.active_pairs()
    assert seen[0] == pairs[0] and seen[6] == pairs[0]               # wrapped after 6
    assert len(set(seen[:6])) == 6                                   # all distinct in one cycle
    assert sp.exists()
```

- [ ] **A6. Run → PASS** (logic already supports it).

- [ ] **A7. Add `run_register_weekly()` + CLI wiring in `scripts/workshop.py`** (after `run_awwwards_oneshot`)

```python
def run_register_weekly() -> int:
    """Weekly cron entry: pick the next (sub, kit) in rotation and run the gated
    oneshot. On corpus-thin failure (oneshot returns 1) advance to the next viable
    pair, bounded by the number of pairs so a fully-starved set fails once."""
    import register_schedule
    pairs = register_schedule.active_pairs()
    for _ in range(len(pairs)):
        sub, kit = register_schedule.next_pair()
        log.info("register-weekly: attempting %s / %s", sub, kit)
        rc = run_awwwards_oneshot(sub, kit)
        if rc == 0:
            return 0
        log.warning("register-weekly: %s/%s did not ship (rc=%d) — trying next pair", sub, kit, rc)
    log.error("register-weekly: no viable pair shipped a kit this run")
    return 1
```

In `main()` argparse block add:
```python
    p.add_argument("--register-weekly", action="store_true",
                   help="weekly register cron: round-robin the active sub-aesthetics × kit-types")
```
In the early-dispatch (next to the `--awwwards-oneshot` return):
```python
    if args.register_weekly:
        return run_register_weekly()
```

- [ ] **A8. Smoke test** — `venv/bin/python scripts/workshop.py --register-weekly --help` parses; and a dry enumeration import works. Do NOT run a real generation in the unit test (expensive). Commit.

```bash
git add scripts/register_schedule.py scripts/workshop.py tests/test_register_schedule.py
git commit -m "feat(register): weekly round-robin iterator over active aesthetics × kit-types"
```

---

## Component B — Dashboard flagged-kit awareness

**Files:**
- Modify: `dashboard/app.py` (read `verdict.json` + detect `-flagged`)
- Modify: `dashboard/static/*` (surface a flagged column / badge — match existing render)
- Test: `tests/test_dashboard_verdict.py`

**Design:** For each run dir, if `verdict.json` exists, expose `{passed, craft_verdict, craft_scores, reasons, flagged}` (flagged = dir name ends `-flagged` OR a `DO_NOT_DEPLOY` sentinel exists). Add a column/badge. Keep the existing conversion `audit_status` rendering intact (both kinds of runs coexist).

- [ ] **B1. Failing test — verdict parser**

```python
# tests/test_dashboard_verdict.py
import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "dashboard"))
import app

def test_read_verdict_passed(tmp_path):
    (tmp_path / "verdict.json").write_text(json.dumps({
        "passed": True, "reasons": [],
        "craft": {"verdict": "pass", "scores": {"monumentality": 3}}}), encoding="utf-8")
    v = app.read_register_verdict(tmp_path)
    assert v["passed"] is True and v["flagged"] is False and v["craft_verdict"] == "pass"

def test_read_verdict_flagged(tmp_path):
    d = tmp_path / "2026-06-04T00-00-00Z-awwwards-sun-baked-single-product-flagged"
    d.mkdir()
    (d / "verdict.json").write_text(json.dumps({"passed": False, "reasons": ["craft below_bar"],
                                                "craft": {"verdict": "below_bar", "scores": {}}}), encoding="utf-8")
    (d / "DO_NOT_DEPLOY").write_text("x", encoding="utf-8")
    v = app.read_register_verdict(d)
    assert v["passed"] is False and v["flagged"] is True

def test_read_verdict_absent_is_none(tmp_path):
    assert app.read_register_verdict(tmp_path) is None
```

- [ ] **B2. Run → FAIL.**
- [ ] **B3. Implement `read_register_verdict(run_dir)` in `dashboard/app.py`** (returns the dict above or None) and call it in the run-listing builder; add `flagged`/`craft_verdict` to each run's serialized record.
- [ ] **B4. Run → PASS.**
- [ ] **B5. Surface in the UI** — add a "Verdict" badge to the run row in `dashboard/static/` (passed = green, flagged = red with reasons tooltip). Match existing markup/CSS. Manually verify the dashboard still renders (`curl` the index).
- [ ] **B6. Commit.**

---

## Component C — Flagged-ship alert (Telegram)

**Files:**
- Modify: `scripts/workshop.py` (`run_register_weekly` → send a result alert)
- Test: `tests/test_register_alert.py` (alert payload built correctly; delivery injected)

**Design:** After the oneshot returns, send ONE Telegram message: PASS → "✅ shipped <sub>/<kit> (craft sum N)" + the home screenshot; FLAGGED → "⚠️ flagged <sub>/<kit>: <reasons>" + screenshot. Reuse the existing Telegram delivery helper; inject it so the test doesn't hit the network.

- [ ] **C1. Failing test — alert text for pass vs flagged** (build a `_register_alert_text(run_dir, sub, kit) -> (text, shot_path)` pure helper; assert it reads `verdict.json` + the `-flagged` suffix).
- [ ] **C2. Run → FAIL.**
- [ ] **C3. Implement `_register_alert_text` + call the Telegram helper in `run_register_weekly`** (best-effort; wrap in try/except so a delivery failure never fails the run).
- [ ] **C4. Run → PASS. Commit.**

---

## Component D — The flip (CONSEQUENTIAL — gated on a passing 4-agent audit + user confirm)

**Files:** `systemd/workshop.service` (ExecStart), then `daemon-reload`.

- [ ] **D1.** Full suite green in the worktree; merge `awwwards-v1.5-p2` → main; push.
- [ ] **D2.** 4-agent implementation audit of A–C (iterator rotation + corpus-skip; dashboard parsing + no regression to conversion rows; alert best-effort + no run-failure path). Fix until agents agree.
- [ ] **D3.** Dry validation: `workshop.py --register-weekly` end-to-end on the host generates a real kit, gates it, and (on a deliberately-failing kit) ships `-flagged` + alerts. Confirm wall-clock < `TimeoutStartSec` even with a retry.
- [ ] **D4. USER CONFIRM, then flip:** change `ExecStart` to append `--register-weekly`; `systemctl daemon-reload`. **Rollback** = revert that one line + `daemon-reload` (conversion path is untouched and still works).
- [ ] **D5.** Observe the first live Sunday run via the dashboard + telemetry + alert.

---

## Self-review checks
- Iterator NEVER touches `vault_pending` aesthetics (A1 asserts). Corpus-thin → bounded skip, loud single failure (A7), not an infinite loop.
- Dashboard change is ADDITIVE — conversion `audit_status` rows still render (B5 manual check).
- Alert is best-effort — a Telegram outage cannot fail or block a weekly run (C3).
- The flip is ONE reversible line behind an audit + user confirm (D4). Conversion path stays runnable.
- No new secret surfaces: `state/register_queue.json` holds only (sub, kit) names.
