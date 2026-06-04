"""Generate images via the local Codex CLI's built-in image_gen tool.

This is the OAuth path (the ChatGPT-authenticated `codex` session, NOT an
OpenAI API key) — the workshop's image backend / fallback when the Gemini quota
is exhausted. Each call shells out to `codex exec`, which uses its built-in
image_gen tool to produce a bitmap and copy it to the requested path.

Proven on 2026-06-04: codex-cli 0.136.0-alpha.2, model gpt-5.5, ~90s/image,
premium editorial quality, no API key required.
"""
from __future__ import annotations

import glob
import logging
import os
import subprocess
from pathlib import Path

log = logging.getLogger("workshop")

# codex image_gen honours a natural-language aspect hint well enough; we don't
# hard-reject on aspect drift (codex output is premium and roughly on-ratio).
_ASPECT_HINT = {
    "16:9": "16:9 landscape",
    "9:16": "9:16 portrait",
    "1:1": "square 1:1",
    "4:3": "4:3 landscape",
    "3:4": "3:4 portrait",
}
_HOME = os.path.expanduser("~")
_CODEX_HOME = os.environ.get("CODEX_HOME", os.path.join(_HOME, ".codex"))


def _codex_bin() -> str | None:
    """Resolve the codex binary: $CODEX_BIN, then PATH, then the ChatGPT VSCode
    extension's bundled binary (newest version)."""
    env = os.environ.get("CODEX_BIN")
    if env and Path(env).exists():
        return env
    from shutil import which
    onpath = which("codex")
    if onpath:
        return onpath
    hits = sorted(glob.glob(
        f"{_HOME}/.vscode-server/extensions/openai.chatgpt-*/bin/linux-x86_64/codex"))
    return hits[-1] if hits else None


def available() -> bool:
    return _codex_bin() is not None


def _valid_image(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < 1024:
        return False
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.verify()
        return True
    except Exception:  # noqa: BLE001 — a non-decodable file is a failed gen
        return False


def generate_image(prompt: str, aspect_ratio: str, out_path, timeout_s: int = 420) -> bool:
    """Generate ONE image to `out_path` via codex. Returns True only when a
    decodable non-empty image lands at out_path. NEVER raises (image gen is
    non-fatal to a workshop run)."""
    codex = _codex_bin()
    if codex is None:
        log.warning("codex imagegen: binary not found")
        return False
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if out_path.exists():
            out_path.unlink()
    except OSError:
        pass
    hint = _ASPECT_HINT.get(aspect_ratio, aspect_ratio)
    instruction = (
        "Use your built-in image_gen tool to generate ONE high-end photographic image. "
        f"Prompt: {prompt} Aspect ratio: {hint}. "
        f"After it is generated, copy the final image file to exactly {out_path} "
        "(overwrite if it exists). Do not write or modify any other files. "
        "Reply with only: DONE or FAILED:<reason>."
    )
    env = {**os.environ, "HOME": _HOME, "CODEX_HOME": _CODEX_HOME}
    try:
        r = subprocess.run(
            [codex, "exec", "--dangerously-bypass-approvals-and-sandbox",
             "--skip-git-repo-check",
             # image_gen does the work — deep reasoning only adds latency/variance.
             "-c", "model_reasoning_effort=low",
             "-C", str(out_path.parent), instruction],
            capture_output=True, text=True, timeout=timeout_s, env=env,
        )
    except subprocess.TimeoutExpired:
        log.warning("codex imagegen timed out after %ds for %s", timeout_s, out_path.name)
        return False
    except Exception as e:  # noqa: BLE001
        log.warning("codex imagegen failed to launch: %s", e)
        return False
    if _valid_image(out_path):
        return True
    log.warning("codex imagegen produced no valid image (rc=%s) for %s; tail=%s",
                r.returncode, out_path.name, (r.stdout or r.stderr or "")[-200:])
    return False
