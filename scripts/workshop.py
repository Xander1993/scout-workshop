#!/usr/bin/env python3
"""
Workshop — static HTML/CSS/JS kit generator (v1.0).

Pipeline (each phase function takes explicit inputs and returns explicit
outputs — no module-level mutable state; main() orchestrates and threads
state through):

    readiness_check(vertical)
        → int (count of vault refs in vertical). Caller skips if < 8.

    retrieve_inspiration(vertical, aesthetic, vault_index)
        → list[ref] of up to 8 records, semantic search top-20 → Cohere
          Rerank top-8, each record carries {note_path, image_path, payload}.

    synthesize_brief(vertical, aesthetic, references, run_dir)
        → Path to brief.md (claude --print output captured).

    generate_kit(brief_path, references, run_dir)
        → Path to kit_dir. Raises if any of the 5 required files is
          missing/empty. Raw stdout always saved to raw_kit_output.txt.

    self_audit(kit_dir, run_dir)
        → dict (parsed JSON audit). Raises on JSON parse failure;
          raw stdout saved to raw_audit.txt for triage.

    generate_kit_images(kit_dir, run_dir)   [v1.1]
        → dict[image_id, status] (success | fallback | failed). Calls
          Gemini Nano Banana 2 once per image-prompts.json entry, saves
          JPEGs to kit/assets/images/{id}.jpg, falls back to SVG
          placeholders on failure, rewrites picsum URLs in HTML to
          local paths. Hard-fails on missing API key/manifest/PIL.

    capture_screenshots(kit_dir, run_dir)
        → dict[str, Path] of 6 PNGs (3 pages × 2 viewports). Failure is
          non-fatal — main() catches and proceeds with text-only delivery.

    deliver(kit_dir, run_dir, audit, screenshots, vertical, aesthetic)
        → bool (push_ok). Push-failure queues to pending_pushes.txt and
          sends an alert. Telegram delivery is best-effort, never raises.

main() acquires an exclusive flock on /var/lock/workshop.lock; if held,
exits 0. Disk under 1 GB on the project partition → halt + alert + exit 1.

Reuses scout_lib for embed / qdrant_query / rerank / telegram_send.
Direct multipart calls to Telegram sendMediaGroup are inlined here because
scout_lib only exposes plain text.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import scout_lib as sl  # noqa: E402  (path injected above)
from aesthetic_configs import get_config as get_aesthetic_config  # noqa: E402
from aesthetic_configs import get_awwwards_config  # noqa: E402  (v1.5 register)
import awwwards_render  # noqa: E402
import genericness_proxy  # noqa: E402

# ─────────────────────────────────────────────────────────────────────
# Constants — tuned for v1.0; change deliberately, not casually
# ─────────────────────────────────────────────────────────────────────

PROJECT_ROOT = HERE.parent
WORKSHOP_DIR = PROJECT_ROOT / "workshop"
RUNS_DIR = WORKSHOP_DIR / "runs"
STATE_DIR = WORKSHOP_DIR / "state"
KIT_TEMPLATE_DIR = WORKSHOP_DIR / "kit-template"
PLAYBOOK_PATH = PROJECT_ROOT / "skills" / "workshop-playbook.md"
VAULT_DIR = PROJECT_ROOT / "vault"
LOGS_DIR = PROJECT_ROOT / "logs"
KITS_MIRROR = PROJECT_ROOT / ".kits-mirror"
KITS_REMOTE = "git@github.com:Xander1993/camelotflows-kits.git"

LOCKFILE = "/var/lock/workshop.lock"
HTTP_PORT = int(os.environ.get("WORKSHOP_HTTP_PORT", "8200"))
CLAUDE_MODEL = "claude-opus-4-7"
CLAUDE_TIMEOUT_S = 1800
CLAUDE_RETRY_BACKOFF_S = 60
PUSH_RETRY_BACKOFFS_S = (5, 30, 120)
DISK_MIN_GB = 1.0

VAULT_READINESS_THRESHOLD = 4
QDRANT_TOP_K_INITIAL = 20
RERANK_TOP_N = 8
KIT_REFERENCE_IMAGE_COUNT = 3

VIEWPORTS = (("desktop", 1440, 900), ("mobile", 390, 844))
PAGES = ("index", "services", "contacts")

GITHUB_USER = "Xander1993"
GITHUB_REPO = "camelotflows-kits"

# Every Workshop-originated Telegram message starts with this prefix so humans
# (and the reaction_poller's cross-reference against sent_messages.json) can
# tell Workshop's deliveries apart from Scout's on the shared chat.
WORKSHOP_PREFIX = "🛠️ Workshop: "
SENT_MESSAGES_RING = 200  # cap on workshop/state/sent_messages.json entries

log = logging.getLogger("workshop")


# ─────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────

def _setup_logging(run_dir: Optional[Path] = None) -> None:
    """Configure stdout + workshop.log + per-run run.log handlers."""
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%dT%H:%M:%SZ")
    fmt.converter = time.gmtime  # always UTC
    if not log.handlers:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        log.addHandler(sh)
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(LOGS_DIR / "workshop.log")
        fh.setFormatter(fmt)
        log.addHandler(fh)
    if run_dir is not None:
        rh = logging.FileHandler(run_dir / "run.log")
        rh.setFormatter(fmt)
        log.addHandler(rh)


# ─────────────────────────────────────────────────────────────────────
# Lock + disk preflight
# ─────────────────────────────────────────────────────────────────────

def acquire_lock(path: str = LOCKFILE):
    """Try to grab an exclusive non-blocking flock on `path`.

    Returns the open file handle (caller must keep it alive for the lock
    to remain held — store on a long-lived variable). Returns None if
    the lock is already held; caller should exit 0 in that case.
    """
    f = open(path, "w")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return f
    except BlockingIOError:
        f.close()
        return None


def disk_check(min_gb: float = DISK_MIN_GB) -> bool:
    """Return True if the project partition has at least `min_gb` GB free."""
    free_gb = shutil.disk_usage(PROJECT_ROOT).free / (1024 ** 3)
    if free_gb < min_gb:
        log.error("disk preflight: %.2f GB free, need %.2f GB", free_gb, min_gb)
        _workshop_send(f"⛔ disk halt — only {free_gb:.1f} GB free; need ≥{min_gb} GB.")
        return False
    log.info("disk preflight: %.2f GB free", free_gb)
    return True


# ─────────────────────────────────────────────────────────────────────
# Queue (anchor mode for v1.0)
# ─────────────────────────────────────────────────────────────────────

def load_queue() -> dict:
    """Load workshop/state/queue.json. Bootstrap from queue.json.example
    on first invocation if the runtime file is absent."""
    p = STATE_DIR / "queue.json"
    if not p.exists():
        ex = STATE_DIR / "queue.json.example"
        if not ex.exists():
            raise FileNotFoundError(f"{p} missing and {ex} not available to bootstrap from")
        shutil.copy(ex, p)
        log.info("bootstrapped queue.json from queue.json.example")
    return json.loads(p.read_text(encoding="utf-8"))


def save_queue(queue: dict) -> None:
    """Atomically write workshop/state/queue.json."""
    p = STATE_DIR / "queue.json"
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)


def pick_next_target(queue: dict) -> Optional[tuple[str, str]]:
    """Choose the next (vertical, aesthetic) pair from the queue.

    v1.0 implements anchor mode only. Returns None if anchor is complete
    (caller exits 0 — exploration mode is v1.1 work).
    """
    if queue.get("mode") != "anchor":
        log.info("queue.mode=%s — exploration mode is v1.1, exiting", queue.get("mode"))
        return None
    anchor = queue["anchor"]
    if anchor["completed"] >= anchor["target_kits"]:
        log.info("anchor complete (%d/%d) — exploration is v1.1, exiting",
                 anchor["completed"], anchor["target_kits"])
        return None
    remaining = anchor.get("aesthetic_directions_remaining") or []
    if not remaining:
        log.error("anchor.completed=%d but no aesthetics remaining — queue corruption",
                  anchor["completed"])
        return None
    return anchor["vertical"], remaining[0]


def update_queue_after_run(queue: dict, used_aesthetic: str) -> None:
    """Decrement queue counters: drop the used aesthetic and bump completed."""
    anchor = queue["anchor"]
    anchor["aesthetic_directions_remaining"] = [
        a for a in anchor["aesthetic_directions_remaining"] if a != used_aesthetic
    ]
    anchor["completed"] = int(anchor["completed"]) + 1
    save_queue(queue)
    log.info("queue updated: completed=%d, remaining=%s",
             anchor["completed"], anchor["aesthetic_directions_remaining"])


# ─────────────────────────────────────────────────────────────────────
# Vault index — bridge Qdrant point id → vault file paths
# ─────────────────────────────────────────────────────────────────────

def build_vault_index() -> dict[str, tuple[Path, Optional[Path]]]:
    """Walk vault/references/**/note.md, parse the frontmatter `id` field,
    and return {qdrant_point_id: (note_md_path, screenshot_png_path_or_None)}.

    Notes without a parseable id are skipped with a WARNING.
    """
    index: dict[str, tuple[Path, Optional[Path]]] = {}
    refs_root = VAULT_DIR / "references"
    if not refs_root.is_dir():
        log.warning("vault references dir missing: %s", refs_root)
        return index
    for note in refs_root.rglob("note.md"):
        fm_id = _read_frontmatter_id(note)
        if not fm_id:
            log.warning("no id in frontmatter: %s", note)
            continue
        screenshot = note.parent / "screenshot.png"
        entry = (note, screenshot if screenshot.exists() else None)
        index[fm_id] = entry
        # v1.5: also key by directory slug so AWWWARDS_CONFIGS.anchor_reference_ids
        # (slug form, e.g. "989723a6-studio-namma") resolve. Slug and UUIDv5 never collide.
        index[note.parent.name] = entry
    return index


def _read_frontmatter_id(path: Path) -> Optional[str]:
    """Cheap frontmatter parser — extract the `id:` value without pulling YAML."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    for line in text[4:end].splitlines():
        if line.startswith("id:"):
            return line.split(":", 1)[1].strip()
    return None


