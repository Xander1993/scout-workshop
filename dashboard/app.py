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
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO_ROOT / "workshop" / "runs"
TELEMETRY_FILE = REPO_ROOT / "state" / "quality_floor_telemetry.jsonl"
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Workshop Floor", version="1.4.0-pre")


# ---- helpers ----------------------------------------------------------------


RUN_SLUG_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)-(?P<vertical>[a-z0-9]+)-(?P<aesthetic>[a-z0-9-]+)$"
)


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
    if not RUNS_DIR.exists():
        return []
    results = []
    for d in sorted(RUNS_DIR.iterdir(), key=lambda p: p.name, reverse=True):
        if d.is_dir():
            r = parse_run_dir(d)
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
    run_dir = RUNS_DIR / slug
    if not run_dir.exists() or not run_dir.is_dir():
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
def api_screenshot(slug: str, filename: str) -> FileResponse:
    # Sanitize: must match expected pattern and stay inside runs dir
    if not RUN_SLUG_RE.match(slug):
        raise HTTPException(status_code=400, detail="malformed slug")
    if not re.match(r"^[a-z0-9_-]+\.(png|jpg|jpeg|webp)$", filename):
        raise HTTPException(status_code=400, detail="malformed filename")
    candidate = (RUNS_DIR / slug / "kit" / "screenshots" / filename).resolve()
    # Path traversal defense
    if not str(candidate).startswith(str(RUNS_DIR.resolve())):
        raise HTTPException(status_code=403, detail="path traversal blocked")
    if not candidate.exists():
        raise HTTPException(status_code=404, detail="screenshot not found")
    return FileResponse(candidate)


# ---- static -----------------------------------------------------------------


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
