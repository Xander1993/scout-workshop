"""scout_lib.py — Shared helpers for the Scout-Workshop pipeline.

Public functions:
    embed(text, image_path=None)        OpenRouter Gemini Embedding 2 Preview
                                        (multimodal falls back to text-only on
                                        failure; logs WARN; see embed_with_mode)
    embed_with_mode(text, image_path)   Returns (vector, mode_str) so callers
                                        can detect "multimodal" vs
                                        "multimodal-fallback" vs "text"
    rerank(query, documents, top_k)     OpenRouter Cohere Rerank 4 Pro
    firecrawl_scrape(url)               Firecrawl with Playwright fallback
    playwright_scrape(url)              Headless Chromium scraper + screenshot
    screenshot(url, output_path=None)   Full-page Playwright screenshot
    qdrant_client_init()                QdrantClient + collection self-heal
                                        (strict dim+distance check on existing)
    qdrant_insert(point_id, vec, pl)    Single-point upsert
    qdrant_query(vector, filters, lim)  Vector search with metadata filters
    telegram_send(message, chat_ids)    Multi-recipient delivery, 4000-char split
    load_env()                          Cached .env loader

All HTTP calls retry on 429/5xx with exponential backoff (max 5 attempts).
Errors propagate with context: URL, model name, attempt count.
"""

from __future__ import annotations

import base64
import functools
import hashlib
import json
import logging
import os
import re
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import requests
import yaml
from dotenv import dotenv_values
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

# ────────────────────────────────────────────────────────────────────────
# Constants
# ────────────────────────────────────────────────────────────────────────

ROOT = Path("/opt/scout-workshop")
ENV_PATH = ROOT / ".env"
SCREENSHOTS_DIR = ROOT / "state" / "screenshots"

COLLECTION = "scout_workshop"
VECTOR_SIZE = 3072

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_EMBED_URL = f"{OPENROUTER_BASE}/embeddings"
OPENROUTER_RERANK_URL = f"{OPENROUTER_BASE}/rerank"

INDEXED_FIELDS = {
    "reference_type": PayloadSchemaType.KEYWORD,
    "vertical": PayloadSchemaType.KEYWORD,
    "techniques": PayloadSchemaType.KEYWORD,
    "color_mood": PayloadSchemaType.KEYWORD,
    "typography_style": PayloadSchemaType.KEYWORD,
    "layout_pattern": PayloadSchemaType.KEYWORD,
}

# OpenRouter recommends sending these headers for analytics/leaderboard.
_OPENROUTER_HEADERS_EXTRA = {
    "HTTP-Referer": "https://camelotflows.dev",
    "X-Title": "scout-workshop",
}

# Module logger. Configure at the application entry point if you want WARN
# messages (notably multimodal-embedding fallbacks) to surface to a file or
# Telegram. By default they propagate to the root logger.
log = logging.getLogger("scout_workshop")


# ────────────────────────────────────────────────────────────────────────
# Env loader
# ────────────────────────────────────────────────────────────────────────


@functools.lru_cache(maxsize=1)
def load_env() -> dict[str, str]:
    """Load /opt/scout-workshop/.env once and cache the result.

    Returns:
        Dict of env var name -> string value. Empty values are dropped.

    Raises:
        FileNotFoundError if the .env file is missing.
    """
    if not ENV_PATH.exists():
        raise FileNotFoundError(f"Expected env file at {ENV_PATH}")
    raw = dotenv_values(ENV_PATH)
    return {k: v for k, v in raw.items() if v}


# ────────────────────────────────────────────────────────────────────────
# Retry helper
# ────────────────────────────────────────────────────────────────────────


