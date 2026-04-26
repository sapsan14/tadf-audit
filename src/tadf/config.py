"""Project paths and feature flags. Single source of truth."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # /home/anton/projects/tadf
DATA_DIR = ROOT / "data"
AUDITS_DIR = DATA_DIR / "audits"
CORPUS_DIR = DATA_DIR / "corpus"
CACHE_DIR = DATA_DIR / "cache"
DB_PATH = ROOT / "tadf.db"
DB_URL = os.environ.get("TADF_DB_URL", f"sqlite:///{DB_PATH}")

# Feature flags
USE_LLM = os.environ.get("TADF_USE_LLM", "0") == "1"  # Phase 2
USE_SIGNING = os.environ.get("TADF_USE_SIGNING", "0") == "1"  # Phase 3

for d in (AUDITS_DIR, CORPUS_DIR, CACHE_DIR):
    d.mkdir(parents=True, exist_ok=True)
