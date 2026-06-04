"""Pure rotation logic for the weekly register cron — pick the next (sub_aesthetic,
kit_type) to generate. No generation side effects; only its own small cursor file."""
from __future__ import annotations
import json
from pathlib import Path

KIT_TYPES = ("editorial-studio", "single-product")
_STATE = Path("/opt/scout-workshop/state/register_queue.json")


def active_pairs() -> list[tuple]:
    """Cross product of ACTIVE (non-vault_pending) sub-aesthetics × kit-types,
    deterministically ordered so the round-robin cursor is stable."""
    from aesthetic_configs import AWWWARDS_CONFIGS as A  # leaf import, no cycle
    subs = sorted(k for k, v in A.items() if not v.get("vault_pending"))
    return [(s, k) for s in subs for k in KIT_TYPES]


def _load(state_path: Path) -> dict:
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {"cursor": -1, "history": []}


def next_pair(state_path: Path = _STATE) -> tuple:
    """Advance the round-robin cursor and return the next (sub, kit). Persists the
    cursor + a bounded history. Recovers from a missing/corrupt state file."""
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