# ─────────────────────────────────────────────────────────────────────
# Phase 1: readiness_check
# ─────────────────────────────────────────────────────────────────────

def readiness_check(vertical: str) -> int:
    """Return the exact count of Qdrant points tagged `vertical`.

    Uses the count API rather than a query-with-limit so the threshold
    decision is correct even when count > QDRANT_TOP_K_INITIAL.
    """
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    client = sl.qdrant_client_init()
    qfilter = Filter(must=[FieldCondition(key="vertical", match=MatchValue(value=vertical))])
    return client.count(
        collection_name=sl.COLLECTION_NAME, count_filter=qfilter, exact=True
    ).count


# ─────────────────────────────────────────────────────────────────────
# Phase 2: retrieve_inspiration
# ─────────────────────────────────────────────────────────────────────

def build_query_text(vertical: str, aesthetic: str) -> str:
    """Synthetic semantic-search query string for the embedding step."""
    return (
        f"High-converting {vertical} static website landing page with a {aesthetic} aesthetic. "
        "Strong primary CTA above the fold. Click-to-call mobile header. Trust signals. "
        "Mobile-first responsive layout. Conversion-tuned services and contacts pages."
    )


def retrieve_inspiration(
    vertical: str,
    aesthetic: str,
    vault_index: dict[str, tuple[Path, Optional[Path]]],
) -> list[dict[str, Any]]:
    """Top-20 Qdrant hits filtered by vertical, then Cohere Rerank → top-8.

    Returns a list of up to 8 dicts:
        {"point_id": str, "score": float, "title": str,
         "note_path": Path, "image_path": Path|None, "payload": dict}
    Rerank position is preserved (highest relevance first).
    """
    query = build_query_text(vertical, aesthetic)
    qvec = sl.embed(query)
    points = sl.qdrant_query(qvec, filters={"vertical": vertical}, limit=QDRANT_TOP_K_INITIAL)
    if not points:
        log.warning("retrieve_inspiration: 0 points for vertical=%s — readiness should have caught this",
                    vertical)
        return []

    candidate_docs: list[str] = []
    for p in points:
        pl = p.payload or {}
        parts = [
            pl.get("title", ""),
            pl.get("layout_pattern", "") or "",
            " | ".join(pl.get("techniques", []) or []),
            f"color_mood={pl.get('color_mood', '')} typography_style={pl.get('typography_style', '')}",
        ]
        candidate_docs.append(" — ".join(t for t in parts if t))

    reranked = sl.rerank(query, candidate_docs, top_n=RERANK_TOP_N)

    out: list[dict[str, Any]] = []
    for r in reranked:
        idx = r["index"]
        p = points[idx]
        pid = str(p.id)
        if pid not in vault_index:
            log.warning("rerank pick %s has no vault note.md — skipping", pid)
            continue
        note_path, image_path = vault_index[pid]
        out.append({
            "point_id": pid,
            "score": float(r.get("relevance_score", 0.0)),
            "title": (p.payload or {}).get("title", "(untitled)"),
            "note_path": note_path,
            "image_path": image_path,
            "payload": p.payload or {},
        })
    return out


# ─────────────────────────────────────────────────────────────────────
# claude --print wrapper (single retry on timeout/error per spec)
# ─────────────────────────────────────────────────────────────────────

def load_prompt_template(name: str) -> str:
    """Extract a prompt block named `name` from skills/workshop-playbook.md.

    Block delimiters are `>>> BEGIN PROMPT <name>` … `<<< END PROMPT <name>`.
    """
    body = PLAYBOOK_PATH.read_text(encoding="utf-8")
    pattern = rf">>> BEGIN PROMPT {re.escape(name)}\n(.*?)\n<<< END PROMPT {re.escape(name)}"
    m = re.search(pattern, body, re.DOTALL)
    if not m:
        raise KeyError(f"prompt block {name!r} not found in {PLAYBOOK_PATH}")
    return m.group(1)


def run_claude(
    prompt: str,
    *,
    effort: str,
    add_dirs: list[Path],
    tools: str,
    timeout_s: int = CLAUDE_TIMEOUT_S,
    permission_mode: str = "acceptEdits",
) -> str:
    """Invoke `claude --print --model claude-opus-4-7 --effort <effort> …`
    with `prompt` on stdin. Returns stdout.

    Retries once with CLAUDE_RETRY_BACKOFF_S on TimeoutExpired or non-zero exit.
    Raises subprocess.TimeoutExpired or subprocess.CalledProcessError after the
    second attempt fails (caller is expected to propagate / exit 1).
    """
    add_dir_args: list[str] = []
    for d in add_dirs:
        add_dir_args += ["--add-dir", str(d)]
    cmd = [
        "claude", "--print",
        "--model", CLAUDE_MODEL,
        "--effort", effort,
        "--permission-mode", permission_mode,
        "--tools", tools,
        "--output-format", "text",
        "--no-session-persistence",
        *add_dir_args,
    ]
    last_exc: Optional[BaseException] = None
    for attempt in (1, 2):
        log.info("claude --print effort=%s attempt=%d (timeout=%ds, tools=%r)",
                 effort, attempt, timeout_s, tools)
        try:
            r = subprocess.run(
                cmd, input=prompt,
                capture_output=True, text=True,
                timeout=timeout_s, check=True,
            )
            return r.stdout
        except subprocess.TimeoutExpired as e:
            last_exc = e
            log.warning("claude timeout on attempt %d", attempt)
        except subprocess.CalledProcessError as e:
            last_exc = e
            log.warning("claude exit %d on attempt %d: stderr=%r",
                        e.returncode, attempt, (e.stderr or "")[:1000])
        if attempt == 1:
            time.sleep(CLAUDE_RETRY_BACKOFF_S)
    assert last_exc is not None
    raise last_exc


