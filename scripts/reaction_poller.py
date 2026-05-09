#!/usr/bin/env python3
"""
reaction_poller — poll Telegram for emoji reactions on **Workshop** messages.

Each invocation does one short poll and exits. Designed to run from a 5-min
systemd timer. Records each `message_reaction` event whose `(chat_id,
message_id)` matches an entry in `workshop/state/sent_messages.json` (written
by `workshop.py` on every Telegram send) into
`workshop/state/reactions.json`. Reactions on messages Workshop did NOT send
— Scout's deliveries, human messages, anything else on the shared bot — are
counted only as "skipped non-Workshop" in the log and not persisted.

The Telegram Bot API does not allow bots to read arbitrary historical message
text by id, so the prefix-based filter ("messages starting with 🛠️ Workshop:")
cannot be enforced inside the reaction event itself. Instead, Workshop tracks
its own sent message_ids in sent_messages.json and the poller cross-references
against that. The visible WORKSHOP_PREFIX on every message is for human
readers and forward-compatibility, not the filter mechanism.

v1.0 logs only — Workshop behavior is not yet driven by reactions (exploration
mode adjustment is v1.1 work).

Telegram API notes:
- `getUpdates` is the only way to read reactions; the Bot API has no webhook
  for them in v1.0 of our stack.
- We pass `allowed_updates=["message_reaction"]` to scope updates fetched.
- `timeout=0` (short poll, not long-poll) — the systemd timer is the pacing
  mechanism, not the Telegram server.

Concurrency contract: a single getUpdates consumer per bot token. As of
Phase 0 audit, Workshop's reaction_poller is the ONLY getUpdates consumer.
If another consumer is added, both start losing updates — see ADR-5.
"""
from __future__ import annotations

import json
import logging
import shutil
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import scout_lib as sl  # noqa: E402

PROJECT_ROOT = HERE.parent
STATE_DIR = PROJECT_ROOT / "workshop" / "state"
LOGS_DIR = PROJECT_ROOT / "logs"
REACTIONS_FILE = STATE_DIR / "reactions.json"
REACTIONS_EXAMPLE = STATE_DIR / "reactions.json.example"
SENT_MESSAGES_FILE = STATE_DIR / "sent_messages.json"

POLL_TIMEOUT_S = 15

log = logging.getLogger("reaction-poller")


def _setup_logging() -> None:
    log.setLevel(logging.INFO)
    if log.handlers:
        return
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%dT%H:%M:%SZ")
    fmt.converter = time.gmtime
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    log.addHandler(sh)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(LOGS_DIR / "reaction-poller.log")
    fh.setFormatter(fmt)
    log.addHandler(fh)


def load_state() -> dict[str, Any]:
    """Read reactions.json. Bootstrap from .example on first run."""
    if not REACTIONS_FILE.exists():
        if not REACTIONS_EXAMPLE.exists():
            raise FileNotFoundError(
                f"{REACTIONS_FILE} missing and {REACTIONS_EXAMPLE} not available"
            )
        shutil.copy(REACTIONS_EXAMPLE, REACTIONS_FILE)
        log.info("bootstrapped reactions.json from reactions.json.example")
    return json.loads(REACTIONS_FILE.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any]) -> None:
    """Atomic-ish write of reactions.json."""
    tmp = REACTIONS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    tmp.replace(REACTIONS_FILE)


