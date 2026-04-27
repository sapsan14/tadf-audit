"""FastAPI sidecar — receives data POSTed by the in-browser helpers
(bookmarklet + Tampermonkey userscript). Runs alongside Streamlit on
port 8001 in production; Caddy routes `/api/*` to it.

Token-based auth: each TADF audit has a per-audit HMAC token that the
Streamlit "Open in EHR/Teatmik" buttons embed in the URL fragment;
the in-browser helper reads it from `location.hash` and includes it in
the POST. Tokens expire after 24 hours.
"""

from tadf.api.app import app

__all__ = ["app"]
