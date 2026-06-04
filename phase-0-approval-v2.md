# Phase 0 Plan approved with answers + operational hardening

Plan structure correct. Cross-section findings (Telegram in §1/§2/§6) are good catches. Five answers below, plus operational hardening from a peer review that surfaced several deployment gaps. Read all of this before starting Phase 1.

## Answers to 5 open questions

**Q1 — Dirty tree:** Discard. `git checkout logs/day-2-bootstrap-act.log`. The file is execution log, not deliverable. Add `logs/*-act.log` to .gitignore in commit 1 (housekeeping) so this can't recur.

**Q2 — Scout's other Telegram call sites:** YES, patch all three. Silent invisible failure at budget-exhausted / no-candidates / unhandled-exception is worse than no autonomy.

Architectural simplification: ONE file `vault/state/scout-digest-latest.md` for all four message types. Daemon doesn't parse types — reads whatever text is in the file, delivers, deletes. Single code path.

Patches in skills/scout-playbook.md:

- §1 budget-exhausted: replace "exit immediately with a Telegram message: 🚫 Scout: budget exhausted for today. Resuming tomorrow." with "Write status text to `vault/state/scout-digest-latest.md`: '🚫 Scout: budget exhausted for today. Resuming tomorrow.' Commit + push. Exit cleanly. The VPS daemon will deliver to Telegram on its next 10-minute tick."

- §2 dedup zero-candidates: replace "send a Telegram message and exit cleanly: ℹ️ Scout: no new candidates..." with "Write status to `vault/state/scout-digest-latest.md`: 'ℹ️ Scout: no new candidates this run. Source feeds returned all-known URLs.' Commit + push. Exit cleanly."

- §6 unhandled exception: replace "send Telegram with the traceback (truncated 1500 chars), exit non-zero" with "Write traceback (truncated 1500 chars) to `vault/state/scout-digest-latest.md` with prefix '❌ Scout: unhandled exception\n\n<traceback>'. Best-effort commit + push (if commit/push fails inside exception handler, log to stderr, exit non-zero anyway)."

**Q3 — Mode distribution:** Change `process_one()` signature to `(ok, point_id, mode)`. In Branch C: propagate mode from `embed_with_mode()` tuple. In Branch A/B (already indexed): return `mode = "skipped-already-indexed"` or `None`. Daemon's mode aggregation only counts newly-embedded.

**Q4 — Daemon push retry:** YES. Reuse `vault_push(max_attempts=3)` from scout_lib in `deliver_pending_digest()` cleanup commit. Don't reimplement.

If push fails after Telegram delivered: log error, do NOT crash daemon. Worst case is rare double-send on next tick — accepted v1.1 risk documented in code comment.

**Q5 — Commit grouping:** Split into two commits. Insurance against partial rollout. If commit 2 fails push, commit 1 (branch fix) is still on origin and Scout's next run commits to main correctly.

## CRITICAL operational pre-flight (must pass before Phase 1 starts)

These four checks gate Phase 1 entirely. If any fails, abort and report — do NOT proceed to patching.

**Pre-flight 1: Working directory + repo identity**

```bash
cd /opt/scout-workshop
pwd   # must be /opt/scout-workshop, NOT .../vault
ls -la skills/scout-playbook.md scripts/ingest_daemon.py
git remote -v   # must show Xander1993/scout-workshop, NOT scout-workshop-vault
```

If any output unexpected — STOP. We're in the wrong directory or repo state is unexpected.

**Pre-flight 2: Branch protection sanity**

```bash
cd /opt/scout-workshop
git fetch origin
git push origin main --dry-run
```

If `--dry-run` reports protection rules blocking direct push — STOP and report. User will need to either disable protection temporarily or grant admin override before patches can land.

Expected: "Everything up-to-date" or a normal push preview without errors.

**Pre-flight 3: Telegram bot reachability from VPS**

This is the load-bearing check. The entire v1.1 architecture assumes daemon-side Telegram delivery works. If bot is unreachable for any reason (token expired, network policy change, DNS), the patches don't help — they just relocate silent failure.

```bash
source /opt/scout-workshop/.env
response=$(curl -sS "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe")
if echo "$response" | grep -q '"ok":true'; then
    echo "Telegram bot reachable from VPS — proceeding"
else
    echo "ABORT: Telegram bot not reachable. Response: $response"
    exit 1
fi
```

If this fails — STOP. Do not patch anything. Report the response body so we can debug (token rotation, firewall, DNS, etc).

