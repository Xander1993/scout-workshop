#!/usr/bin/env python3
"""Reset tokens_used_today and references_added_today in vault state at 06:30 UTC.

Idempotent. Pulls vault, sets the two counters to 0, commits + pushes if changed.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scout_lib import VAULT_DIR, vault_pull, vault_commit, vault_push  # type: ignore

state_path = VAULT_DIR / "state" / "scout-last-run.json"
vault_pull()
state = json.loads(state_path.read_text(encoding="utf-8"))
if state.get("tokens_used_today", 0) == 0 and state.get("references_added_today", 0) == 0:
    print("already reset, no-op")
    sys.exit(0)
state["tokens_used_today"] = 0
state["references_added_today"] = 0
state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
sha = vault_commit("scout: daily budget reset", [state_path])
if sha:
    vault_push()
    print(f"reset committed: {sha}")
