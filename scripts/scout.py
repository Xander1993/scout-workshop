#!/usr/bin/env python3
"""Scout v1.3 — VPS cron entrypoint for autonomous design reference
discovery. Wraps claude --print to invoke playbook execution with
full Anthropic Max subscription quota, on VPS infrastructure with
unrestricted internet. Replaces Anthropic Routine architecture.
"""
import os
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


def main():
    env = os.environ.copy()
    env.setdefault("VAULT_DIR", "/opt/scout-workshop/vault")
    env.pop("CLAUDECODE", None)

    result = subprocess.run(
        [CLAUDE_BIN, "--print", "--verbose", "--output-format", "stream-json", PROMPT],
        cwd="/opt/scout-workshop",
        env=env,
        stdout=subprocess.DEVNULL,  # discard stream-json chunks; only exit code matters
        timeout=3600,
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
