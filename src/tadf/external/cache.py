"""Generic SHA256-keyed file cache, namespaced under data/cache/<namespace>/.

Used by:
  - llm/client.py via the legacy `_cache_get` / `_cache_put` thin wrappers
    (namespace = "llm").
  - external/ehr_client.py for EHR.ee lookups (namespace = "ehr").
  - external/teatmik_client.py for Teatmik.ee lookups (namespace = "teatmik").
  - llm/extractor.py for project-doc extraction results (namespace = "extract").

TTL semantics: callers pass `ttl_days` to `cache_get`. Entries past TTL are
treated as missing AND deleted from disk so the cache doesn't grow unboundedly.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from tadf.config import CACHE_DIR


def cache_key(*pieces: str) -> str:
    """sha256 over `\\x1e`-separated pieces, truncated to 32 hex chars."""
    h = hashlib.sha256()
    for piece in pieces:
        h.update(piece.encode("utf-8"))
        h.update(b"\x1e")
    return h.hexdigest()[:32]


def _path(namespace: str, key: str) -> Path:
    folder = CACHE_DIR / namespace
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{key}.json"


def cache_get(namespace: str, key: str, ttl_days: int | None = None) -> Any | None:
    """Return cached value or None.

    If `ttl_days` is given and the entry is older than that, treat as missing
    AND unlink the stale file.
    """
    p = _path(namespace, key)
    if not p.exists():
        return None
    if ttl_days is not None:
        age_seconds = time.time() - p.stat().st_mtime
        if age_seconds > ttl_days * 86400:
            with contextlib.suppress(OSError):
                p.unlink()
            return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def cache_put(namespace: str, key: str, value: Any) -> None:
    """Write value as JSON. Atomic via tmp + rename."""
    p = _path(namespace, key)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)
