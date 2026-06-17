"""Workshop Floor — Tailnet dashboard for Scout-Workshop runs.

Reads existing run data from /opt/scout-workshop/workshop/runs/ and exposes
it as JSON endpoints + a single-page static frontend. Listens on the
Tailscale interface only; never public.

Future v1.4: when quality_floor_telemetry.jsonl exists, this app also reads
from that file for richer telemetry. Until then it synthesizes from
run.log + brief.md + audit.md per run dir.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiofiles
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO_ROOT / "workshop" / "runs"
# The refinery/third-system worktree (sw-garage) writes its experimental runs
# into its own workshop/runs. Must stay in sync with refinery_daily.ROOTS so
# the dashboard shows the same queue the refinery walks.
RUNS_ROOTS = (
    RUNS_DIR,
    Path("/home/deployer/sw-garage/workshop/runs"),
)
TELEMETRY_FILE = REPO_ROOT / "state" / "quality_floor_telemetry.jsonl"
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Workshop Floor", version="1.4.0-pre")


# ---- helpers ----------------------------------------------------------------


RUN_SLUG_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)-(?P<vertical>[a-z0-9]+)-(?P<aesthetic>[a-z0-9-]+)$"
)


def find_run_dir(slug: str) -> Path | None:
    """Resolve a run slug across all runs roots (first root wins)."""
    for root in RUNS_ROOTS:
        d = root / slug
        if d.is_dir():
            return d
    return None


def read_refinery_report(run_dir: Path) -> dict[str, Any] | None:
    """Compact view of the refinery (third system) result, or None if the
    refinery has not run on this kit yet."""
    rpath = run_dir / "refinery" / "refinery_report.json"
    if not rpath.exists():
        return None
    try:
        r = json.loads(rpath.read_text(errors="replace"))
    except (ValueError, OSError):
        return None
    return {
        "verdict": r.get("verdict"),
        "serious_history": r.get("serious_history") or [],
        "changed_files": len(r.get("changed_files") or []),
        "aborted": r.get("aborted") or "",
    }


def read_register_verdict(run_dir: Path) -> dict[str, Any] | None:
    """v1.5 register kits write verdict.json (the quality-gate result). Returns a
    compact view, or None for conversion-era runs that have no verdict.json.
    `flagged` = the kit was NOT deployable (dir renamed `…-flagged` or a
    DO_NOT_DEPLOY sentinel present)."""
    vpath = run_dir / "verdict.json"
    if not vpath.exists():
        return None
    try:
        v = json.loads(vpath.read_text(errors="replace"))
    except (ValueError, OSError):
        return None
    craft = v.get("craft") or {}
    flagged = run_dir.name.endswith("-flagged") or (run_dir / "DO_NOT_DEPLOY").exists()
    return {
        "passed": bool(v.get("passed")),
        "flagged": bool(flagged),
        "reasons": v.get("reasons") or [],
        "craft_verdict": craft.get("verdict"),
        "craft_scores": craft.get("scores") or {},
    }


def parse_run_dir(run_dir: Path) -> dict[str, Any] | None:
    """Read a single run directory and return a summary dict."""
    m = RUN_SLUG_RE.match(run_dir.name)
    if not m:
        return None
    ts = m.group("ts").replace("T", " ").replace("-", ":", 2).replace("-", "-", 1)
    # Convert back to ISO: "2026-05-17T01-00-02Z" -> "2026-05-17T01:00:02Z"
    ts_iso = re.sub(
        r"T(\d{2})-(\d{2})-(\d{2})Z", r"T\1:\2:\3Z", m.group("ts")
    )

    summary = {
        "slug": run_dir.name,
        "ts": ts_iso,
        "vertical": m.group("vertical"),
        "aesthetic": m.group("aesthetic"),
        "register": _infer_register(m.group("vertical"), m.group("aesthetic")),
        "audit_status": None,
        "warnings_count": 0,
        "warnings": [],
        "html_files": 0,
        "image_files": 0,
        "screenshot_files": [],
        "brief_excerpt": None,
        "bytes_index_html": 0,
        "sections_index_html": 0,
        "articles_index_html": 0,
        "gate_timings": [],
        "errors": [],
    }

    # v1.5 register quality-gate verdict (None for conversion-era runs)
    reg = read_register_verdict(run_dir)
    summary["register_verdict"] = reg
    summary["flagged"] = bool(reg and reg["flagged"])

    # Refinery (third system) result + fixed-copy preview availability
    summary["refinery"] = read_refinery_report(run_dir)
    summary["has_kit_fixed"] = (run_dir / "kit-fixed" / "index.html").exists()

    # Parse audit.md
    audit_path = run_dir / "audit.md"
    if audit_path.exists():
        text = audit_path.read_text(errors="replace")
        sm = re.search(r"\*\*Status:\*\*\s+(\w+)", text)
        if sm:
            summary["audit_status"] = sm.group(1)
        warnings = re.findall(r"^- (.+)$", text, re.MULTILINE)
        # filter to just Warnings section
        if "## Warnings" in text:
            warn_block = text.split("## Warnings", 1)[1].split("\n## ", 1)[0]
            summary["warnings"] = [
                w.strip().lstrip("- ") for w in warn_block.splitlines() if w.strip().startswith("- ")
            ]
        summary["warnings_count"] = len(summary["warnings"])

    # Parse brief.md (first paragraph after the aesthetic header)
    brief_path = run_dir / "brief.md"
    if brief_path.exists():
        text = brief_path.read_text(errors="replace")
        m2 = re.search(r"## Aesthetic\s*\n(.+?)(?=\n##|\Z)", text, re.DOTALL)
        if m2:
            excerpt = m2.group(1).strip().split("\n\n")[0]
            summary["brief_excerpt"] = excerpt[:400]

    # Inspect kit
    kit_dir = run_dir / "kit"
    if kit_dir.exists():
        for f in kit_dir.iterdir():
            if f.suffix == ".html":
                summary["html_files"] += 1
                if f.name == "index.html":
                    content = f.read_text(errors="replace")
                    summary["bytes_index_html"] = len(content)
                    summary["sections_index_html"] = len(re.findall(r"<section", content))
                    summary["articles_index_html"] = len(re.findall(r"<article", content))
        images_dir = kit_dir / "assets" / "images"
        if images_dir.exists():
            summary["image_files"] = sum(1 for _ in images_dir.iterdir())
        screenshots_dir = kit_dir / "screenshots"
        if screenshots_dir.exists():
            summary["screenshot_files"] = sorted(
                p.name for p in screenshots_dir.iterdir() if p.suffix in {".png", ".jpg"}
            )

    # Parse run.log for gate timings + errors
    log_path = run_dir / "run.log"
    if log_path.exists():
        text = log_path.read_text(errors="replace")
        for line in text.splitlines():
            if " ERROR " in line or " FAIL " in line:
                summary["errors"].append(line.strip()[:200])

    # Density heuristic (proxy for v1.4 gates until they land)
    sect = summary["sections_index_html"] + summary["articles_index_html"]
    if sect >= 10:
        summary["density"] = "rich"
    elif sect >= 6:
        summary["density"] = "ok"
    elif sect >= 4:
        summary["density"] = "thin"
    else:
        summary["density"] = "sparse"

    return summary


def _infer_register(vertical: str, aesthetic: str) -> str:
    if vertical == "awwwards":
        return "awwwards"
    awwwards_aesthetics = {
        "sun-baked",
        "acid-tech",
        "cool-jewel",
        "warm-earth",
        "editorial-mid-century",
    }
    if aesthetic in awwwards_aesthetics:
        return "awwwards"
    return "conversion"


def list_runs() -> list[dict[str, Any]]:
    dirs: dict[str, Path] = {}
    for root in RUNS_ROOTS:
        if not root.exists():
            continue
        for d in root.iterdir():
            if d.is_dir():
                dirs.setdefault(d.name, d)  # first root wins on collision
    results = []
    for name in sorted(dirs, reverse=True):
        r = parse_run_dir(dirs[name])
        if r:
            results.append(r)
    return results


def compute_stats(runs: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(runs)
    if total == 0:
        return {"total_runs": 0}
    pass_count = sum(1 for r in runs if r.get("audit_status") == "pass")
    warn_count = sum(1 for r in runs if r.get("audit_status") == "warn")
    fail_count = sum(1 for r in runs if r.get("audit_status") == "fail")
    register_count = sum(1 for r in runs if r.get("register_verdict"))
    register_pass_count = sum(
        1 for r in runs if (r.get("register_verdict") or {}).get("passed"))
    flagged_count = sum(1 for r in runs if r.get("flagged"))
    refined_count = sum(1 for r in runs
                        if (r.get("refinery") or {}).get("verdict")
                        in ("clean", "improved"))
    avg_warnings = sum(r.get("warnings_count", 0) for r in runs) / total
    densities = Counter(r.get("density", "unknown") for r in runs)
    registers = Counter(r.get("register", "unknown") for r in runs)
    aesthetics = Counter(r.get("aesthetic", "unknown") for r in runs)
    total_warnings = sum(r.get("warnings_count", 0) for r in runs)
    total_images = sum(r.get("image_files", 0) for r in runs)
    return {
        "total_runs": total,
        "pass_count": pass_count,
        "warn_count": warn_count,
        "fail_count": fail_count,
        "register_count": register_count,
        "register_pass_count": register_pass_count,
        "flagged_count": flagged_count,
        "refined_count": refined_count,
        "ship_rate_pct": int(((pass_count + warn_count) / total) * 100),
        "avg_warnings_per_run": round(avg_warnings, 1),
        "total_warnings": total_warnings,
        "total_images_generated": total_images,
        "densities": dict(densities),
        "registers": dict(registers),
        "aesthetics": dict(aesthetics.most_common(8)),
        "latest_run": runs[0] if runs else None,
    }


# ---- API --------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "runs_dir_exists": RUNS_DIR.exists(),
        "telemetry_file_exists": TELEMETRY_FILE.exists(),
        "version": "1.4.0-pre",
        "time": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/runs")
def api_runs(
    register: str | None = None,
    aesthetic: str | None = None,
    audit_status: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    runs = list_runs()
    if register:
        runs = [r for r in runs if r.get("register") == register]
    if aesthetic:
        runs = [r for r in runs if r.get("aesthetic") == aesthetic]
    if audit_status:
        runs = [r for r in runs if r.get("audit_status") == audit_status]
    return runs[:limit]


@app.get("/api/runs/{slug}")
def api_run_detail(slug: str) -> dict[str, Any]:
    run_dir = find_run_dir(slug)
    if run_dir is None:
        raise HTTPException(status_code=404, detail=f"run {slug} not found")
    summary = parse_run_dir(run_dir)
    if not summary:
        raise HTTPException(status_code=400, detail="malformed slug")
    # Add full brief + audit + log content
    for fname in ("brief.md", "audit.md", "run.log"):
        fpath = run_dir / fname
        if fpath.exists():
            summary[fname.replace(".", "_")] = fpath.read_text(errors="replace")
    return summary


@app.get("/api/stats")
def api_stats() -> dict[str, Any]:
    return compute_stats(list_runs())


@app.get("/api/screenshot/{slug}/{filename}")
def api_screenshot(slug: str, filename: str, w: int = 0) -> FileResponse:
    # Sanitize: must match expected pattern and stay inside runs dir
    if not RUN_SLUG_RE.match(slug):
        raise HTTPException(status_code=400, detail="malformed slug")
    if not re.match(r"^[a-z0-9_-]+\.(png|jpg|jpeg|webp)$", filename):
        raise HTTPException(status_code=400, detail="malformed filename")
    run_dir = find_run_dir(slug)
    if run_dir is None:
        raise HTTPException(status_code=404, detail=f"run {slug} not found")
    candidate = (run_dir / "kit" / "screenshots" / filename).resolve()
    # Path traversal defense
    if not str(candidate).startswith(str(run_dir.resolve())):
        raise HTTPException(status_code=403, detail="path traversal blocked")
    if not candidate.exists():
        raise HTTPException(status_code=404, detail="screenshot not found")
    if w and 80 <= w <= 1600:
        try:
            from PIL import Image
            tdir = Path("/tmp/sw-thumbs"); tdir.mkdir(parents=True, exist_ok=True)
            thumb = tdir / ("%s__%s__%d.jpg" % (slug, filename, w))
            if (not thumb.exists()) or thumb.stat().st_mtime < candidate.stat().st_mtime:
                im = Image.open(candidate)
                if im.mode in ("RGBA", "P", "LA"): im = im.convert("RGB")
                rh = max(1, int(im.height * (w / im.width)))
                im = im.resize((w, rh), Image.LANCZOS)
                if im.height > w * 4: im = im.crop((0, 0, w, w * 4))
                im.save(thumb, "JPEG", quality=78, optimize=True)
            return FileResponse(thumb, media_type="image/jpeg")
        except Exception:
            pass
    return FileResponse(candidate)


# ---- live kit preview -------------------------------------------------------
# Serve each run's kit/ as a live, interactive site so the dashboard can open the
# real page (motion + scroll), not just its screenshots. Read-only static serving,
# path-traversal-guarded to the run's kit/ directory.


def _no_kit_placeholder(slug: str, sub: str) -> Response:
    """A readable HTML page for runs that produced no kit/ (e.g. generation
    errored before writing HTML). Beats a raw {"detail": "..."} JSON 404 when a
    tab is opened directly. Status stays 404 — the resource genuinely is absent."""
    label = "refined kit" if sub == "kit-fixed" else "kit"
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>No {label} — {slug}</title>
<style>
  html,body{{height:100%;margin:0}}
  body{{display:grid;place-items:center;background:#14100c;color:#e8ddc8;
       font:400 16px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;padding:2rem}}
  .box{{max-width:46rem;text-align:center}}
  h1{{font-size:1.1rem;letter-spacing:.04em;color:#c98a3a;margin:0 0 1rem}}
  code{{color:#b9a98a;word-break:break-all}}
  a{{color:#e07b4f}}
</style></head><body><div class="box">
  <h1>No {label} for this run</h1>
  <p>This run did not produce output — generation likely errored before writing
     <code>{sub}/index.html</code>.</p>
  <p>Run: <code>{slug}</code></p>
  <p>Check <code>run.log</code> in the run directory for the failure reason,
     or <a href="/">return to the Workshop Floor</a>.</p>
</div></body></html>"""
    return Response(content=html, media_type="text/html", status_code=404)


