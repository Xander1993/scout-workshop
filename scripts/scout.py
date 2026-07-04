#!/usr/bin/env python3
"""Scout v1.3 — VPS cron entrypoint for autonomous design reference
discovery. Wraps claude --print to invoke playbook execution with
full Anthropic Max subscription quota, on VPS infrastructure with
unrestricted internet. Replaces Anthropic Routine architecture.

v1.4 (2026-07-02): Firecrawl credit pre-check before the claude call —
16 consecutive runs (06-17 .. 07-02) burned a full Opus session each
just to discover at Bootstrap that the monthly credit pool was empty.
Now we ask Firecrawl first (cheap GET) and skip the session entirely
when starved. Also: playbook is read from the LOCAL checkout instead
of GitHub raw origin/main, which had drifted 352 commits stale.
"""
import datetime
import json
import os
import pathlib
import subprocess
import sys
import urllib.request

PLAYBOOK_PATH = "/opt/scout-workshop/skills/scout-playbook.md"

PROMPT = f"""You are the Scout for the camelotflows.dev autonomous design template generator.

On every run, read (with the Read tool) and follow the playbook at:
{PLAYBOOK_PATH}

That document is your operating procedure. Treat it as authoritative — if
it conflicts with anything you've memorized, the playbook wins. Do not
deviate from its budget caps, batch sizes, or commit message conventions.

When the playbook completes (success, partial, or budget-exhausted), exit
with a Telegram digest as specified in the playbook's "Delivery" section.
This run is on VPS infrastructure (not Anthropic Routine sandbox), so all
network access is unrestricted — Firecrawl, Telegram, source listings
all reachable directly via bash + curl as the playbook describes.
"""


CLAUDE_BIN = "/home/deployer/.nvm/versions/node/v22.22.1/bin/claude"
LOG_DIR = pathlib.Path("/opt/scout-workshop/logs/scout-runs")
ENV_FILE = pathlib.Path("/opt/scout-workshop/.env")
LAST_RUN_STATE = pathlib.Path(
    "/opt/scout-workshop/vault/state/scout-last-run.json")

# One day's sensible spend (stealth scrapes cost ~5 credits each); below
# this the playbook can't do useful work, so don't burn an Opus session.
FIRECRAWL_MIN_CREDITS = 35


def _load_env_file() -> None:
    """Fill os.environ from .env for manual runs. Under systemd the unit's
    EnvironmentFile= already populated the environment; never override."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def firecrawl_remaining_credits():
    """Return remaining Firecrawl credits (int), or None if the check could
    not be performed (missing key / network / unexpected shape) — callers
    treat None as fail-open and proceed with the run as before."""
    key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
    if not key:
        print("scout: FIRECRAWL_API_KEY not set; skipping credit pre-check",
              file=sys.stderr)
        return None
    for endpoint in ("https://api.firecrawl.dev/v2/team/credit-usage",
                     "https://api.firecrawl.dev/v1/team/credit-usage"):
        try:
            req = urllib.request.Request(
                endpoint, headers={"Authorization": f"Bearer {key}"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            data = body.get("data", {})
            # v2 is camelCase, v1 is snake_case — accept either.
            remaining = data.get("remainingCredits",
                                 data.get("remaining_credits"))
            if remaining is not None:
                return int(remaining)
            print(f"scout: credit-usage response missing remaining field "
                  f"({endpoint}); trying next/fail-open", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 — deliberate fail-open
            print(f"scout: credit pre-check error on {endpoint}: {exc}; "
                  "fail-open", file=sys.stderr)
    return None


def notify_telegram(text: str) -> None:
    """Best-effort Telegram send, same bot/chat convention as
    scout_lib.send_telegram (first entry of TELEGRAM_CHAT_IDS)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_ids = os.environ.get("TELEGRAM_CHAT_IDS", "").strip()
    if not token or not chat_ids:
        print("scout: telegram creds missing; skip notify", file=sys.stderr)
        return
    chat_id = chat_ids.split(",")[0].strip()
    try:
        payload = json.dumps({
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as exc:  # noqa: BLE001 — notification is best-effort
        print(f"scout: telegram notify failed: {exc}", file=sys.stderr)


def _persist_last_run(ts: str, status: str, note: str) -> None:
    """Merge a run status + note into scout-last-run.json atomically, preserving
    the counters (references_total etc.) the playbook's Bootstrap relies on.
    Sets references_added_this_run=0 (a skipped/failed run produced nothing).
    Shared by the credit-skip path AND the claude-failure path so the state file
    never stays silently stale after a no-op or failed run."""
    state = {}
    try:
        if LAST_RUN_STATE.exists():
            state = json.loads(LAST_RUN_STATE.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"scout: could not read last-run state: {exc}", file=sys.stderr)
    state["last_run_iso"] = ts
    state["last_run_status"] = status
    state["references_added_this_run"] = 0
    state.setdefault("notes", [])
    state["notes"].insert(0, note)
    try:
        LAST_RUN_STATE.parent.mkdir(parents=True, exist_ok=True)
        tmp = LAST_RUN_STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True),
                       encoding="utf-8")
        tmp.replace(LAST_RUN_STATE)
    except Exception as exc:  # noqa: BLE001
        print(f"scout: could not write last-run state: {exc}",
              file=sys.stderr)


def write_skip_state(remaining: int, ts: str) -> None:
    """Record the credit-starved skip in scout-last-run.json. Status
    'budget_exhausted' (a playbook-schema value) — NOT 'error', so the next
    real run does not trigger the failed-batch retry path."""
    note = (f"skipped: firecrawl credits exhausted ({remaining} remaining) — "
            f"scout.py pre-check at {ts}; no claude session launched, "
            f"0 credits burned")
    _persist_last_run(ts, "budget_exhausted", note)


