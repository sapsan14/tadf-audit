"""Anthropic API client wrapper for TADF.

API key resolution order:
  1. ANTHROPIC_API_KEY env var
  2. ~/.anthropic/key file (per Fjodor's preference — same key shared with
     other Anthropic tools)
  3. Streamlit secrets (st.secrets["ANTHROPIC_API_KEY"]) when running on Cloud

Includes a persistent JSON cache keyed by sha256(model + prompt + section_key)
so re-rendering the same audit doesn't re-hit the API. Anthropic prompt
caching is also enabled via top-level `cache_control` on every call so the
long stable system prefix is billed at ~10 % of the standard input rate.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from anthropic import Anthropic

from tadf.config import CACHE_DIR
from tadf.llm.usage import record as _record_usage

LLM_CACHE_DIR = CACHE_DIR / "llm"
LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Per the original Phase 2 plan: Sonnet for prose-heavy tasks, Haiku for fast
# classification + vision. Both support adaptive thinking and prompt caching.
MODEL_DRAFTER = "claude-sonnet-4-6"
MODEL_POLISH = "claude-sonnet-4-6"
MODEL_CAPTION = "claude-haiku-4-5"
MODEL_RANKER = "claude-haiku-4-5"


class MissingAPIKey(RuntimeError):
    """Raised when no API key can be found anywhere."""


def _load_api_key() -> str | None:
    """Resolve the Anthropic API key from env / ~/.anthropic/key / streamlit secrets."""
    if v := os.environ.get("ANTHROPIC_API_KEY"):
        return v.strip()
    key_file = Path.home() / ".anthropic" / "key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    try:
        import streamlit as st

        if "ANTHROPIC_API_KEY" in st.secrets:
            return str(st.secrets["ANTHROPIC_API_KEY"]).strip()
    except Exception:
        pass
    return None


@functools.lru_cache(maxsize=1)
def _client() -> Anthropic:
    key = _load_api_key()
    if not key:
        raise MissingAPIKey(
            "No Anthropic API key found. Set ANTHROPIC_API_KEY, write a key to "
            "~/.anthropic/key, or add it to Streamlit Secrets."
        )
    return Anthropic(api_key=key)


def is_available() -> bool:
    """True if the API key resolves and the client can be constructed."""
    try:
        _client()
        return True
    except MissingAPIKey:
        return False


# ---------------------------------------------------------------------------
# Persistent cache
# ---------------------------------------------------------------------------
def _cache_key(model: str, system: str, user: str, extra: str = "") -> str:
    h = hashlib.sha256()
    for piece in (model, system, user, extra):
        h.update(piece.encode("utf-8"))
        h.update(b"\x1e")  # record separator
    return h.hexdigest()[:32]


def _cache_path(key: str) -> Path:
    return LLM_CACHE_DIR / f"{key}.json"


def _cache_get(key: str) -> Any | None:
    p = _cache_path(key)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _cache_put(key: str, value: Any) -> None:
    _cache_path(key).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------
def complete_text(
    *,
    model: str,
    system: str,
    user: str,
    max_tokens: int = 2000,
    cache: bool = True,
) -> str:
    """Plain text completion with prompt caching + persistent JSON cache."""
    key = _cache_key(model, system, user)
    if cache and (cached := _cache_get(key)):
        return cached["text"]

    resp = _client().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
    )
    text = next((b.text for b in resp.content if b.type == "text"), "").strip()
    _record_usage(model, resp.usage)
    if cache:
        _cache_put(key, {"text": text, "model": model})
    return text


def complete_json(
    *,
    model: str,
    system: str,
    user: str,
    schema: dict[str, Any],
    max_tokens: int = 1000,
    cache: bool = True,
) -> dict[str, Any]:
    """Structured-output completion. `schema` is a JSON schema dict."""
    key = _cache_key(model, system, user, json.dumps(schema, sort_keys=True))
    if cache and (cached := _cache_get(key)):
        return cached["data"]

    resp = _client().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )
    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    _record_usage(model, resp.usage)
    data = json.loads(text)
    if cache:
        _cache_put(key, {"data": data, "model": model})
    return data


def complete_with_image(
    *,
    model: str,
    system: str,
    image_bytes: bytes,
    image_media_type: str,
    user_text: str,
    max_tokens: int = 500,
    cache: bool = True,
) -> str:
    """Vision completion. Image is sent as base64."""
    import base64

    image_b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    image_hash = hashlib.sha256(image_bytes).hexdigest()[:16]
    key = _cache_key(model, system, user_text, image_hash)
    if cache and (cached := _cache_get(key)):
        return cached["text"]

    resp = _client().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": image_media_type,
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": user_text},
                ],
            }
        ],
    )
    text = next((b.text for b in resp.content if b.type == "text"), "").strip()
    _record_usage(model, resp.usage)
    if cache:
        _cache_put(key, {"text": text, "model": model})
    return text