# ─────────────────────────────────────────────────────────────────────
# Aesthetic config substitutions + anti-similarity context (v1.2)
#
# These helpers feed prompt-template tokens that Patch 1c adds to
# brief_synthesis and kit_generation. Until Patch 1c lands, the
# substitutions are inert (the templates don't contain the placeholders
# yet, so .replace() is a no-op). Keeping the wiring in this commit
# means Patch 1c is a single-file edit of skills/workshop-playbook.md.
# ─────────────────────────────────────────────────────────────────────

# Match `--color-bg: #F5EDE2;` etc. in the first :root block of style.css.
_CSS_PALETTE_TOKEN_RE = re.compile(
    r"--color-([a-z][\w-]*)\s*:\s*(#[0-9A-Fa-f]{6,8})"
)
# Match the H1 of brief.md: `# Brief — beauty / restrained-luxury-warm`
# Tolerates em-dash / en-dash / hyphen between Brief and the slug pair.
_BRIEF_H1_RE = re.compile(
    r"^#\s*Brief\s*[—–-]\s*([\w-]+)\s*/\s*([\w-]+)", re.MULTILINE
)


def _extract_palette_from_css(css_path: Path) -> dict[str, str]:
    """Parse a kit's style.css for `--color-{name}: #XXXXXX` tokens.

    Returns dict keyed by the suffix after `--color-` (e.g. "bg", "fg",
    "accent", "muted", "surface"). Empty dict on missing file or no matches —
    caller should treat empty as "skip this kit."
    """
    if not css_path.exists():
        return {}
    try:
        text = css_path.read_text(encoding="utf-8")
    except Exception:
        return {}
    # Limit scan to the first ~4 KB — palette tokens live in the :root block
    # at the top of every kit's style.css. Saves a regex sweep on long files.
    return {
        m.group(1).lower(): m.group(2).upper()
        for m in _CSS_PALETTE_TOKEN_RE.finditer(text[:4096])
    }


def _read_brief_vertical(brief_path: Path) -> Optional[str]:
    """Parse the vertical name from brief.md's H1 line. Returns None if
    brief is missing or H1 is unparseable — caller skips the run."""
    if not brief_path.exists():
        return None
    try:
        text = brief_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    m = _BRIEF_H1_RE.search(text[:1024])
    return m.group(1) if m else None


def _extract_prior_kits_palettes(vertical: str, exclude_run_dir: Path) -> str:
    """Anti-similarity context: walk RUNS_DIR for kits in the same vertical,
    extract their palette tokens, and return formatted markdown for prompt
    injection.

    Excludes `exclude_run_dir` (the current in-progress run) so the model
    never sees its own prior placeholder palette as a "prior kit". Always
    returns non-empty text — empty-state goes to a descriptive line so the
    substituted token in the prompt always renders something readable.
    """
    if not RUNS_DIR.exists():
        return f"(no prior {vertical!r}-vertical kits — this kit sets the baseline)"
    items: list[str] = []
    for run in sorted(RUNS_DIR.iterdir()):
        if not run.is_dir() or run.resolve() == exclude_run_dir.resolve():
            continue
        if _read_brief_vertical(run / "brief.md") != vertical:
            continue
        css = run / "kit" / "assets" / "css" / "style.css"
        palette = _extract_palette_from_css(css)
        if not palette:
            continue
        bg = palette.get("bg", "?")
        fg = palette.get("fg", "?")
        accent = palette.get("accent", "?")
        items.append(f"- `{run.name}`: bg={bg}, fg={fg}, accent={accent}")
    if not items:
        return f"(no prior {vertical!r}-vertical kits — this kit sets the baseline)"
    return "\n".join(items)


def _format_avoid_list(items: list[str]) -> str:
    """Render an aesthetic_configs `avoid` list as a markdown bullet list."""
    if not items:
        return "(no explicit avoidances for this aesthetic)"
    return "\n".join(f"- {it}" for it in items)


def _aesthetic_substitutions(aesthetic: str) -> dict[str, str]:
    """Build the prompt-substitution map for aesthetic_configs fields.

    Keys are the placeholder tokens that Patch 1c will introduce in
    brief_synthesis and kit_generation. Until Patch 1c lands, none of these
    tokens appear in the templates, so .replace() is a no-op. After Patch 1c
    lands, the same call site automatically picks up the new placeholders —
    no further wiring needed.
    """
    cfg = get_aesthetic_config(aesthetic)
    return {
        "{{AESTHETIC_NAME}}":                 cfg["name"],
        "{{AESTHETIC_PALETTE_DIRECTIVE}}":    cfg["palette_directive"],
        "{{AESTHETIC_TYPOGRAPHY_DIRECTIVE}}": cfg["typography_directive"],
        "{{AESTHETIC_LAYOUT_DIRECTIVE}}":     cfg["layout_directive"],
        "{{AESTHETIC_LAYOUT_SKETCH_CSS}}":    cfg["layout_sketch_css"],
        "{{AESTHETIC_AVOID_LIST}}":           _format_avoid_list(cfg["avoid"]),
        "{{AESTHETIC_CRAFT_DIRECTIVE}}":      cfg["craft_directive"],
        "{{AESTHETIC_IMAGE_PREFIX}}":         cfg["image_prefix"],
    }


# ─────────────────────────────────────────────────────────────────────
# Phase 3: synthesize_brief
# ─────────────────────────────────────────────────────────────────────

def synthesize_brief(
    vertical: str, aesthetic: str,
    references: list[dict[str, Any]],
    run_dir: Path,
) -> Path:
    """Run the brief-synthesis prompt; return path to the written brief.md.

    The model reads each reference note from the vault directly via the Read
    tool, so we only pass paths in the prompt — not contents.
    """
    template = load_prompt_template("brief_synthesis")
    refs_list = "\n".join(f"- {r['note_path']}" for r in references)
    # Aesthetic config tokens are substituted whether or not the template
    # currently contains them — Patch 1c adds the placeholders to the
    # template, and this wiring lets that be a single-file edit.
    subs = {
        "{{VERTICAL}}": vertical,
        "{{AESTHETIC}}": aesthetic,
        "{{REFERENCE_NOTES_LIST}}": refs_list,
        **_aesthetic_substitutions(aesthetic),
    }
    prompt = template
    for k, v in subs.items():
        prompt = prompt.replace(k, v)
    out = run_claude(
        prompt, effort="high",
        add_dirs=[VAULT_DIR, run_dir],
        tools="Read Write",
    )
    brief_path = run_dir / "brief.md"
    brief_path.write_text(out, encoding="utf-8")
    log.info("brief.md written: %d bytes", len(out))
    return brief_path


# ─────────────────────────────────────────────────────────────────────
# Phase 4: generate_kit
# ─────────────────────────────────────────────────────────────────────

KIT_REQUIRED_FILES = (
    "index.html",
    "services.html",
    "contacts.html",
    "assets/css/style.css",
    "assets/js/main.js",
    "image-prompts.json",
)

# v1.5 awwwards register: per-kit_type required files (editorial-studio = 3-page,
# single-product = 1-page). The conversion path keeps using KIT_REQUIRED_FILES.
KIT_REQUIRED_FILES_BY_KIT_TYPE = {
    "editorial-studio": ("index.html", "work.html", "contact.html",
                         "assets/css/style.css", "assets/js/main.js", "image-prompts.json"),
    "single-product": ("index.html",
                       "assets/css/style.css", "assets/js/main.js", "image-prompts.json"),
}