def _retry(fn, *, max_attempts: int = 5, base_delay: float = 1.0, context: str = ""):
    """Exponential-backoff retry on 429 and 5xx HTTP errors and connection errors.

    Args:
        fn: Zero-arg callable that performs the HTTP call.
        max_attempts: Total attempts including the first.
        base_delay: Seconds. Delay is base_delay * 2^(attempt-1).
        context: Human-readable description for error messages.

    Returns:
        Whatever fn returns on success.

    Raises:
        RuntimeError if all attempts fail. The original exception is chained.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if status not in (429, 500, 502, 503, 504):
                raise
            last_exc = exc
        except requests.RequestException as exc:
            last_exc = exc
        if attempt < max_attempts:
            time.sleep(base_delay * (2 ** (attempt - 1)))
    raise RuntimeError(
        f"Retry exhausted after {max_attempts} attempts ({context}): {last_exc}"
    ) from last_exc


# ────────────────────────────────────────────────────────────────────────
# Embeddings
# ────────────────────────────────────────────────────────────────────────


def _extract_vec(data: dict, model: str) -> list[float]:
    """Pull the 1536-dim vector out of an OpenRouter embeddings response.

    Raises:
        RuntimeError if the response shape is unexpected.
        ValueError if the vector dim does not match VECTOR_SIZE.
    """
    try:
        vec = data["data"][0]["embedding"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(
            f"Unexpected embedding response shape from {model}: {data}"
        ) from exc
    if len(vec) != VECTOR_SIZE:
        raise ValueError(
            f"Embedding returned {len(vec)} dims; expected {VECTOR_SIZE} from {model}"
        )
    return vec


def _embed_text(text: str, model: str, api_key: str) -> list[float]:
    """Text-only embedding via OpenRouter. Raises on any failure (no fallback)."""
    payload = {"model": model, "input": text, "dimensions": VECTOR_SIZE}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        **_OPENROUTER_HEADERS_EXTRA,
    }

    def _call():
        r = requests.post(OPENROUTER_EMBED_URL, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        return r.json()

    data = _retry(_call, context=f"embed (text) model={model}")
    return _extract_vec(data, model)


def _embed_multimodal(text: str, image_path: str, model: str, api_key: str) -> list[float]:
    """Multimodal text+image embedding via OpenRouter.

    Payload shape empirically confirmed via curl probes on 2026-05-05 (Variant A):
    `input` is a list of objects each with a `content` array of typed parts.
    Variants B (single object) and C (flat array of typed parts) both return
    OpenRouter ZodError 422. `dimensions` is passed explicitly even though the
    model defaults to 3072, to make the contract self-documenting.
    """
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    ext = path.suffix.lower().lstrip(".")
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(ext, "jpeg")
    img_b64 = base64.b64encode(path.read_bytes()).decode()

    payload = {
        "model": model,
        "dimensions": VECTOR_SIZE,
        "input": [
            {
                "content": [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{img_b64}"}},
                ]
            }
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        **_OPENROUTER_HEADERS_EXTRA,
    }

    def _call():
        r = requests.post(OPENROUTER_EMBED_URL, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        return r.json()

    data = _retry(_call, context=f"embed (multimodal) model={model}")
    return _extract_vec(data, model)


def embed_with_mode(text: str, image_path: str | None = None) -> tuple[list[float], str]:
    """Embedding with explicit mode signal so callers can detect fallback.

    Args:
        text: Anchor text. Always required.
        image_path: Optional local image path. When provided, the multimodal
            path is attempted first; on any failure (network, payload shape,
            wrong dim, etc.) the function logs a WARNING and falls back to
            text-only embedding of `text`.

    Returns:
        (vector, mode) tuple. `vector` is always a 3072-dim list[float].
        `mode` is one of:
            - "text"                — text-only request, no image given.
            - "multimodal"          — multimodal request, succeeded.
            - "multimodal-fallback" — multimodal failed, returned text-only.

    Callers that need to know whether they got true multimodal should check
    mode == "multimodal" before, e.g., storing distinctiveness scores that
    assume image-aware embeddings.
    """
    env = load_env()
    api_key = env["OPENROUTER_API_KEY"]
    model = env.get("EMBEDDING_MODEL", "google/gemini-embedding-2-preview")

    if image_path is None:
        return _embed_text(text, model, api_key), "text"

    try:
        return _embed_multimodal(text, image_path, model, api_key), "multimodal"
    except Exception as exc:
        log.warning(
            "Multimodal embedding failed (model=%s, image=%s, err=%s: %s); "
            "falling back to text-only embedding. Investigate OpenRouter payload "
            "shape — see TODO in scout_lib._embed_multimodal().",
            model,
            image_path,
            type(exc).__name__,
            exc,
        )
        return _embed_text(text, model, api_key), "multimodal-fallback"


def embed(text: str, image_path: str | None = None) -> list[float]:
    """Generate a 3072-dim embedding via OpenRouter Gemini Embedding 2 Preview.

    Args:
        text: Anchor text. Required.
        image_path: Optional local PNG/JPEG/WebP path for multimodal embedding.

    Returns:
        3072-element list of floats. If multimodal is requested but fails, this
        function silently falls back to text-only embedding of `text` (a WARNING
        is logged via the `scout_workshop` logger). Callers that need to detect
        fallback should use embed_with_mode() instead.

    Raises:
        FileNotFoundError if image_path is set but the file is absent.
        ValueError if the API returns a vector of unexpected dimension.
        RuntimeError if both multimodal and text-only paths fail after retries.
    """
    vec, _mode = embed_with_mode(text, image_path)
    return vec


# ────────────────────────────────────────────────────────────────────────
# Reranking — Day 1's stub was untested and returned tuples; replaced by
# the Day 2 §4 version below (returns list[dict] including document text).
# ────────────────────────────────────────────────────────────────────────


# ────────────────────────────────────────────────────────────────────────
# Scraping
# ────────────────────────────────────────────────────────────────────────


def _sha_url(url: str) -> str:
    """Stable 32-char prefix of SHA-256(url) for filename derivation."""
    return hashlib.sha256(url.encode()).hexdigest()[:32]


def screenshot(url: str, output_path: str | None = None) -> str:
    """Capture a full-page screenshot via headless Chromium.

    Args:
        url: URL to screenshot.
        output_path: Destination path. Defaults to
            state/screenshots/<sha>.png.

    Returns:
        Absolute path to the saved PNG.
    """
    from playwright.sync_api import sync_playwright

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        output_path = str(SCREENSHOTS_DIR / f"{_sha_url(url)}.png")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            page = ctx.new_page()
            page.goto(url, wait_until="networkidle", timeout=30_000)
            page.screenshot(path=output_path, full_page=True)
        finally:
            browser.close()
    return output_path


def playwright_scrape(url: str) -> dict[str, Any]:
    """Playwright-based scraper with main-content extraction and screenshot.

    Returns:
        Dict with keys:
            markdown: str (plain text from main/article/body innerText)
            html: str (full page HTML)
            metadata: {title, description, source_url}
            screenshot_path: str (path to PNG under state/screenshots/)
    """
    from playwright.sync_api import sync_playwright

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    shot_path = SCREENSHOTS_DIR / f"{_sha_url(url)}.png"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            page = ctx.new_page()
            page.goto(url, wait_until="networkidle", timeout=30_000)
            page.screenshot(path=str(shot_path), full_page=True)

            html = page.content()
            title = page.title()
            description = page.evaluate(
                "() => document.querySelector('meta[name=\"description\"]')?.content || ''"
            )
            text = page.evaluate(
                """() => {
                    const el = document.querySelector('main')
                           || document.querySelector('article')
                           || document.body;
                    return el ? el.innerText : '';
                }"""
            )
        finally:
            browser.close()

    return {
        "markdown": text,
        "html": html,
        "metadata": {
            "title": title,
            "description": description,
            "source_url": url,
        },
        "screenshot_path": str(shot_path),
    }


def firecrawl_scrape(url: str) -> dict[str, Any]:
    """Scrape via Firecrawl; fall back to Playwright on thin/error/timeout.

    Returns the same shape as playwright_scrape.

    Falls back when:
        - FIRECRAWL_API_KEY is missing
        - Firecrawl raises any exception
        - Returned markdown is shorter than 500 characters
    """
    env = load_env()
    api_key = env.get("FIRECRAWL_API_KEY")
    if not api_key:
        return playwright_scrape(url)

    try:
        from firecrawl import FirecrawlApp

        app = FirecrawlApp(api_key=api_key)
        # firecrawl-py's signature has shifted across releases; try modern then legacy.
        try:
            result = app.scrape_url(url, formats=["markdown", "html"], timeout=30_000)
        except TypeError:
            result = app.scrape_url(url, params={"formats": ["markdown", "html"], "timeout": 30_000})
    except Exception:
        return playwright_scrape(url)

    if not isinstance(result, dict):
        # Some firecrawl-py versions return a Pydantic model — coerce to dict.
        try:
            result = result.model_dump()
        except Exception:
            return playwright_scrape(url)

    md = result.get("markdown") or ""
    if len(md) < 500:
        return playwright_scrape(url)

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    shot_path = SCREENSHOTS_DIR / f"{_sha_url(url)}.png"
    if not shot_path.exists():
        try:
            screenshot(url, str(shot_path))
        except Exception:
            pass  # Screenshot is bonus; don't fail the scrape if it errors.

    metadata = result.get("metadata") or {}
    return {
        "markdown": md,
        "html": result.get("html") or "",
        "metadata": {
            "title": metadata.get("title", ""),
            "description": metadata.get("description", ""),
            "source_url": url,
        },
        "screenshot_path": str(shot_path) if shot_path.exists() else "",
    }


# ────────────────────────────────────────────────────────────────────────
# Qdrant
# ────────────────────────────────────────────────────────────────────────


@functools.lru_cache(maxsize=1)
def qdrant_client_init() -> QdrantClient:
    """Return a connected QdrantClient and ensure the collection exists.

    Self-heals: if the collection is absent, creates it with the documented
    schema and indexes. If present, strictly validates that both the vector
    dimension AND the distance metric match the expected schema. Either
    mismatch raises ValueError with a clear discrepancy message — this guards
    against test pollution from earlier exploratory runs that may have
    created a same-named collection with different parameters.

    Raises:
        ValueError if an existing collection has the wrong vector dimension
        or the wrong distance metric.
    """
    env = load_env()
    host = env.get("QDRANT_HOST", "localhost")
    port = int(env.get("QDRANT_PORT_REST", "6333"))
    client = QdrantClient(host=host, port=port)

    if client.collection_exists(COLLECTION):
        info = client.get_collection(COLLECTION)
        existing_dim = info.config.params.vectors.size
        existing_dist_obj = info.config.params.vectors.distance
        # Distance is an enum (qdrant_client.http.models.Distance);
        # compare by name, case-insensitive, to be tolerant of client variants.
        existing_dist_name = (
            existing_dist_obj.name
            if hasattr(existing_dist_obj, "name")
            else str(existing_dist_obj)
        ).upper()
        expected_dist_name = Distance.COSINE.name.upper()

        problems = []
        if existing_dim != VECTOR_SIZE:
            problems.append(f"dim={existing_dim} (expected {VECTOR_SIZE})")
        if existing_dist_name != expected_dist_name:
            problems.append(
                f"distance={existing_dist_name} (expected {expected_dist_name})"
            )
        if problems:
            raise ValueError(
                f"Collection '{COLLECTION}' has mismatched schema: "
                f"{'; '.join(problems)}. Refusing to use. Inspect with "
                f"`curl http://localhost:6333/collections/{COLLECTION}` and "
                f"either delete and recreate, or rename the existing collection."
            )
        return client

    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
    )
    for field, schema in INDEXED_FIELDS.items():
        client.create_payload_index(
            collection_name=COLLECTION,
            field_name=field,
            field_schema=schema,
        )
    return client


def qdrant_insert(point_id: str, vector: list[float], payload: dict[str, Any]) -> None:
    """Upsert a single point into scout_workshop.

    Args:
        point_id: Deterministic UUID string. Recommended derivation:
            ``str(uuid.uuid5(uuid.NAMESPACE_URL, source_url))``.
            Using uuid5 makes re-scrapes idempotent (same URL → same point).
        vector: 1536-dim embedding from `embed()`.
        payload: Metadata dict matching the documented schema.
    """
    client = qdrant_client_init()
    client.upsert(
        collection_name=COLLECTION,
        points=[PointStruct(id=point_id, vector=vector, payload=payload)],
    )


def qdrant_query(
    vector: list[float],
    filters: dict[str, Any] | None = None,
    limit: int = 20,
) -> list[Any]:
    """Vector search with optional metadata filters.

    Args:
        vector: 3072-dim query embedding.
        filters: Dict mapping payload field name to either a single value
            (str) or a list of values (any-of). Use a list for `techniques`
            and any other multi-valued field. Examples::

                {"vertical": "lawyer"}
                {"techniques": ["parallax", "magnetic-buttons"]}
                {"vertical": "beauty-salon", "color_mood": "warm-feminine"}

        limit: Max hits.

    Returns:
        List of qdrant_client ScoredPoint objects.
    """
    client = qdrant_client_init()
    qfilter: Filter | None = None
    if filters:
        must: list[FieldCondition] = []
        for key, val in filters.items():
            if isinstance(val, list):
                must.append(FieldCondition(key=key, match=MatchAny(any=val)))
            else:
                must.append(FieldCondition(key=key, match=MatchValue(value=val)))
        qfilter = Filter(must=must)

    return client.query_points(
        collection_name=COLLECTION,
        query=vector,
        query_filter=qfilter,
        limit=limit,
    ).points


# ────────────────────────────────────────────────────────────────────────
# Telegram
# ────────────────────────────────────────────────────────────────────────


_TELEGRAM_CHUNK = 4000  # Telegram hard limit is 4096; leave headroom for prefix.


def telegram_send(message: str, chat_ids: list[str] | None = None) -> None:
    """Send a message to one or more Telegram chats.

    Splits at _TELEGRAM_CHUNK boundary and prefixes multi-part messages with
    "[i/N]" continuation indicators.

    Args:
        message: The body text. Plain text only (no parse_mode).
        chat_ids: Override list of chat IDs. Defaults to the comma-separated
            TELEGRAM_CHAT_IDS env var.

    Raises:
        ValueError if no chat IDs are configured.
        RuntimeError if a send fails after retries.
    """
    env = load_env()
    token = env["TELEGRAM_BOT_TOKEN"]
    if chat_ids is None:
        raw = env.get("TELEGRAM_CHAT_IDS", "")
        chat_ids = [c.strip() for c in raw.split(",") if c.strip()]
    if not chat_ids:
        raise ValueError("No Telegram chat IDs configured (TELEGRAM_CHAT_IDS empty)")

    chunks: list[str] = []
    remaining = message
    while remaining:
        chunks.append(remaining[:_TELEGRAM_CHUNK])
        remaining = remaining[_TELEGRAM_CHUNK:]
    n = len(chunks)
    if n > 1:
        chunks = [f"[{i + 1}/{n}]\n{c}" for i, c in enumerate(chunks)]

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for chat_id in chat_ids:
        for chunk in chunks:
            def _call(c=chunk, cid=chat_id):
                r = requests.post(
                    url,
                    json={
                        "chat_id": cid,
                        "text": c,
                        "disable_web_page_preview": True,
                    },
                    timeout=15,
                )
                r.raise_for_status()
                return r.json()

            _retry(_call, context=f"telegram chat={chat_id}")


# =============================================================================
# Day 2 additions — vault-bus model, daemon helpers, source utilities.
# =============================================================================

# Aliases for Day 1 symbols — avoid rewriting Day 1 in case anything else
# (Workshop on Day 3, hermes touch points, etc.) imports the original names.
qdrant_client = qdrant_client_init   # Day 1 named the constructor qdrant_client_init
COLLECTION_NAME = COLLECTION         # Day 1 named the constant COLLECTION

VAULT_DIR = Path(os.environ.get("VAULT_DIR", "/opt/scout-workshop/vault"))
STATE_DIR = Path(os.environ.get("STATE_DIR", "/opt/scout-workshop/state"))
LOG_DIR = Path(os.environ.get("LOG_DIR", "/opt/scout-workshop/logs"))


# ----- ID & dedup --------------------------------------------------------

def stable_url_hash(url: str, length: int = 16) -> str:
    """Short hex hash of a URL — used for filesystem slugs and seen-urls dedup index.

    NOT used as a Qdrant point ID. Qdrant only accepts unsigned ints or UUIDs;
    hex strings get rejected at upsert. Use `stable_point_id()` for that.
    """
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:length]


def stable_point_id(url: str) -> str:
    """Deterministic UUID v5 derived from URL. THIS is the Qdrant point ID.

    Same URL → same UUID, on any machine, across replays. This guarantees
    that re-ingesting the same reference is idempotent — Qdrant.upsert with
    the same point_id overwrites cleanly, no duplicates.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_URL, url.strip()))


