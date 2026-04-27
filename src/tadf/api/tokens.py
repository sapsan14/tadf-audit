"""Per-audit HMAC tokens for the import API.

The Streamlit "Open in EHR" / "Open in Teatmik" buttons wrap a token like
`<audit_id>:<expiry>:<hmac>` into the URL fragment they hand to the
browser. The in-browser helper (bookmarklet or userscript) reads it from
`location.hash` and ships it back via `Authorization: Bearer <token>`.

The FastAPI side verifies the HMAC against `TADF_IMPORT_SECRET` (set as
an environment variable on Hetzner). If the secret isn't configured we
fall back to a random per-process key — that way local dev works
without setup, but production tokens issued from one process won't be
honoured by another.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

_TOKEN_TTL_SECONDS = 7 * 24 * 3600  # 7 days — matches the typical audit work cycle
_SEPARATOR = ":"


def _secret() -> bytes:
    env = os.environ.get("TADF_IMPORT_SECRET")
    if env:
        return env.encode("utf-8")
    # Cache an in-process random key so all tokens issued in this process
    # validate. NOT suitable for multi-process production — set the env var.
    global _FALLBACK
    try:
        return _FALLBACK
    except NameError:
        pass
    _FALLBACK = secrets.token_bytes(32)
    return _FALLBACK


_FALLBACK: bytes  # populated lazily by _secret()


def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def issue(audit_id: int, ttl_seconds: int = _TOKEN_TTL_SECONDS) -> str:
    """Return a token that authorises imports into `audit_id` for ttl_seconds."""
    expiry = int(time.time()) + ttl_seconds
    payload = f"{audit_id}{_SEPARATOR}{expiry}"
    sig = _sign(payload)
    return f"{payload}{_SEPARATOR}{sig}"


def verify(token: str) -> int | None:
    """Return audit_id if the token is valid and not expired, else None."""
    if not token:
        return None
    parts = token.split(_SEPARATOR)
    if len(parts) != 3:
        return None
    audit_id_s, expiry_s, sig = parts
    try:
        audit_id = int(audit_id_s)
        expiry = int(expiry_s)
    except ValueError:
        return None
    if expiry < int(time.time()):
        return None
    expected = _sign(f"{audit_id}{_SEPARATOR}{expiry}")
    if not hmac.compare_digest(sig, expected):
        return None
    return audit_id


__all__ = ["issue", "verify"]
