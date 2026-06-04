# Pre-flight 2 resolution — Option A authorized

You correctly identified that pre-flight 2's failure was a non-fast-forward, not a branch-protection block. Two different failure classes, my v2 spec conflated them by ordering pre-flight 2 before Step 1 cleanup. That was a design error in the pre-flight ordering.

**Option A authorized.** Proceed with the procedure below.

## Authorized procedure

**Step 1 (cleanup) — execute now:**

```bash
cd /opt/scout-workshop
git checkout logs/day-2-bootstrap-act.log
git pull origin main
git status
```

Expected after pull:
- Working tree clean
- Local main fast-forwarded to 8c16276 (budget bump from earlier)
- `git status` reports "nothing to commit, working tree clean, your branch is up to date with origin/main"

If anything other than that — STOP and report.

**Re-run pre-flight 2 on post-pull state:**

```bash
git push origin main --dry-run
```

This is now the meaningful version of the check — it asks "would a push from current local state succeed?" not "are we in a stale state?" Three possible outcomes:

**Outcome 2A — clean dry-run:** Output similar to "Everything up-to-date" or shows a normal push preview. **Proceed to Phase 1 Step 2 (commit 1).** This is the expected outcome.

**Outcome 2B — branch protection block:** Output mentions "protected branch", "required pull request", "required status check", or similar policy language. STOP and report — this is a real architectural blocker. User would need to either disable protection on `Xander1993/scout-workshop:main` temporarily or grant admin override. Don't proceed to commits.

**Outcome 2C — some other unexpected error:** Auth failure, network issue, anything else. STOP and report the full error verbatim. Don't try to infer or fix.

**Run sanity check on pulled content (from v2 Step 1):**

```bash
grep "tokens_used_today" skills/scout-playbook.md
```

Expected: line containing `100000` (confirms the budget bump from 8c16276 actually landed in the file). If still showing `50000` — the pull didn't include the file change we expected. STOP and report.

**Run process_one() call site count (from v2 Step 1):**

```bash
grep -n "process_one(" scripts/ingest_daemon.py
```

Expected: 2 occurrences (function definition + 1 call site in run_once). If more than 2 — additional call sites we didn't plan for, STOP and report. If less than 2 — daemon state is unexpected, STOP.

## After all post-pull checks pass

**Proceed directly to Phase 1 Step 2 (commit 1) per v2 + addendum:**

- Apply branch fix patches in skills/scout-playbook.md (§3d + §4)
- Apply 3 gitignore additions: `logs/*-act.log`, `day-2-v1-1-patches.md`, `state/*-failures.json`
- Verify before commit: `cat .gitignore` should show all 3 new patterns at the bottom
- Commit + push with retry-on-conflict for-loop
- Verify commit 1 on origin: `git fetch origin && git log origin/main --oneline -3`

Then Phase 1 Step 3 (commit 2) per v2 + addendum.

Then Phase 2 Verify on Opus 4.7 / effort high / thinking extended, including the addendum's py_compile + sys.path import test.

## Why this matters beyond this run

The lesson for future bootstraps: pre-flight checks must be ordered so they're testing conditions that are either stable or outside our control. Conditions we resolve ourselves in Step 1 of the same instruction document shouldn't be in the pre-flight gate — that's a circular dependency.

Future fix to v3 / v1.2 instructions: pre-flight 2 (branch protection) should run AFTER cleanup pull, not before. Pre-flight 4 (resume guard) should also run AFTER fetch, since stale local view can give wrong answer about what's on origin.

Recording this in this approval doc so it's traceable in the conversation history for the next iteration.

## Standing by

Run the procedure above. If post-pull pre-flight 2 outcome is 2A (clean) — proceed straight to commits without further authorization. If 2B (real protection block) — stop and report. If 2C (something else) — stop and report verbatim.

End of authorization.
