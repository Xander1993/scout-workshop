#!/usr/bin/env python3
"""Scout v1.3 — VPS cron entrypoint for autonomous design reference
discovery. Wraps claude --print to invoke playbook execution with
full Anthropic Max subscription quota, on VPS infrastructure with
unrestricted internet. Replaces Anthropic Routine architecture.
"""
import datetime
import os
import pathlib
import subprocess
import sys

PLAYBOOK_RAW_URL = (
    "https://raw.githubusercontent.com/Xander1993/scout-workshop/"
    "main/skills/scout-playbook.md"
)

PROMPT = f"""You are the Scout for the camelotflows.dev autonomous design template generator.

On every run, fetch and follow the playbook at:
{PLAYBOOK_RAW_URL}

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


def main():
    env = os.environ.copy()
    env.setdefault("VAULT_DIR", "/opt/scout-workshop/vault")
    env.pop("CLAUDECODE", None)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = LOG_DIR / f"scout-{ts}.log"

    with log_path.open("wb") as log:
        log.write(f"=== scout.py run start {ts} ===\n".encode())
        log.flush()
        result = subprocess.run(
            [CLAUDE_BIN, "--print", "--verbose", "--dangerously-skip-permissions", "--output-format", "stream-json", PROMPT],
            cwd="/opt/scout-workshop",
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=7200,
        )
        log.write(f"\n=== scout.py run end exit={result.returncode} ===\n".encode())

    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
