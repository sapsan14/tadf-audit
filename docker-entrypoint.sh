#!/usr/bin/env bash
# TADF entrypoint — runs the FastAPI sidecar (port 8001) alongside the
# Streamlit UI (port 8501) in the same container. Caddy in front routes
# /api/* → 8001 and everything else → 8501.
#
# Both processes share the SQLite at /app/data/tadf.db. uvicorn is
# launched in the background; if it dies, the container keeps running
# (Streamlit is the primary process for the healthcheck).

set -euo pipefail

# Generate a random per-container HMAC secret if none is set. The secret
# only needs to be stable for the lifetime of the container so tokens
# issued by Streamlit validate against the FastAPI sidecar — both run in
# the same process tree, so a fresh-each-restart secret is fine and
# avoids leaking it via env from the compose file.
if [[ -z "${TADF_IMPORT_SECRET:-}" ]]; then
    export TADF_IMPORT_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')"
fi

# Sidecar — bind to 127.0.0.1 only, Caddy reaches us on the docker
# network via the container's exposed port.
uv run uvicorn tadf.api.app:app \
    --host 0.0.0.0 \
    --port 8001 \
    --log-level warning \
    --proxy-headers \
    &

# Streamlit (foreground — keeps the container alive, drives the
# healthcheck in the Dockerfile).
exec uv run streamlit run app/main.py \
    --server.address=0.0.0.0 \
    --server.port=8501 \
    --server.headless=true \
    --server.fileWatcherType=none \
    --browser.gatherUsageStats=false