def slugify(text: str, max_len: int = 40) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:max_len].rstrip("-")


def reference_slug(url: str, title: str) -> str:
    """Filesystem-friendly slug for vault/references/<source>/<slug>/. Not a point ID."""
    return f"{stable_url_hash(url, 8)}-{slugify(title)}"


# ----- State files -------------------------------------------------------

def load_state(name: str) -> dict:
    path = STATE_DIR / name
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(name: str, data: dict) -> None:
    path = STATE_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)  # atomic on same fs


def is_seen(url: str, seen_index: dict) -> bool:
    h = stable_url_hash(url)
    for entry in seen_index.get("urls", []):
        if entry.get("hash") == h:
            return True
    return False


def mark_seen(url: str, outcome: str, seen_index: dict) -> dict:
    h = stable_url_hash(url)
    seen_index.setdefault("urls", []).append({
        "url": url,
        "hash": h,
        "first_seen": iso_now(),
        "outcome": outcome,
    })
    return seen_index


# ----- Time --------------------------------------------------------------

def iso_now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


# ----- Vault note I/O ----------------------------------------------------

def parse_note(path: Path) -> tuple[dict, str]:
    """Parse a markdown note with YAML frontmatter. Returns (frontmatter, body)."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"No frontmatter in {path}")
    _, fm, body = text.split("---\n", 2)
    return yaml.safe_load(fm), body.lstrip("\n")


def write_note(path: Path, frontmatter: dict, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fm_yaml = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
    path.write_text(f"---\n{fm_yaml}\n---\n\n{body.strip()}\n", encoding="utf-8")


def find_unembedded_notes(vault_root: Path = VAULT_DIR) -> list[Path]:
    """Walk vault/references/ and return notes whose qdrant_point_id is null/missing."""
    refs_root = vault_root / "references"
    if not refs_root.exists():
        return []
    pending = []
    for note_path in refs_root.rglob("note.md"):
        try:
            fm, _ = parse_note(note_path)
        except Exception:
            continue
        if not fm.get("qdrant_point_id"):
            pending.append(note_path)
    return pending


# ----- Qdrant payload mapping --------------------------------------------

PAYLOAD_FIELDS = (
    "id source source_url scraped_at title vertical reference_type "
    "techniques color_mood typography_style layout_pattern palette_hex"
).split()


def frontmatter_to_payload(fm: dict) -> dict:
    return {k: fm.get(k) for k in PAYLOAD_FIELDS if k in fm}


def upsert_reference(point_id: str, vector: list[float], payload: dict) -> None:
    """Upsert a single reference into the scout_workshop collection.

    Uses the modern qdrant-client API (>=1.7) which is what we standardized on Day 1.
    """
    qdrant_client().upsert(
        collection_name=COLLECTION_NAME,
        points=[PointStruct(id=point_id, vector=vector, payload=payload)],
    )


def reference_already_indexed(point_id: str) -> bool:
    res = qdrant_client().retrieve(
        collection_name=COLLECTION_NAME,
        ids=[point_id],
        with_payload=False,
        with_vectors=False,
    )
    return len(res) > 0


# ----- Git operations ----------------------------------------------------

def git(*args: str, cwd: Path = VAULT_DIR, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=check, capture_output=True, text=True,
    )


def vault_pull() -> bool:
    """Pull vault. Returns True if there were new commits, False otherwise."""
    before = git("rev-parse", "HEAD").stdout.strip()
    git("pull", "--rebase", "--autostash")
    after = git("rev-parse", "HEAD").stdout.strip()
    return before != after


def vault_commit(message: str, paths: list[Path]) -> Optional[str]:
    """Stage paths, commit, return commit sha or None if nothing to commit."""
    rel = [str(p.relative_to(VAULT_DIR)) for p in paths]
    git("add", *rel)
    status = git("status", "--porcelain").stdout.strip()
    if not status:
        return None
    git("commit", "-m", message)
    return git("rev-parse", "HEAD").stdout.strip()


def vault_push(max_attempts: int = 3) -> None:
    """Push vault to origin/main with rebase-on-conflict retry.

    Conflicts can happen when the Routine commits at 06:00 UTC while the
    daemon's 06:00 timer tick is mid-flight, or when you push from your
    laptop in parallel. Handle by pulling-rebasing-and-retrying up to
    max_attempts times. Don't auto-resolve merge conflicts — those raise
    the underlying CalledProcessError to caller.
    """
    last_err: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            git("push", "origin", "main")
            return
        except subprocess.CalledProcessError as e:
            last_err = e
            if attempt == max_attempts:
                break
            git("pull", "--rebase", "--autostash", "origin", "main")
            time.sleep(attempt * 5)
    if last_err is not None:
        raise last_err


# ----- Telegram ----------------------------------------------------------

def send_telegram(text: str, chat_id: Optional[str] = None) -> dict:
    # Convention (matches Day 1's _embed_text/_embed_multimodal): every lib
    # function that needs secrets calls load_env() and reads from its result.
    # This makes the function work from any caller — systemd (EnvironmentFile=
    # populates os.environ), interactive shell (load_env reads .env from disk),
    # cron, or pytest. Don't read os.environ[KEY] directly — that raises
    # KeyError when the caller didn't source .env.
    env = load_env()
    chat_id = chat_id or env["TELEGRAM_CHAT_IDS"].split(",")[0].strip()
    token = env["TELEGRAM_BOT_TOKEN"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


# ----- Cohere reranking (smoke + Workshop later) -------------------------
#
# Replaces Day 1's stub `rerank(query, documents, top_k)` (returned
# list[tuple[int, float]] without the document text). The Day 2 version
# returns dicts including the document text, which Workshop (Day 3) will need.

def rerank(query: str, candidates: list[str], top_n: int = 5) -> list[dict]:
    """Cohere Rerank 4 Pro via OpenRouter.

    Returns a list of {index, relevance_score, document} dicts, sorted desc.
    """
    # See send_telegram() above for the rationale on load_env() over os.environ.
    env = load_env()
    payload = {
        "model": "cohere/rerank-4-pro",
        "query": query,
        "documents": candidates,
        "top_n": min(top_n, len(candidates)),
    }
    r = requests.post(
        "https://openrouter.ai/api/v1/rerank",
        headers={
            "Authorization": f"Bearer {env['OPENROUTER_API_KEY']}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("results", [])