def generate_kit(
    brief_path: Path,
    references: list[dict[str, Any]],
    run_dir: Path,
    vertical: str,
    aesthetic: str,
) -> Path:
    """Run the kit-generation prompt; verify all 5 files were written.

    Raises RuntimeError if any required file is missing or empty after
    the call. The raw stdout is always saved to run_dir/raw_kit_output.txt
    so a failed run is debuggable without rerunning.

    `vertical` + `aesthetic` (v1.2) drive two new prompt substitutions:
    aesthetic_configs fields (palette directive, layout sketch, avoid list,
    craft directive) and prior-kits-palette anti-similarity context. Both
    sets of placeholders are populated whether or not the template currently
    references them — Patch 1c adds them to the template body.
    """
    kit_dir = run_dir / "kit"
    (kit_dir / "assets/css").mkdir(parents=True, exist_ok=True)
    (kit_dir / "assets/js").mkdir(parents=True, exist_ok=True)

    top_imgs = [r for r in references if r["image_path"] is not None][:KIT_REFERENCE_IMAGE_COUNT]
    if not top_imgs:
        raise RuntimeError("no reference images available — cannot generate kit")
    while len(top_imgs) < KIT_REFERENCE_IMAGE_COUNT:
        # pad by repeating the last available image; the prompt still gets 3 paths
        top_imgs.append(top_imgs[-1])

    prior_palettes = _extract_prior_kits_palettes(vertical, run_dir)
    log.info("prior kits palette context: %d-line summary",
             prior_palettes.count("\n") + 1)

    template = load_prompt_template("kit_generation")
    subs = {
        "{{KIT_DIR}}": str(kit_dir),
        "{{RUN_DIR}}": str(run_dir),
        "{{VERTICAL}}": vertical,
        "{{AESTHETIC}}": aesthetic,
        "{{PRIOR_KITS_PALETTES}}": prior_palettes,
        **_aesthetic_substitutions(aesthetic),
    }
    for i, r in enumerate(top_imgs, 1):
        subs[f"{{{{REF_IMAGE_{i}}}}}"] = str(r["image_path"])
    prompt = template
    for k, v in subs.items():
        prompt = prompt.replace(k, v)

    out = run_claude(
        prompt, effort="high",
        add_dirs=[VAULT_DIR, run_dir],
        tools="Read Write",
    )
    raw_path = run_dir / "raw_kit_output.txt"
    raw_path.write_text(out, encoding="utf-8")

    missing: list[str] = []
    for rel in KIT_REQUIRED_FILES:
        p = kit_dir / rel
        if not p.exists() or p.stat().st_size == 0:
            missing.append(rel)
    if missing:
        log.error("kit incomplete; missing/empty: %s", missing)
        raise RuntimeError(
            f"generate_kit produced {len(KIT_REQUIRED_FILES) - len(missing)}/"
            f"{len(KIT_REQUIRED_FILES)} files; raw output saved to {raw_path}"
        )

    # README accompanies the kit; copied from the static template, not generated
    readme_src = KIT_TEMPLATE_DIR / "README.md"
    if readme_src.exists():
        shutil.copy(readme_src, kit_dir / "README.md")
    log.info("kit generated: %d files in %s", len(KIT_REQUIRED_FILES) + 1, kit_dir)
    return kit_dir


# ─────────────────────────────────────────────────────────────────────
# Phase 5: self_audit
# ─────────────────────────────────────────────────────────────────────

def self_audit(kit_dir: Path, run_dir: Path) -> dict[str, Any]:
    """Run the audit prompt; return the parsed JSON.

    On JSON parse failure, raw stdout is saved to run_dir/raw_audit.txt and
    RuntimeError is raised — the spec mandates aborting rather than continuing
    with a broken audit.
    """
    template = load_prompt_template("self_audit")
    prompt = template.replace("{{KIT_DIR}}", str(kit_dir)).replace("{{RUN_DIR}}", str(run_dir))
    out = run_claude(
        prompt, effort="medium",
        add_dirs=[kit_dir],
        tools="Read",
    )
    try:
        json_text = _extract_json_object(out)
        data = json.loads(json_text)
    except (ValueError, json.JSONDecodeError) as e:
        raw = run_dir / "raw_audit.txt"
        raw.write_text(out, encoding="utf-8")
        log.error("audit JSON parse failed: %s — raw saved to %s", e, raw)
        raise RuntimeError(f"audit JSON parse failed: {e}; raw at {raw}") from e

    audit_md = run_dir / "audit.md"
    audit_md.write_text(_render_audit_markdown(data), encoding="utf-8")
    log.info("audit_status=%s warnings=%d",
             data.get("audit_status"), len(data.get("warnings", [])))
    return data


def _extract_json_object(text: str) -> str:
    """Return the first balanced `{ … }` block in `text`. Honors string escapes."""
    depth = 0
    start = -1
    in_str = False
    escape = False
    for i, ch in enumerate(text):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                return text[start:i + 1]
    raise ValueError("no balanced JSON object found")


def _render_audit_markdown(data: dict[str, Any]) -> str:
    bool_keys = (
        "html_valid", "css_valid", "wcag_aa_pairs_pass",
        "has_cta_above_fold", "has_click_to_call", "has_trust_signals",
        "telemetry_placeholders_present", "lazy_images_below_fold",
    )
    lines = ["# Self-audit report", "",
             f"**Status:** {data.get('audit_status', '?')}", "",
             "## Boolean checks"]
    for k in bool_keys:
        lines.append(f"- `{k}`: {data.get(k, '?')}")
    if data.get("lighthouse_concerns"):
        lines += ["", "## Lighthouse concerns"]
        lines += [f"- {c}" for c in data["lighthouse_concerns"]]
    if data.get("warnings"):
        lines += ["", "## Warnings"]
        lines += [f"- {w}" for w in data["warnings"]]
    return "\n".join(lines) + "\n"


# ─────────────────────────────────────────────────────────────────────
# Phase 7: capture_screenshots (Playwright + python -m http.server)
# (was phase 6 before v1.1 — image generation now occupies phase 6)
# ─────────────────────────────────────────────────────────────────────

def capture_screenshots(kit_dir: Path, run_dir: Path, pages=PAGES) -> dict[str, Path]:
    """Serve `kit_dir` over loopback, take 6 PNGs, return dict of paths.

    Failure (browser crash, server bind failure, navigation timeout) raises;
    main() catches and proceeds with text-only delivery per spec.
    """
    import urllib.request

    screenshots_dir = kit_dir / "screenshots"
    screenshots_dir.mkdir(exist_ok=True)

    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(HTTP_PORT), "--bind", "127.0.0.1"],
        cwd=str(kit_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    out: dict[str, Path] = {}
    try:
        url_root = f"http://127.0.0.1:{HTTP_PORT}/"
        ready = False
        for _ in range(50):  # 5s total
            try:
                with urllib.request.urlopen(url_root + "index.html", timeout=0.5) as r:
                    if r.status == 200:
                        ready = True
                        break
            except Exception:
                time.sleep(0.1)
        if not ready:
            raise RuntimeError(f"http.server failed to bind on {HTTP_PORT}")

        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                for vp_name, vp_w, vp_h in VIEWPORTS:
                    ctx = browser.new_context(viewport={"width": vp_w, "height": vp_h})
                    try:
                        for page_name in pages:
                            page = ctx.new_page()
                            try:
                                page.goto(url_root + f"{page_name}.html",
                                          wait_until="load", timeout=20_000)
                                page.wait_for_timeout(2500)  # settle GSAP/Lenis motion
                                logical = "home" if page_name == "index" else page_name
                                path = screenshots_dir / f"{logical}-{vp_name}.png"
                                page.screenshot(path=str(path), full_page=True)
                                out[f"{logical}-{vp_name}"] = path
                            finally:
                                page.close()
                    finally:
                        ctx.close()
            finally:
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
    log.info("captured %d screenshots in %s", len(out), screenshots_dir)
    return out


# ─────────────────────────────────────────────────────────────────────
# Phase 8: deliver — git push + Telegram media group
# (was phase 7 before v1.1)
# ─────────────────────────────────────────────────────────────────────

def deliver(
    kit_dir: Path, run_dir: Path,
    audit: dict[str, Any], screenshots: dict[str, Path],
    vertical: str, aesthetic: str,
    images_status: Optional[dict[str, dict[str, Any]]] = None,
) -> bool:
    """Push to camelotflows-kits and send a Telegram media group.

    Returns push_ok (True/False). Telegram delivery never raises; failures
    are logged. A failed push is queued to workshop/state/pending_pushes.txt
    and an alert is sent. `images_status` (v1.1) is included in the Telegram
    caption when provided; pass None to omit the image-gen line entirely.
    """
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    kit_name = f"{today}-{vertical}-{aesthetic}"

    repo = _ensure_kits_repo()
    target = repo / "kits" / kit_name
    suffix = 2
    while target.exists():
        target = repo / "kits" / f"{kit_name}-{suffix}"
        suffix += 1
    kit_name = target.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(kit_dir, target)
    for sib in ("brief.md", "audit.md"):
        s = run_dir / sib
        if s.exists():
            shutil.copy(s, target / sib)

    commit_msg = f"Workshop kit: {vertical} {aesthetic}\n\nAudit: {audit.get('audit_status', '?')}"
    tag = f"v{kit_name}"

    push_ok = _git_publish(repo, kit_name, commit_msg, tag)
    commit_url: Optional[str] = None
    if push_ok:
        commit_url = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}/commit/{_git_head_sha(repo)}"
    else:
        _queue_pending_push(kit_name, tag)

    _send_telegram_kit(audit, screenshots, vertical, aesthetic,
                       commit_url, push_ok, images_status)
    return push_ok