def _serve_kit_file(slug: str, sub: str, file_path: str) -> Response:
    if not RUN_SLUG_RE.match(slug):
        raise HTTPException(status_code=400, detail="malformed slug")
    run_dir = find_run_dir(slug)
    if run_dir is None:
        raise HTTPException(status_code=404, detail=f"run {slug} not found")
    kit_root = (run_dir / sub).resolve()
    if not kit_root.is_dir():
        # Run produced no kit (failed generation). Degrade gracefully.
        return _no_kit_placeholder(slug, sub)
    candidate = (kit_root / (file_path or "index.html")).resolve()
    if not str(candidate).startswith(str(kit_root)):     # path traversal defense
        raise HTTPException(status_code=403, detail="path traversal blocked")
    if candidate.is_dir():
        candidate = candidate / "index.html"
    if not candidate.exists():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(candidate)


@app.get("/live/{slug}")
def live_root_redirect(slug: str) -> RedirectResponse:
    # Trailing slash so the kit's RELATIVE asset paths (assets/css/…) resolve under /live/<slug>/.
    return RedirectResponse(url=f"/live/{slug}/")


@app.get("/live/{slug}/{file_path:path}")
def live_kit(slug: str, file_path: str = "") -> Response:
    return _serve_kit_file(slug, "kit", file_path)


@app.get("/live-fixed/{slug}")
def live_fixed_root_redirect(slug: str) -> RedirectResponse:
    return RedirectResponse(url=f"/live-fixed/{slug}/")


@app.get("/live-fixed/{slug}/{file_path:path}")
def live_fixed_kit(slug: str, file_path: str = "") -> Response:
    # The refinery's kit-fixed/ copy — original kit/ is never touched.
    return _serve_kit_file(slug, "kit-fixed", file_path)


# ---- static -----------------------------------------------------------------


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