def classify_claude_failure(log_path: pathlib.Path):
    """Inspect the tail of a failed scout run log and classify WHY the claude
    session failed. Returns (status_slug, owner_reason). Fail-safe: any read
    problem yields the generic ('claude_failed', ...). status_slug is a stable
    value for scout-last-run.json; owner_reason is a human sentence for Telegram."""
    try:
        tail = log_path.read_text(encoding="utf-8", errors="replace")[-8000:].lower()
    except Exception:  # noqa: BLE001
        return ("claude_failed", "claude session failed (run log unreadable).")
    if ("oauth_org_not_allowed" in tail
            or "disabled claude subscription" in tail
            or "subscription access for claude code" in tail):
        return ("claude_org_disabled",
                "the Anthropic org has DISABLED Claude Code subscription access "
                "(oauth_org_not_allowed / HTTP 403). OWNER ACTION: re-enable Claude "
                "Code for the org in the Anthropic Console, or provide an API key.")
    if ('"api_error_status":429' in tail or '"status":429' in tail
            or "rate_limit" in tail or "rate limit" in tail):
        return ("claude_rate_limited",
                "claude hit a rate limit (HTTP 429). Usually transient — the next "
                "scheduled run should recover on its own.")
    if "usage limit reached" in tail or "usage_limit" in tail or "quota" in tail:
        return ("claude_quota_exhausted",
                "claude usage/quota limit reached on the Max plan; it resets on the "
                "plan cycle. No Firecrawl credits were wasted.")
    return ("claude_failed",
            "the claude session exited non-zero; see the run log for the raw error.")


def handle_claude_failure(returncode: int, log_path: pathlib.Path, ts: str) -> str:
    """On a non-zero claude scout session, write a CLASSIFIED failure into
    scout-last-run.json (so it is never silently stale) and send ONE Telegram
    alert to the owner. Returns the status slug. Before this, a claude/org-auth
    outage exited 1 silently — no alert, no state — and the corpus quietly
    stopped growing until someone read the logs by hand."""
    status, reason = classify_claude_failure(log_path)
    note = (f"claude session FAILED (exit {returncode}) at {ts} — {status}: "
            f"{reason} log={log_path.name}")
    _persist_last_run(ts, status, note)
    urgent = "‼️ ACTION NEEDED — " if status == "claude_org_disabled" else ""
    notify_telegram(
        f"❌ Scout {ts}: claude session FAILED (exit {returncode}).\n"
        f"{urgent}{reason}\n"
        f"Nothing scraped this run; scout-last-run.json marked '{status}'. "
        f"Log: {log_path}")
    return status


def main():
    env = os.environ.copy()
    env.setdefault("VAULT_DIR", "/opt/scout-workshop/vault")
    env.pop("CLAUDECODE", None)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = LOG_DIR / f"scout-{ts}.log"

    # ── Firecrawl credit pre-check (v1.4) ─────────────────────────────
    _load_env_file()
    remaining = firecrawl_remaining_credits()
    if remaining is not None and remaining < FIRECRAWL_MIN_CREDITS:
        msg = (f"skipped: firecrawl credits exhausted ({remaining} "
               f"remaining < {FIRECRAWL_MIN_CREDITS} minimum)")
        log_path.write_text(
            f"=== scout.py run start {ts} ===\n{msg}\n"
            f"=== scout.py run end exit=0 (pre-check skip) ===\n",
            encoding="utf-8")
        print(f"scout: {msg}")
        write_skip_state(remaining, ts)
        notify_telegram(
            f"🚫 Scout {ts}: credit-starved — Firecrawl has {remaining} "
            f"credits left (< {FIRECRAWL_MIN_CREDITS} needed for a run). "
            f"Skipped the claude session; nothing scraped, nothing burned. "
            f"Runs resume automatically when credits reset.")
        sys.exit(0)
    if remaining is not None:
        print(f"scout: firecrawl credits ok ({remaining} remaining)")
    # remaining is None → check failed; fail-open (already logged to stderr).

    with log_path.open("wb") as log:
        log.write(f"=== scout.py run start {ts} ===\n".encode())
        log.flush()
        result = subprocess.run(
            # Opus 4.8 + xhigh thinking budget. Pinned per standing directive
            # (max thinking); also stops the cron defaulting to an unavailable
            # model (Fable 5) and failing with rate_limit. NOTE: --effort max is
            # rejected under Claude.ai/Max OAuth (the cron context), so we set the
            # thinking budget via --settings effortLevel:xhigh — the same working
            # workaround already used in workshop.py.
            [CLAUDE_BIN, "--print", "--verbose", "--dangerously-skip-permissions",
             "--model", "claude-opus-4-8", "--settings", '{"effortLevel":"xhigh"}',
             "--output-format", "stream-json", PROMPT],
            cwd="/opt/scout-workshop",
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=7200,
        )
        log.write(f"\n=== scout.py run end exit={result.returncode} ===\n".encode())

    # A non-zero claude exit used to be SILENT: sys.exit(returncode) with no alert
    # and no state write, so an org-auth/claude outage quietly zeroed a day's
    # harvest and left scout-last-run.json stale. Now classify + persist + alert.
    if result.returncode != 0:
        status = handle_claude_failure(result.returncode, log_path, ts)
        print(f"scout: claude session failed (exit {result.returncode}); "
              f"classified '{status}', owner alerted", file=sys.stderr)

    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