def _ensure_kits_repo() -> Path:
    """Idempotent clone or fast-forward of camelotflows-kits to .kits-mirror/."""
    if not KITS_MIRROR.exists():
        log.info("cloning %s to %s", KITS_REMOTE, KITS_MIRROR)
        subprocess.run(["git", "clone", KITS_REMOTE, str(KITS_MIRROR)], check=True)
        return KITS_MIRROR
    log.info("syncing %s with origin/main", KITS_MIRROR)
    subprocess.run(["git", "-C", str(KITS_MIRROR), "fetch", "origin"], check=True)
    # Check if origin/main exists yet (repo could be empty on first run)
    has_main = subprocess.run(
        ["git", "-C", str(KITS_MIRROR), "rev-parse", "--verify", "origin/main"],
        capture_output=True,
    ).returncode == 0
    if has_main:
        subprocess.run(["git", "-C", str(KITS_MIRROR), "checkout", "main"], check=True)
        subprocess.run(["git", "-C", str(KITS_MIRROR), "reset", "--hard", "origin/main"], check=True)
    else:
        log.info("origin/main not yet on remote — will create on first push")
        subprocess.run(["git", "-C", str(KITS_MIRROR), "checkout", "-B", "main"], check=True)
    return KITS_MIRROR


def _git_publish(repo: Path, kit_name: str, commit_msg: str, tag: str) -> bool:
    """git add → commit → tag → push (with retry). True on success."""
    def _g(*args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            check=check, capture_output=True, text=True,
        )
    _g("add", f"kits/{kit_name}")
    _g("-c", "user.name=Workshop Bot",
       "-c", "user.email=workshop@srv1420550.local",
       "commit", "-m", commit_msg)
    _g("tag", tag)
    for attempt, backoff in enumerate(PUSH_RETRY_BACKOFFS_S, start=1):
        try:
            _g("push", "origin", "main", "--tags")
            log.info("push success on attempt %d", attempt)
            return True
        except subprocess.CalledProcessError as e:
            log.warning("push attempt %d failed: %s — backing off %ds",
                        attempt, (e.stderr or "")[:200], backoff)
            time.sleep(backoff)
    log.error("push failed all %d attempts", len(PUSH_RETRY_BACKOFFS_S))
    return False


