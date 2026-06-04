# Addendum to phase-0-approval-v2 — two operational fixes

Peer review caught two more operational gaps in v2. Both are real, both are small, neither blocks Phase 1. Apply these on top of v2 — don't replace v2.

## Fix 1: Failure tracker gitignore pattern

**Context:** Commit 2 introduces `deliver_pending_digest()` which writes a tracker file at `/opt/scout-workshop/state/digest-delivery-failures.json` for daemon-local failure counting. v2 documents this as "gitignored, daemon-local" but does NOT add a specific gitignore pattern for it.

**Risk:** Depending on current .gitignore state, the file may end up tracked when daemon creates it. Random commits would then include daemon's runtime state — bad for git hygiene.

**Action — add to commit 1's .gitignore changes:**

In Phase 1 Step 2 (commit 1), the .gitignore additions are currently:
```
logs/*-act.log
day-2-v1-1-patches.md
```

Add a third line:
```
state/*-failures.json
```

Pattern is broad enough to catch the daemon-local failure tracker AND any future similar files (e.g., if we add Workshop on Day 3 with its own failure tracking). Specific enough to not accidentally exclude anything we'd want versioned.

The commit 1 .gitignore section becomes:
```bash
# Update .gitignore: add three patterns
cat >> .gitignore <<'EOF'
logs/*-act.log
day-2-v1-1-patches.md
state/*-failures.json
EOF
```

(Or use whichever .gitignore-edit mechanism is cleaner — append, sed insert, whatever VPS Claude prefers. Just ensure all three patterns land.)

Pre-flight check before commit 1: verify the patterns aren't already in .gitignore (avoid duplicate lines):

```bash
cd /opt/scout-workshop
for pattern in 'logs/\*-act\.log' 'day-2-v1-1-patches\.md' 'state/\*-failures\.json'; do
    if grep -qE "^${pattern}$" .gitignore; then
        echo "Pattern already present, will skip: $pattern"
    else
        echo "Pattern missing, will add: $pattern"
    fi
done
```

If all three already present (somehow) — fine, skip the .gitignore edit, just commit playbook patches alone in commit 1. If any are missing — add the missing ones.

## Fix 2: Daemon import test — replace fragile import statement

**Context:** v2 Phase 2 Verify uses this check:
```bash
/opt/scout-workshop/venv/bin/python -c "from scripts.ingest_daemon import run_once, deliver_pending_digest; print('imports ok')"
```

**Risk:** This requires `scripts/` to be a Python package (i.e., `scripts/__init__.py` exists). If it doesn't exist, the import fails with `ModuleNotFoundError` even when the daemon code itself is syntactically perfect — false negative on Phase 2 Verify, you might revert good patches thinking they broke imports when actually it's a path issue unrelated to v1.1.

**Action — replace the import test with a more robust two-step check:**

In Phase 2 Verify, change the "Daemon imports work (no syntax errors)" section to:

```bash
# Step 1: Pure syntax + module-level import check via py_compile
/opt/scout-workshop/venv/bin/python -m py_compile scripts/ingest_daemon.py
echo "py_compile exit code: $?"
# Expected: 0. Non-zero means syntax error or top-level import failure.

# Step 2: Verify new symbols are present (works regardless of __init__.py existence)
cd /opt/scout-workshop && /opt/scout-workshop/venv/bin/python <<'PYEOF'
import sys
sys.path.insert(0, 'scripts')
import ingest_daemon

required = ['process_one', 'run_once', 'deliver_pending_digest', 'main']
for sym in required:
    assert hasattr(ingest_daemon, sym), f"missing: {sym}"

# Also verify process_one signature change took effect
import inspect
sig = inspect.signature(ingest_daemon.process_one)
return_annotation = sig.return_annotation
print(f"process_one signature: {sig}")
print(f"return annotation: {return_annotation}")
# Expected: signature shows (note_path, dry_run) and return annotation indicates 3-tuple

print('symbols + signature ok')
PYEOF
```

The two-step check separates concerns:
- Step 1 (py_compile) catches syntax errors and unresolved imports at module scope. It's the cheapest sanity check.
- Step 2 (sys.path manipulation) verifies the specific new symbols (`deliver_pending_digest`) and the modified signature (`process_one` returning 3-tuple instead of 2-tuple) are actually present, independent of whether `scripts/` is a proper package.

If step 1 passes and step 2 fails — module is fine but our new code didn't land. If step 1 fails — code itself has a problem.

## What stays unchanged from v2

Everything else in phase-0-approval-v2 stands:

- 4 critical pre-flight checks (cwd, branch protection, Telegram bot, resume guard)
- Phase 1 Act on Opus 4.7 / effort medium / thinking extended
- Two-commit split (branch fix first, Firecrawl + Telegram + daemon second)
- All find/replace patches as specified
- §3a defensive screenshot handler preservation discipline
- CDN propagation check before final manual trigger
- Phase 2 Verify on Opus 4.7 / effort high / thinking extended
- Final manual trigger by user via claude.ai/code/routines

Just patch in:
1. Third gitignore pattern in commit 1
2. Replace fragile import test with py_compile + sys.path manipulation in Phase 2 Verify

## Standing by

Apply v2 + this addendum. Run pre-flight checks. Report pre-flight results before starting Phase 1 Act.

End of addendum.