def load_workshop_messages() -> set[tuple[int, int]]:
    """Read workshop/state/sent_messages.json (written by workshop.py on every
    Telegram send) and return a set of (chat_id, message_id) tuples. Reactions
    on message_ids NOT in this set are skipped — they belong to Scout or any
    other consumer of the shared bot token, not to Workshop."""
    if not SENT_MESSAGES_FILE.exists():
        return set()
    try:
        data = json.loads(SENT_MESSAGES_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("could not parse %s: %s", SENT_MESSAGES_FILE, e)
        return set()
    out: set[tuple[int, int]] = set()
    for m in data.get("messages") or []:
        try:
            out.add((int(m["chat_id"]), int(m["message_id"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def fetch_updates(token: str, offset: int) -> list[dict[str, Any]]:
    """Single short-poll getUpdates call. Returns the `result` list verbatim."""
    import requests
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params = {
        "offset": offset,
        "allowed_updates": json.dumps(["message_reaction"]),
        "timeout": 0,
    }
    r = requests.get(url, params=params, timeout=POLL_TIMEOUT_S)
    r.raise_for_status()
    body = r.json()
    if not body.get("ok"):
        raise RuntimeError(f"getUpdates not ok: {body!r}")
    return body.get("result") or []


def classify_delta(old: list[str], new: list[str]) -> str:
    """Tag the reaction event so consumers don't have to compare lists later."""
    if old and not new:
        return "remove:" + ",".join(old)
    if new and not old:
        return "add:" + ",".join(new)
    if set(old) == set(new):
        return "noop"
    return f"change:{','.join(old)}->{','.join(new)}"


def record_event(
    update: dict[str, Any],
    workshop_msgs: set[tuple[int, int]],
) -> dict[str, Any] | None:
    """Convert a Telegram update into a reaction record. Returns None when:
      - the update is not a `message_reaction` event, or
      - the (chat_id, message_id) is not in `workshop_msgs` (i.e., the reaction
        is on a message Workshop didn't send — could be Scout's, or a human's,
        or any other consumer of the shared bot token)."""
    mr = update.get("message_reaction")
    if not mr:
        return None
    chat = mr.get("chat", {}) or {}
    chat_id = chat.get("id")
    message_id = mr.get("message_id")
    try:
        key = (int(chat_id), int(message_id))
    except (TypeError, ValueError):
        return None
    if key not in workshop_msgs:
        return None
    user = mr.get("user") or {}
    old = [e.get("emoji") for e in (mr.get("old_reaction") or []) if e.get("type") == "emoji"]
    new = [e.get("emoji") for e in (mr.get("new_reaction") or []) if e.get("type") == "emoji"]
    return {
        "update_id": update.get("update_id"),
        "chat_id": chat_id,
        "message_id": message_id,
        "user_id": user.get("id"),
        "user_name": user.get("first_name") or user.get("username"),
        "date": mr.get("date"),
        "old_reaction": old,
        "new_reaction": new,
        "delta": classify_delta(old, new),
    }


def main() -> int:
    _setup_logging()
    try:
        state = load_state()
    except FileNotFoundError as e:
        log.error("%s", e)
        return 1
    last_uid = int(state.get("last_update_id") or 0)
    offset = last_uid + 1 if last_uid else 0

    env = sl.load_env()
    token = env.get("TELEGRAM_BOT_TOKEN")
    if not token:
        log.error("TELEGRAM_BOT_TOKEN not set")
        return 1

    try:
        updates = fetch_updates(token, offset)
    except Exception as e:
        log.error("getUpdates failed: %s", e)
        return 1

    workshop_msgs = load_workshop_messages()
    log.info("workshop sent_messages tracked: %d", len(workshop_msgs))

    new_records: list[dict[str, Any]] = []
    skipped_non_workshop = 0
    max_uid = last_uid
    for u in updates:
        uid = int(u.get("update_id") or 0)
        if uid > max_uid:
            max_uid = uid
        if u.get("message_reaction") and not u.get("message_reaction").get("message_id") is None:
            rec = record_event(u, workshop_msgs)
            if rec:
                new_records.append(rec)
            else:
                # reaction event on a non-Workshop message (Scout / human / other)
                skipped_non_workshop += 1

    if new_records:
        state.setdefault("reactions", []).extend(new_records)
        log.info("recorded %d new Workshop reactions (skipped %d non-Workshop)",
                 len(new_records), skipped_non_workshop)
    else:
        log.info("no new Workshop reactions (skipped %d non-Workshop)", skipped_non_workshop)
    state["last_update_id"] = max_uid
    save_state(state)
    log.info("poll done: last_update_id=%d", max_uid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
