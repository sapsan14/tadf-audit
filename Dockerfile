# TADF Аудит — production Streamlit container
#
# Multi-arch (amd64 + arm64). Built and pushed to GHCR by
# .github/workflows/deploy-hetzner.yml, then pulled by docker compose
# on the Hetzner host.
#
# uv is used for install (faster than pip and the same lockfile we use
# in dev). The image is small enough on slim-bookworm — no need for an
# alpine variant.

FROM python:3.12-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# OS deps — minimal. Streamlit + Python deps cover everything the
# deployed demo needs. Legacy .doc parsing (libreoffice) and scanned-PDF
# OCR (tesseract) are NOT installed: they're only used by the local
# corpus preload which runs against `/audit/` (gitignored), absent from
# the server. To enable on a derived image, add:
#   apt-get install -y libreoffice tesseract-ocr tesseract-ocr-est
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl libgomp1 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# uv binary (single static file, no Python deps)
COPY --from=ghcr.io/astral-sh/uv:0.9.27 /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first for layer caching — only invalidated when
# pyproject.toml or uv.lock change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Now copy source and install the local package (tadf) into the venv.
COPY app ./app
COPY src ./src
COPY scripts ./scripts
RUN uv sync --frozen --no-dev

# Streamlit config + master template (latter is generated from build_master.py
# but checked into git so we don't need libreoffice at build time).
COPY .streamlit ./.streamlit

# Pre-create the writable runtime dir owned by app uid; bind-mount in
# docker-compose puts a real Docker volume here so SQLite + photos persist.
RUN mkdir -p /app/data && useradd --create-home --uid 1000 app && chown -R app:app /app
USER app

# `auth.yaml` is mounted at runtime (gitignored), not baked in.

ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 8501

# `--server.address=0.0.0.0` so Caddy on the host can reach us via the
# docker network. Healthcheck hits the standard /_stcore/health endpoint.
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=4 \
    CMD curl -fsS http://127.0.0.1:8501/_stcore/health || exit 1

CMD ["uv", "run", "streamlit", "run", "app/main.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--server.fileWatcherType=none", \
     "--browser.gatherUsageStats=false"]