**Pre-flight 4: Resume guard (idempotency for re-runs)**

If Phase 1 is being re-run after partial failure (e.g., commit 1 succeeded but commit 2 broke mid-flight), don't try to redo commit 1 — go straight to commit 2.

```bash
cd /opt/scout-workshop
git fetch origin
commit_1_present=$(git log origin/main --oneline -10 | grep -c "v1.1: branch fix" || echo "0")
if [ "$commit_1_present" -ge "1" ]; then
    echo "v1.1 commit 1 already on origin/main — skipping cleanup + commit 1, jumping to commit 2"
    # Skip Step 1 (pre-flight cleanup) and Step 2 (commit 1)
    # Proceed directly to Step 3 (commit 2)
fi
```

## Phase 1 Act — settings updated

Earlier I said Sonnet 4.6 / medium / brief. Updated based on review feedback:

**New settings: Opus 4.7, effort medium, thinking extended.**

Rationale: §3a Firecrawl scrape has a JSON block at lines 91-101 followed by Python defensive screenshot handler at lines 102-117 that MUST remain untouched. Sonnet with brief thinking risks eating the defensive handler along with the JSON block during str_replace. Opus with extended thinking is more careful with surrounding-context preservation. Token cost difference is negligible against the cost of a botched edit.

The user has Claude Max 20×, quota allows.

## Phase 1 Act — execution order

Apply patches in this order. Each step has its own verification.

**Step 1: Pre-flight cleanup**

```bash
cd /opt/scout-workshop

# Discard dirty file
git checkout logs/day-2-bootstrap-act.log

# Pull origin
git pull origin main

# Verify clean tree
git status   # expect: "nothing to commit, working tree clean"

# Sanity check pull worked (budget bump committed in 8c16276 should now be in working tree)
grep "tokens_used_today" skills/scout-playbook.md   # expect: line containing "100000"

# Verify process_one() call sites count BEFORE signature change
grep -n "process_one(" scripts/ingest_daemon.py
# Expected: 2 occurrences (definition + 1 call site in run_once)
# If MORE than 2 — STOP. There are call sites we missed in planning.
# If LESS than 2 — STOP. State is unexpected.
```

**Step 2: Commit 1 — branch fix + gitignore chores**

Patches in skills/scout-playbook.md:

- §3d: append branch instruction paragraph after existing "Commit `note.md` and `screenshot.png` together." line. New paragraph: explicit `git checkout main && git pull origin main` requirement, prohibition on `claude/*` feature branches, prohibition on opening PRs, mandate to `git push origin main`. (~12 lines added.)

- §4 close-out: replace single line "Push vault." with multi-line "Push vault to main with retry-on-conflict protocol" block — the 3-attempt `git pull --rebase --autostash` / `git push origin main` for-loop, plus abort-on-merge-conflict rule. (~14 lines added, 1 line replaced.)

Update .gitignore:
- Add line: `logs/*-act.log`
- Add line: `day-2-v1-1-patches.md`

Commit:
```bash
git add skills/scout-playbook.md .gitignore
git commit -m "v1.1: branch fix + gitignore chores

- §3d/§4 explicit instructions to commit direct to main, no feature branches
- §4 retry-on-conflict push protocol embedded in playbook
- .gitignore: logs/*-act.log (catches future Act-phase log accidents)
- .gitignore: day-2-v1-1-patches.md (instruction document, not deliverable)"

# Push with retry-on-conflict
for attempt in 1 2 3; do
    git pull --rebase --autostash origin main && \
    git push origin main && \
    break
    echo "push attempt $attempt failed, retrying in $((attempt * 5))s..."
    sleep $((attempt * 5))
done
```

Verify commit 1 landed:
```bash
git fetch origin
git log origin/main --oneline -3
# Top line should be: <new-sha> v1.1: branch fix + gitignore chores
```

**Step 3: Commit 2 — Firecrawl stealth + Telegram migration + daemon changes**

Patches in skills/scout-playbook.md (10 sites):

Firecrawl stealth (5 sites):
- §2 top of section: insert enforcement paragraph
- §2a Awwwards: replace block with explicit POST + proxy:stealth
- §2b Dribbble: replace block with explicit POST + proxy:stealth
- §2c WordPress: replace block with explicit POST + proxy:stealth
- §3a per-candidate: add "proxy": "stealth" line to JSON, append commentary about residential IP. **CRITICAL: preserve Python defensive screenshot handler at lines 102-117 (or wherever they end up after pull) verbatim. The handler block starts after the JSON closing fence and includes `screenshot = data["screenshot"]` and the isinstance/decode logic.** Use view first to confirm exact line numbers post-pull, then str_replace ONLY the JSON object body — not the surrounding context.

