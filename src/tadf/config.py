"""Project paths and feature flags. Single source of truth.

Designed to work both locally (writable repo dir) and on Streamlit Cloud
(repo dir is read-only — must fall back to a writable location like $HOME).
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # repo root


def _writable(preferred: Path, fallback_name: str) -> Path:
    """Return `preferred` if we can write to it, else $HOME/<fallback_name>."""
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        probe = preferred / ".write_probe"
        probe.write_text("ok")
        probe.unlink(missing_ok=True)
        return preferred
    except (OSError, PermissionError):
        alt = Path.home() / fallback_name
        alt.mkdir(parents=True, exist_ok=True)
        return alt


DATA_DIR = _writable(ROOT / "data", ".tadf-data")
AUDITS_DIR = DATA_DIR / "audits"
CORPUS_DIR = DATA_DIR / "corpus"
CACHE_DIR = DATA_DIR / "cache"

# DB lives next to the data dir so a backup script can grab everything together.
_DEFAULT_DB = DATA_DIR / "tadf.db"
DB_PATH = Path(os.environ.get("TADF_DB_PATH", _DEFAULT_DB))
DB_URL = os.environ.get("TADF_DB_URL", f"sqlite:///{DB_PATH}")

# Feature flags
USE_LLM = os.environ.get("TADF_USE_LLM", "0") == "1"  # Phase 2
USE_SIGNING = os.environ.get("TADF_USE_SIGNING", "0") == "1"  # Phase 3

for d in (AUDITS_DIR, CORPUS_DIR, CACHE_DIR):
    d.mkdir(parents=True, exist_ok=True)


def is_streamlit_cloud() -> bool:
    """Best-effort detection of Streamlit Community Cloud runtime."""
    return (
        os.environ.get("STREAMLIT_SHARING_MODE") is not None
        or "/mount/src/" in str(ROOT)
        or os.environ.get("HOSTNAME", "").startswith("streamlit")
    )
