"""Structure-weighted diversity gate (design §11).

Distance over STRUCTURE (archetype + section topology + type-scale + concept);
palette is excluded (weight 0 — the proven no-op). Repeat if the new kit is
within `threshold` of any prior kit in the same register_family.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path


def _dl(a: list, b: list) -> int:
    """Damerau-Levenshtein distance over two token lists (with transposition).
    Hand-rolled — no Levenshtein/rapidfuzz in the venv."""
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    d = [[0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        d[i][0] = i
    for j in range(lb + 1):
        d[0][j] = j
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[la][lb]


def signature(manifest: dict, render_m: dict, concept: dict) -> dict:
    sections = manifest.get("sections") or []
    hsr = render_m.get("hero_scale_ratio", 0)
    bucket = "xl" if hsr >= 12 else "l" if hsr >= 6 else "m" if hsr >= 4 else "s"
    hook = (concept or {}).get("hook_name") or (concept or {}).get("signature_move", "")
    return {
        "archetype": manifest.get("hero_archetype"),
        "sections": list(sections),
        "type_scale_bucket": bucket,
        "concept_bucket": hashlib.sha256(hook.encode()).hexdigest()[:8],
    }


def distance(a: dict, b: dict) -> float:
    arch = 0.0 if a.get("archetype") == b.get("archetype") else 1.0
    sa, sb = a.get("sections") or [], b.get("sections") or []
    topo = _dl(sa, sb) / max(len(sa), len(sb), 1)
    ts = 0.0 if a.get("type_scale_bucket") == b.get("type_scale_bucket") else 1.0
    concept = 0.0 if a.get("concept_bucket") == b.get("concept_bucket") else 1.0
    return round(0.35 * arch + 0.30 * min(topo, 1.0) + 0.20 * ts + 0.15 * concept, 3)


def is_repeat(sig: dict, priors: list[dict], threshold: float = 0.34) -> bool:
    return any(distance(sig, p) < threshold for p in priors)


# ----- bounded ring store (repo-root state/, what the dashboard reads) -----
_STORE = Path("/opt/scout-workshop/state/structural_signatures.json")


def _load() -> dict:
    if _STORE.exists():
        try:
            return json.loads(_STORE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def priors(register_family: str) -> list[dict]:
    return _load().get(register_family, [])


def record(sig: dict, register_family: str, cap: int = 24) -> None:
    data = _load()
    lst = data.setdefault(register_family, [])
    lst.append(sig)
    data[register_family] = lst[-cap:]
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: a kill mid-write must not corrupt this CROSS-RUN state (a
    # truncated store would poison every future week's diversity gate).
    tmp = _STORE.with_name(_STORE.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, _STORE)