Telegram migration to vault file (4 sites):
- §1 line ~30: replace budget-exhausted Telegram call with vault file write
- §2 line ~62: replace zero-candidates Telegram call with vault file write
- §5 entire section: replace "Telegram digest" with "Digest hand-off" — describes writing to scout-digest-latest.md, daemon picks up and delivers
- §6 line ~279: replace exception handler Telegram call with vault file write

§6 Firecrawl 5xx clarification (1 site):
- Replace bullet to add proxy:stealth retry note + "Do NOT fall back to Web Fetch / WebSearch" prohibition

Patches in scripts/ingest_daemon.py:

- Change `process_one()` signature: `def process_one(note_path, dry_run) -> tuple[bool, str | None, str | None]:` Returns `(ok, point_id, mode)`. In Branch A/B return `mode = "skipped-already-indexed"`. In Branch C unpack mode from `embed_with_mode()` and propagate.
- Update call site in `run_once()`: unpack 3-tuple, accumulate in `summary["modes"]`.
- Add `import json` if not already present.
- Add new function `deliver_pending_digest(summary)` between `run_once()` and `main()`. Function reads `vault/state/scout-digest-latest.md`, augments with ingestion stats from summary (succeeded count, mode distribution, Qdrant total via `qdrant_client().count(COLLECTION_NAME, exact=True).count`), POSTs via `send_telegram()`. On 200 OK: deletes file, calls `vault_commit("ingest: telegram digest delivered " + iso_now(), [path])`, calls `vault_push(max_attempts=3)`. On failure: increments counter in `/opt/scout-workshop/state/digest-delivery-failures.json`, gives up after 3 consecutive same-content failures.
- Call `deliver_pending_digest(summary)` at end of `run_once()` AFTER the existing vault_commit/vault_push for embed updates, but BEFORE return summary. Call it regardless of pending count (Scout may have committed a digest with 0 references).

Commit:
```bash
git add skills/scout-playbook.md scripts/ingest_daemon.py
git commit -m "v1.1: Firecrawl stealth + Telegram migration to daemon

Firecrawl stealth (§2/§3a/§6):
- Explicit POST blocks with proxy:stealth for residential IP routing
- §6 prohibits Web Fetch / WebSearch fallback explicitly
- 4 stealth occurrences total (§2a, §2b, §2c, §3a)

Telegram migration to daemon-side delivery:
- Routine env doesn't allow api.telegram.org egress
- §1, §2, §5, §6 now write digest/status to vault/state/scout-digest-latest.md
- Daemon's deliver_pending_digest() reads file, augments with
  ingestion stats, POSTs to Telegram, deletes file
- Single file for all message types (digest/budget/dedup/exception)

Daemon changes:
- process_one() signature: (ok, pid, mode) — mode tracking propagated
- run_once() accumulates summary[\"modes\"] distribution
- New deliver_pending_digest() with vault_push retry
- Daemon-local failure counter at state/digest-delivery-failures.json"

# Push with retry-on-conflict
for attempt in 1 2 3; do
    git pull --rebase --autostash origin main && \
    git push origin main && \
    break
    echo "push attempt $attempt failed, retrying in $((attempt * 5))s..."
    sleep $((attempt * 5))
done
```

Verify commit 2 landed:
```bash
git fetch origin
git log origin/main --oneline -3
# Top line should be: <sha> v1.1: Firecrawl stealth + Telegram migration to daemon
# Below: <sha> v1.1: branch fix + gitignore chores
# Below: <sha> Increase budget_tokens_per_run to 100000
```

## Phase 2 Verify — Opus 4.7, effort high, thinking extended

After Phase 1 reports complete, switch settings to Opus 4.7 / high / extended and run all checks:

**Static file checks (local):**