def _git_head_sha(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _queue_pending_push(kit_name: str, tag: str) -> None:
    """Append a tab-separated record to workshop/state/pending_pushes.txt."""
    p = STATE_DIR / "pending_pushes.txt"
    line = "\t".join([
        dt.datetime.now(dt.timezone.utc).isoformat(),
        kit_name,
        tag,
    ]) + "\n"
    with p.open("a", encoding="utf-8") as f:
        f.write(line)
    _workshop_send(
        f"⚠️ push failed for {kit_name}; queued to {p}. "
        "Run `cd .kits-mirror && git push origin main --tags` to retry manually."
    )


# ─────────────────────────────────────────────────────────────────────
# Telegram — Workshop-prefixed sends + sent_messages.json tracking
# (scout_lib.telegram_send is text-only and doesn't return a message_id,
#  so Workshop owns its own send path to capture ids for the reaction
#  poller's cross-reference filter.)
# ─────────────────────────────────────────────────────────────────────

def _record_sent_message(chat_id: int, message_id: int) -> None:
    """Append (chat_id, message_id, ts) to workshop/state/sent_messages.json.
    Bounded ring — keeps last SENT_MESSAGES_RING entries. Never raises."""
    p = STATE_DIR / "sent_messages.json"
    try:
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
        else:
            data = {"messages": []}
        msgs = data.setdefault("messages", [])
        msgs.append({
            "chat_id": chat_id,
            "message_id": message_id,
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        })
        if len(msgs) > SENT_MESSAGES_RING:
            data["messages"] = msgs[-SENT_MESSAGES_RING:]
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        tmp.replace(p)
    except Exception as e:
        log.warning("could not record sent message %s/%s: %s", chat_id, message_id, e)


def _send_telegram_text_raw(text: str) -> None:
    """Direct sendMessage call (no prefix-prepending; caller wrote the full
    message). Records message_id for each chat. Never raises — Telegram
    delivery is best-effort per spec."""
    import requests
    try:
        env = sl.load_env()
        token = env["TELEGRAM_BOT_TOKEN"]
        chat_ids = [c.strip() for c in env.get("TELEGRAM_CHAT_IDS", "").split(",") if c.strip()]
        if not chat_ids:
            log.warning("TELEGRAM_CHAT_IDS empty; dropping workshop alert")
            return
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        for chat_id in chat_ids:
            try:
                r = requests.post(
                    url,
                    json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
                    timeout=15,
                )
                r.raise_for_status()
                mid = (r.json().get("result") or {}).get("message_id")
                if mid is not None:
                    _record_sent_message(int(chat_id), int(mid))
            except Exception as e:
                log.warning("workshop send to chat=%s failed: %s", chat_id, e)
    except Exception as e:
        log.warning("workshop send failed: %s", e)


def _workshop_send(msg: str) -> None:
    """Prefix WORKSHOP_PREFIX + send + record. Use this for Workshop alerts."""
    _send_telegram_text_raw(WORKSHOP_PREFIX + msg)


def _tier_from_audit(audit: dict[str, Any]) -> int:
    """1=ship-ready (pass), 2=needs polish (warn), 3=draft only (fail or unknown)."""
    return {"pass": 1, "warn": 2, "fail": 3}.get(audit.get("audit_status", ""), 3)


def _send_telegram_kit(
    audit: dict[str, Any],
    screenshots: dict[str, Path],
    vertical: str, aesthetic: str,
    commit_url: Optional[str], push_ok: bool,
    images_status: Optional[dict[str, dict[str, Any]]] = None,
) -> None:
    """Best-effort Telegram delivery. Caption first, then 6 photos. Never raises."""
    try:
        emoji = {"pass": "✅", "warn": "⚠️", "fail": "❌"}.get(
            audit.get("audit_status", ""), "❔",
        )
        tier = _tier_from_audit(audit)
        # First line carries WORKSHOP_PREFIX so the reaction poller can match
        # this delivery against sent_messages.json (and humans can scan the chat).
        lines = [
            f"{WORKSHOP_PREFIX}{emoji} kit — {vertical} / {aesthetic}",
            f"Tier: {tier} (1=ship, 2=polish, 3=draft)",
        ]
        lines.append(f"Commit: {commit_url}" if commit_url
                     else "Push: queued (see pending_pushes.txt)")
        extras: list[str] = []
        warns = audit.get("warnings") or []
        if warns:
            extras += [f"• {w}" for w in warns[:3]]
            if len(warns) > 3:
                extras.append(f"• +{len(warns) - 3} more (see audit.md)")
        if images_status:
            total = len(images_status)
            succ = sum(1 for v in images_status.values() if v.get("status") == "success")
            fb = sum(1 for v in images_status.values() if v.get("status") == "fallback")
            failed = sum(1 for v in images_status.values() if v.get("status") == "failed")
            img_line = f"• Images: {succ}/{total} generated"
            if fb:
                img_line += f", {fb} fallback placeholders"
            if failed:
                img_line += f", {failed} failed"
            extras.append(img_line)
        if extras:
            lines.append("")
            lines += extras
        caption = "\n".join(lines)[:1024]

        order = ("home-desktop", "home-mobile",
                 "services-desktop", "services-mobile",
                 "contacts-desktop", "contacts-mobile")
        files = [(n, screenshots[n]) for n in order if n in screenshots]
        if not files:
            # Caption already begins with WORKSHOP_PREFIX — don't double-prepend.
            _send_telegram_text_raw(caption + "\n\n(screenshots failed — see audit.md)")
            return
        _telegram_send_media_group(files, caption)
    except Exception as e:
        log.warning("telegram delivery failed (non-fatal): %s", e)


def _telegram_send_media_group(files: list[tuple[str, Path]], caption: str) -> None:
    """POST sendMediaGroup with multipart/form-data. Up to 10 photos per call;
    we send 6. Caption rides on the first item."""
    import requests
    env = sl.load_env()
    token = env["TELEGRAM_BOT_TOKEN"]
    chat_ids = [c.strip() for c in env.get("TELEGRAM_CHAT_IDS", "").split(",") if c.strip()]
    if not chat_ids:
        raise ValueError("TELEGRAM_CHAT_IDS empty")
    url = f"https://api.telegram.org/bot{token}/sendMediaGroup"
    for chat_id in chat_ids:
        media = []
        opened: list = []
        files_arg: dict[str, tuple[str, Any, str]] = {}
        try:
            for i, (_name, path) in enumerate(files):
                key = f"photo{i}"
                item = {"type": "photo", "media": f"attach://{key}"}
                if i == 0:
                    item["caption"] = caption
                media.append(item)
                fh = open(path, "rb")
                opened.append(fh)
                files_arg[key] = (path.name, fh, "image/png")
            r = requests.post(
                url,
                data={"chat_id": chat_id, "media": json.dumps(media)},
                files=files_arg,
                timeout=120,
            )
            r.raise_for_status()
            # Record the *first* message_id of the group — the one carrying the
            # caption (WORKSHOP_PREFIX). That's what reactions will land on.
            results = r.json().get("result") or []
            if results:
                first_mid = results[0].get("message_id")
                if first_mid is not None:
                    _record_sent_message(int(chat_id), int(first_mid))
        finally:
            for fh in opened:
                try:
                    fh.close()
                except Exception:
                    pass


# ─────────────────────────────────────────────────────────────────────
# v1.5 Awwwards register — additive oneshot (no cron, no gates, no delivery)
# ─────────────────────────────────────────────────────────────────────

def run_design_concept(sub_aesthetic, kit_type, hero_archetype, refs, recent, run_dir):
    """Commit the kit to ONE bespoke signature idea → concept.json."""
    template = load_prompt_template("design_concept")
    cfg = get_awwwards_config(sub_aesthetic)
    subs = {
        "{{SUB_AESTHETIC}}": sub_aesthetic,
        "{{REGISTER_FAMILY}}": cfg["register_family"],
        "{{KIT_TYPE}}": kit_type,
        "{{HERO_ARCHETYPE}}": hero_archetype,
        "{{REF_SIGNATURE_IDEAS}}": "\n".join(
            f"- {r['payload'].get('signature_idea','')}" for r in refs) or "(none)",
        "{{RECENT_CONCEPTS}}": "\n".join(f"- {c}" for c in recent) or "(none)",
    }
    prompt = template
    for k, v in subs.items():
        prompt = prompt.replace(k, v)
    out = run_claude(prompt, effort="medium", add_dirs=[run_dir], tools="")
    data = json.loads(_extract_json_object(out))
    (run_dir / "concept.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    log.info("concept: %s", data.get("hook_name"))
    return data


def synthesize_brief_awwwards(sub_aesthetic, kit_type, directives, hero_archetype,
                              topo, concept, refs, run_dir):
    template = load_prompt_template("brief_synthesis_awwwards")
    refs_list = "\n".join(f"- {r['note_path']}" for r in refs if r.get("note_path"))
    subs = {
        "{{SUB_AESTHETIC}}": sub_aesthetic,
        "{{KIT_TYPE}}": kit_type,
        "{{REGISTER_FAMILY}}": directives["register_family"],
        "{{HERO_ARCHETYPE}}": hero_archetype,
        "{{PALETTE_DIRECTIVE}}": directives["palette_directive"],
        "{{TYPOGRAPHY_DIRECTIVE}}": directives["typography_directive"],
        "{{MOTION_DIRECTIVE}}": directives["motion_directive"],
        "{{SIGNATURE_MOVE}}": concept.get("signature_move", ""),
        "{{AVOID_LIST}}": "; ".join(directives.get("avoid", [])),
        "{{REFERENCE_NOTES_LIST}}": refs_list,
    }
    prompt = template
    for k, v in subs.items():
        prompt = prompt.replace(k, v)
    out = run_claude(prompt, effort="high", add_dirs=[VAULT_DIR, run_dir], tools="Read Write")
    brief_path = run_dir / "brief.md"
    brief_path.write_text(out, encoding="utf-8")
    if "section_manifest" not in out:
        log.warning("brief missing section_manifest (Phase 1b gates depend on it)")
    return brief_path


def generate_kit_awwwards(brief_path, refs, run_dir, kit_type, directives, concept):
    kit_dir = run_dir / "kit"
    (kit_dir / "assets/css").mkdir(parents=True, exist_ok=True)
    (kit_dir / "assets/js").mkdir(parents=True, exist_ok=True)
    template = load_prompt_template("kit_generation_" + kit_type.replace("-", "_"))
    imgs = [r["image_path"] for r in refs if r.get("image_path")][:KIT_REFERENCE_IMAGE_COUNT]
    while imgs and len(imgs) < KIT_REFERENCE_IMAGE_COUNT:
        imgs.append(imgs[-1])
    subs = {
        "{{KIT_DIR}}": str(kit_dir),
        "{{RUN_DIR}}": str(run_dir),
        "{{SIGNATURE_MOVE}}": concept.get("signature_move", ""),
    }
    for i in range(1, KIT_REFERENCE_IMAGE_COUNT + 1):
        subs[f"{{{{REF_IMAGE_{i}}}}}"] = str(imgs[i - 1]) if i <= len(imgs) else ""
    prompt = template
    for k, v in subs.items():
        prompt = prompt.replace(k, v)
    out = run_claude(prompt, effort="high", add_dirs=[VAULT_DIR, run_dir], tools="Read Write")
    (run_dir / "raw_kit_output.txt").write_text(out, encoding="utf-8")
    required = KIT_REQUIRED_FILES_BY_KIT_TYPE[kit_type]
    missing = [rel for rel in required
               if not (kit_dir / rel).exists() or (kit_dir / rel).stat().st_size == 0]
    if missing:
        raise RuntimeError(f"awwwards kit incomplete; missing/empty: {missing}; "
                           f"raw at {run_dir/'raw_kit_output.txt'}")
    return kit_dir


def _append_awwwards_telemetry(run_dir, kit_type, register_family, v):
    line = {
        "run": run_dir.name, "kit_type": kit_type, "register_family": register_family,
        "passed": v["passed"], "reasons": v["reasons"],
        "hero_scale": (v.get("rm") or {}).get("hero_scale_ratio"),
        "tells": (v.get("rm") or {}).get("template_tells"),
        "craft": (v.get("craft") or {}).get("verdict"),
    }
    p = PROJECT_ROOT / "state" / "quality_floor_telemetry.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")


def run_quality_gate(run_dir, kit_dir, kit_type, register_family, concept, shots):
    """Three gates → combined verdict. Lazy-imports the gate modules so an import
    error can never take down the conversion cron main()."""
    import awwwards_manifest, render_metrics, diversity_gate, craft_judge  # noqa: WPS433 (lazy)
    from quality_floor_config import QUALITY_FLOOR as QF  # noqa: WPS433
    reasons = []
    manifest_ok = True
    try:
        manifest = awwwards_manifest.parse_manifest((run_dir / "brief.md").read_text(encoding="utf-8"))
        merrs = awwwards_manifest.validate(manifest)
        if merrs:
            manifest_ok = False
            reasons.append(f"manifest invalid: {merrs}")
        (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    except awwwards_manifest.ManifestError as e:
        manifest_ok = False
        manifest = {"hero_archetype": None, "sections": [], "signature_move": ""}
        reasons.append(f"no manifest: {e}")
    rm = {}
    try:
        rm = render_metrics.render_metrics(kit_dir)
    except Exception as e:  # noqa: BLE001
        reasons.append(f"render_metrics failed: {e}")
    # A void is a broken/sparse gap and is ALWAYS gated — a gap this large is never
    # intentional negative space (both real premium kits measure <=1300px). The
    # earlier page-height carve-out made the void signal inert on tall pages, which
    # is exactly the page class (long premium AND padded-generic) it must police.
    void_bad = rm.get("max_vertical_void_px", 0) > QF["vertical_void_max_px"].get(kit_type, 2400)
    det_ok = (rm.get("hero_scale_ratio", 0) >= QF["hero_scale_min"]
              and len(rm.get("template_tells", [])) <= QF["template_tells_max"]
              and not void_bad)
    if not det_ok:
        reasons.append(f"genericness/density (hero={rm.get('hero_scale_ratio')}, "
                       f"tells={rm.get('template_tells')}, "
                       f"void={rm.get('max_vertical_void_px')}/h{rm.get('page_height_px')})")
    sig = diversity_gate.signature(manifest, rm, concept)
    repeat = False
    if manifest_ok:  # never compare/record a degenerate all-None signature
        repeat = diversity_gate.is_repeat(sig, diversity_gate.priors(register_family),
                                          QF["diversity_reject_below"])
        if repeat:
            reasons.append("structural repeat of a recent kit")
        diversity_gate.record(sig, register_family)
    craft = craft_judge.run(run_dir, kit_dir, kit_type, concept, shots,
                            run_claude=run_claude, load_prompt_template=load_prompt_template,
                            extract_json=_extract_json_object)
    if craft.get("verdict") != "pass":
        reasons.append(f"craft below_bar: {craft.get('reasons', '')}")
    passed = manifest_ok and det_ok and not repeat and craft.get("verdict") == "pass"
    v = {"passed": passed, "reasons": reasons, "rm": rm, "craft": craft, "sig": sig}
    (run_dir / "verdict.json").write_text(
        json.dumps({k: v[k] for k in ("passed", "reasons", "rm", "craft")}, indent=2), encoding="utf-8")
    _append_awwwards_telemetry(run_dir, kit_type, register_family, v)
    return v


def _finalize_awwwards_verdict(run_dir, v, kit_type):
    if v is None:
        log.error("no attempt produced a kit")
        return run_dir
    if v["passed"]:
        log.info("PASS (premium) — kit at %s/kit", run_dir)
        return run_dir
    # ship flagged: write sentinel + verdict INTO run_dir, THEN rename, THEN use the new path
    (run_dir / "DO_NOT_DEPLOY").write_text(
        "below_bar: " + "; ".join(v["reasons"]) + "\n", encoding="utf-8")
    flagged = run_dir.with_name(run_dir.name + "-flagged")
    run_dir.rename(flagged)
    log.warning("FLAGGED below_bar — %s (%s)", flagged, "; ".join(v["reasons"]))
    return flagged


def run_awwwards_oneshot(sub_aesthetic: str, kit_type: str) -> int:
    """Generate ONE awwwards kit end-to-end, gated (retry once → ship flagged)."""
    if kit_type not in KIT_REQUIRED_FILES_BY_KIT_TYPE:
        log.error("unknown kit_type %r (use editorial-studio|single-product)", kit_type)
        return 1
    cfg = get_awwwards_config(sub_aesthetic)  # raises KeyError on unknown sub_aesthetic
    if cfg.get("vault_pending"):
        log.error("sub_aesthetic %r is vault_pending — no anchors yet", sub_aesthetic)
        return 1
    seed = 0
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    run_dir = RUNS_DIR / f"{ts}-awwwards-{sub_aesthetic}-{kit_type}"
    run_dir.mkdir(parents=True, exist_ok=True)
    _setup_logging(run_dir)
    log.info("awwwards oneshot: %s / %s (seed=%d)", sub_aesthetic, kit_type, seed)
    t0 = time.monotonic()

    directives = awwwards_render.render_directives(sub_aesthetic, seed)
    vault_index = build_vault_index()
    refs = awwwards_render.retrieve_awwwards_refs(sub_aesthetic, kit_type, vault_index)
    need = cfg.get("min_exemplar_count", 2)
    if len(refs) < need:
        log.error("only %d premium refs for %s/%s (need >= %d) — corpus too thin",
                  len(refs), sub_aesthetic, kit_type, need)
        return 1
    log.info("retrieved %d premium refs (top: %s)", len(refs), refs[0]["payload"].get("title"))
    hero = refs[0]["payload"].get("hero_archetype", "monumental_wordmark")
    topo = refs[0]["payload"].get("section_topology", [])

    from quality_floor_config import QUALITY_FLOOR as QF  # noqa: WPS433 (lazy)
    register_family = cfg["register_family"]
    best = None
    for attempt in range(QF["retry"]["max"] + 1):
        perturb = (attempt == 0)
        recent = []
        if attempt > 0:
            if (time.monotonic() - t0) >= QF["run_budget_s"]:
                log.warning("run budget (%ds) exhausted — skipping retry, shipping flagged",
                            QF["run_budget_s"])
                break
            alt = next((r for r in refs[1:]
                        if r["payload"].get("hero_archetype") != hero), None)
            if alt is not None:
                hero = alt["payload"].get("hero_archetype", hero)
            recent = [(best.get("concept") or {}).get("hook_name", "")] if best else []
            log.info("retry: archetype=%s, palette perturbation OFF", hero)
        directives = awwwards_render.render_directives(sub_aesthetic, seed, perturb=perturb)
        try:
            concept = run_design_concept(sub_aesthetic, kit_type, hero, refs, recent, run_dir)
            synthesize_brief_awwwards(sub_aesthetic, kit_type, directives, hero, topo, concept, refs, run_dir)
            kit_dir = generate_kit_awwwards(run_dir / "brief.md", refs, run_dir, kit_type, directives, concept)
        except (RuntimeError, subprocess.TimeoutExpired, subprocess.CalledProcessError,
                ValueError, json.JSONDecodeError) as e:
            log.error("awwwards attempt %d aborted: %s", attempt, e)
            if best is None:
                return 1
            break
        raw = (run_dir / "raw_kit_output.txt").read_text(encoding="utf-8")
        if best is not None and raw == best.get("_raw"):
            log.info("retry produced byte-identical output — stopping")
            break
        try:
            from generate_kit_images import generate_kit_images as _gen_imgs  # noqa: WPS433
            _gen_imgs(kit_dir, run_dir, image_prefix_override=directives["photography_prefix"])
        except Exception as e:  # noqa: BLE001 — image gen non-fatal
            log.warning("image gen non-fatal: %s", e)
        pages = [f[:-5] for f in KIT_REQUIRED_FILES_BY_KIT_TYPE[kit_type] if f.endswith(".html")]
        shots = []
        try:
            capture_screenshots(kit_dir, run_dir, pages=pages)
            sd = kit_dir / "screenshots"
            shots = sorted(str(p) for p in sd.glob("*-desktop.png")) if sd.exists() else []
        except Exception as e:  # noqa: BLE001 — screenshots non-fatal
            log.warning("screenshots non-fatal: %s", e)
        v = run_quality_gate(run_dir, kit_dir, kit_type, register_family, concept, shots)
        v["concept"] = concept
        v["_raw"] = raw
        best = v
        log.info("attempt %d verdict: passed=%s reasons=%s", attempt, v["passed"], v["reasons"])
        if v["passed"]:
            break

    final_dir = _finalize_awwwards_verdict(run_dir, best, kit_type)
    log.info("DONE — %s", final_dir)
    return 0


# ─────────────────────────────────────────────────────────────────────
# main()
# ─────────────────────────────────────────────────────────────────────

def run_register_weekly() -> int:
    """Weekly cron entry: pick the next (sub, kit) in rotation and run the gated
    oneshot. On a corpus-thin failure (oneshot returns 1) advance to the next
    viable pair, bounded by the number of pairs so a fully-starved set fails once
    rather than looping forever."""
    import register_schedule  # noqa: WPS433 (lazy)
    pairs = register_schedule.active_pairs()
    if not pairs:
        log.error("register-weekly: no active sub-aesthetics")
        return 1
    for _ in range(len(pairs)):
        sub, kit = register_schedule.next_pair()
        log.info("register-weekly: attempting %s / %s", sub, kit)
        rc = run_awwwards_oneshot(sub, kit)
        if rc == 0:
            return 0
        log.warning("register-weekly: %s/%s did not ship (rc=%d) — trying next pair",
                    sub, kit, rc)
    log.error("register-weekly: no viable pair shipped a kit this run")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Workshop — generate one static-HTML kit per invocation."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="readiness_check + retrieve_inspiration only; no claude calls, no delivery",
    )
    parser.add_argument(
        "--awwwards-oneshot", nargs=2, metavar=("SUB_AESTHETIC", "KIT_TYPE"),
        help="Generate one awwwards kit via the v1.5 register (additive; bypasses the conversion queue).",
    )
    parser.add_argument(
        "--register-weekly", action="store_true",
        help="Weekly register cron: round-robin the active sub-aesthetics × kit-types through the gated pipeline.",
    )
    args = parser.parse_args()

    if args.awwwards_oneshot:
        _setup_logging()
        return run_awwwards_oneshot(*args.awwwards_oneshot)

    if args.register_weekly:
        _setup_logging()
        return run_register_weekly()

    _setup_logging()  # stdout + workshop.log; per-run handler added once run_dir exists
    lock = acquire_lock()
    if lock is None:
        log.info("another workshop run holds %s — exiting 0", LOCKFILE)
        return 0
    if not disk_check():
        return 1

    try:
        queue = load_queue()
    except FileNotFoundError as e:
        log.error("%s", e)
        return 1

    target = pick_next_target(queue)
    if target is None:
        return 0
    vertical, aesthetic = target

    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    run_dir = RUNS_DIR / f"{timestamp}-{vertical}-{aesthetic}"
    run_dir.mkdir(parents=True, exist_ok=True)
    _setup_logging(run_dir)
    log.info("run start: vertical=%s aesthetic=%s run_dir=%s", vertical, aesthetic, run_dir)

    # 1. Readiness gate — wrapped so Qdrant outages / network glitches
    # produce a Telegram alert + clean exit 1 instead of an uncaught
    # RuntimeError dying silently under systemd.
    try:
        count = readiness_check(vertical)
    except RuntimeError as e:
        log.exception("readiness_check failed for %s/%s", vertical, aesthetic)
        _workshop_send(
            f"⚠️ readiness_check failed for {vertical}/{aesthetic}: {str(e)[:200]}"
        )
        return 1
    log.info("readiness_check: %d/%d", count, VAULT_READINESS_THRESHOLD)
    if count < VAULT_READINESS_THRESHOLD:
        _workshop_send(
            f"vertical {vertical!r} has {count}/{VAULT_READINESS_THRESHOLD} "
            "references; skipping this run."
        )
        return 0

    # 2. Retrieve — wrapped because sl.embed (Vertex AI) and sl.rerank
    # (Cohere via OpenRouter) can both return 429 / RESOURCE_EXHAUSTED
    # and we want a clean alert instead of a silent systemd FAILURE.
    try:
        vault_index = build_vault_index()
        log.info("vault_index built: %d entries", len(vault_index))
        references = retrieve_inspiration(vertical, aesthetic, vault_index)
    except RuntimeError as e:
        log.exception("retrieve_inspiration failed for %s/%s", vertical, aesthetic)
        _workshop_send(
            f"⚠️ retrieve_inspiration failed for {vertical}/{aesthetic}: {str(e)[:200]}"
        )
        return 1
    if not references:
        log.error("retrieve_inspiration returned 0 — aborting")
        _workshop_send(
            f"⚠️ retrieve_inspiration returned 0 refs for {vertical}/{aesthetic}"
        )
        return 1
    log.info("retrieved %d references (top: %s)", len(references), references[0]["title"])

    if args.dry_run:
        # Persist the picks for inspection
        (run_dir / "references.json").write_text(
            json.dumps(
                [{k: (str(v) if isinstance(v, Path) else v)
                  for k, v in r.items() if k != "payload"}
                 for r in references],
                indent=2,
            ),
            encoding="utf-8",
        )
        log.info("dry-run complete; references saved to %s/references.json", run_dir)
        return 0

    # 3-5. Claude phases (each retries once on timeout/error then aborts the run)
    try:
        synthesize_brief(vertical, aesthetic, references, run_dir)
        kit_dir = generate_kit(
            run_dir / "brief.md", references, run_dir,
            vertical=vertical, aesthetic=aesthetic,
        )
        audit = self_audit(kit_dir, run_dir)
    except (RuntimeError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
        log.error("pipeline aborted: %s", e)
        _workshop_send(f"❌ run aborted: {e}\nrun_dir={run_dir}")
        return 1

    # 6. Image generation (v1.1) — Gemini Nano Banana 2.
    # Hard config errors (missing key, missing manifest, missing PIL) raise
    # ImageGenError; we catch and continue with picsum URLs untouched. Per-
    # image failures fall back to SVG inside the module without raising.
    images_status: dict[str, dict[str, Any]] = {}
    try:
        from generate_kit_images import (
            generate_kit_images as _generate_images,
            strip_picsum_audit_concerns as _strip_picsum_concerns,
            ImageGenError,
        )
        images_status = _generate_images(kit_dir, run_dir, aesthetic_direction=aesthetic)
        total_imgs = len(images_status)
        succ = sum(1 for v in images_status.values() if v.get("status") == "success")
        fb = sum(1 for v in images_status.values() if v.get("status") == "fallback")
        failed = sum(1 for v in images_status.values() if v.get("status") == "failed")
        log.info("image generation: %d/%d success, %d fallback, %d failed",
                 succ, total_imgs, fb, failed)
        # If at least one image succeeded, the picsum CDN concern is no longer
        # universally true — strip it from audit.md so the markdown reflects
        # post-replacement reality.
        if succ > 0:
            stripped = _strip_picsum_concerns(run_dir / "audit.md")
            if stripped:
                log.info("audit.md: stripped %d picsum-related audit concerns", stripped)
    except ImageGenError as e:
        log.error("image generation aborted (hard config failure): %s", e)
        _workshop_send(f"⚠️ image generation aborted: {e}\nkit ships with picsum URLs intact.")
    except Exception as e:
        log.error("image generation phase crashed unexpectedly: %s", e)
        _workshop_send(f"⚠️ image generation crashed: {e}\nrun_dir={run_dir}")

    # 7. Screenshots — non-fatal failure
    try:
        shots = capture_screenshots(kit_dir, run_dir)
    except Exception as e:
        log.warning("capture_screenshots failed (non-fatal): %s", e)
        shots = {}
        with (run_dir / "audit.md").open("a", encoding="utf-8") as f:
            f.write(f"\n## Screenshots\n\nscreenshot-failed: true\nreason: {e}\n")

    # 8. Deliver
    push_ok = deliver(kit_dir, run_dir, audit, shots, vertical, aesthetic, images_status)

    # 9. Update queue
    update_queue_after_run(queue, aesthetic)
    log.info("run complete: push_ok=%s", push_ok)
    return 0


if __name__ == "__main__":
    sys.exit(main())