```bash
cd /opt/scout-workshop

# Branch fix patches
grep -c "git checkout main" skills/scout-playbook.md   # expect: ≥1
grep -c "Do NOT create a feature branch" skills/scout-playbook.md   # expect: 1
grep -c "git push origin main" skills/scout-playbook.md   # expect: ≥2 (in §3d and §4)

# Firecrawl stealth
grep -c "proxy.*stealth" skills/scout-playbook.md   # expect: 4

# Telegram migration
grep -c "scout-digest-latest.md" skills/scout-playbook.md   # expect: 4 (one in §1, §2, §5, §6)
grep -c "## 5. Telegram digest" skills/scout-playbook.md   # expect: 0 (replaced)
grep -c "## 5. Digest hand-off" skills/scout-playbook.md   # expect: 1

# Daemon changes
grep -n "deliver_pending_digest" scripts/ingest_daemon.py   # expect: definition + call site (≥2 lines)
grep -n "scout-digest-latest.md" scripts/ingest_daemon.py   # expect: ≥1 line
grep -c "vault_push.*max_attempts=3" scripts/ingest_daemon.py   # expect: ≥1
```

**Daemon imports work (no syntax errors):**

```bash
/opt/scout-workshop/venv/bin/python -c "from scripts.ingest_daemon import run_once, deliver_pending_digest; print('imports ok')"
```

**Daemon dry-run (idempotency check):**

```bash
/opt/scout-workshop/venv/bin/python scripts/ingest_daemon.py --dry-run --once
/opt/scout-workshop/venv/bin/python scripts/ingest_daemon.py --dry-run --once
# Both should report no errors. Second run should be idempotent (no double-actions).
```

**Daemon timer status (confirm picking up new code):**

```bash
sudo systemctl status scout-ingest.timer scout-budget-reset.timer
# Both should be active, last trigger recent, no errors

journalctl -u scout-ingest.service --since "15 minutes ago" --no-pager | tail -30
# Recent ticks should show no import errors, no exceptions from new deliver_pending_digest path
```

If you see import errors in journalctl, or service started failing after the patches landed — STOP and report. Daemon may need explicit attention.

**CDN cache propagation check (gates manual Routine trigger):**

```bash
sleep 60   # initial grace
for attempt in 1 2 3; do
    propagated=$(curl -s "https://raw.githubusercontent.com/Xander1993/scout-workshop/main/skills/scout-playbook.md" | grep -cE 'proxy.*stealth')
    if [ "$propagated" = "4" ]; then
        echo "CDN propagated v1.1 ($propagated/4 stealth refs visible)"
        break
    fi
    echo "Attempt $attempt: CDN cache showing $propagated/4 stealth refs. Waiting 90s..."
    sleep 90
done
if [ "$propagated" != "4" ]; then
    echo "WARNING: After 4.5 min wait, CDN still serving stale playbook."
    echo "User should wait longer before triggering Scout manually,"
    echo "OR force GitHub raw URL refresh by appending ?cachebust=$(date +%s)."
fi
```

**Write report:**

Create `logs/day-2-v1.1-bootstrap-report.md` with:
- All static check results (pass/fail per check)
- Both commit SHAs
- CDN propagation status
- daemon journalctl excerpt
- Reference to the v1.0 verification report at `logs/day-2-bootstrap-report.md` for baseline
- The pending manual step: user triggers Scout via claude.ai/code/routines after CDN confirmed propagated

## After Phase 2 reports clean

Final validation step (user-driven, not VPS Claude's):
1. User opens claude.ai/code/routines, triggers Scout via "Run now"
2. Wait for Scout to complete (~5-15 min)
3. **Verify commits land on main** (not on `claude/*` branch this time)
4. Wait up to 10 min for daemon's next tick to pick up Scout's commits + digest file
5. Watch Telegram — daemon should deliver augmented digest with ingestion stats
6. Open one of the new reference folders on `main` branch — check screenshot.png renders, note.md analysis quality

If all six pass — Day 2 v1.1 ships clean, end-to-end pipeline confirmed.

## Reporting format

For each phase, report:
- Pre-flight check results (4 critical checks must all pass before Phase 1 starts)
- Phase 1 commit SHAs (both commits)
- Phase 2 check results (each grep, each daemon test)
- Final report file path

If ANY pre-flight fails or ANY check fails — STOP and report. Don't auto-fix downstream issues.

## What NOT to do

- Don't push to scout-workshop-vault (these patches are exclusively in public scout-workshop)
- Don't add new env variables anywhere
- Don't restart systemd timers (they pick up changes via next tick)
- Don't trigger the Scout Routine yourself — that's user's manual step
- Don't merge or close existing claude/focused-pasteur PR (user decision)
- Don't change vault state files (seen-urls.json, scout-last-run.json)
- Don't touch §3b, §3c, §4 commit format, or any other unrelated playbook section

End of approval response. Standing by for Phase 1 Act report.
