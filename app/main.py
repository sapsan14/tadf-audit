"""TADF Аудит — Streamlit Cloud entry point.

Streamlit Cloud is configured to point at this exact path (`app/main.py`),
so DON'T rename it. The sidebar nav label "TADF Ehitus" is set via
`st.navigation` + `st.Page(title=...)`, not derived from the filename.

This entry script owns three things that must run on EVERY page:
  1. layout (CSS max-width + wide mode)
  2. auth gate
  3. sidebar (logout + Claude usage tracker)

Pages then run via `nav.run()`. They no longer call `apply_consistent_layout`
or `require_login` themselves — Streamlit treats main + active page as one
script run, so set_page_config can only be called once (here).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure both the repo root and `src/` are on sys.path:
#   - repo root → `from app._style import …` (the `app/` package this file is in)
#   - src → `from tadf...` (the editable package, not pip-installed on Cloud)
# Locally cwd is the repo root and Python auto-adds it; on Streamlit Cloud
# only the entry script's directory (`app/`) is auto-added, so `from app.*`
# fails without this explicit insert.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src"))

import streamlit as st  # noqa: E402

from app._style import (  # noqa: E402
    apply_consistent_layout,
    render_sidebar_footer,
    render_sidebar_logo,
)

apply_consistent_layout("TADF Ehitus")

# Logo at the top of the sidebar — visible on every page (including the
# pre-auth login screen, since this runs before require_login).
render_sidebar_logo()


# ---------------------------------------------------------------------------
# Navigation — declared FIRST so the sidebar shows my custom labels even
# before auth completes. Without this, a pre-auth crash falls back to
# Streamlit's auto-discovery which shows "main" + raw filenames.
# ---------------------------------------------------------------------------
pages = [
    st.Page("TADF_Ehitus.py", title="TADF Ehitus", icon="🏗️", default=True),
    st.Page("pages/1_📝_Новый_аудит.py", title="Новый аудит", icon="📝"),
    st.Page("pages/2_🏠_Здание.py", title="Здание", icon="🏠"),
    st.Page("pages/3_🔍_Находки.py", title="Находки", icon="🔍"),
    st.Page("pages/4_📸_Фото.py", title="Фото", icon="📸"),
    st.Page("pages/5_📄_Готовый_отчёт.py", title="Готовый отчёт", icon="📄"),
    st.Page("pages/6_📚_Правовая_база.py", title="Правовая база", icon="📚"),
]
nav = st.navigation(pages, position="sidebar")


# ---------------------------------------------------------------------------
# Auth gate — st.stop()s if not logged in, so nav.run() below never executes
# for unauthenticated users.
# ---------------------------------------------------------------------------
from app._auth import logout_button, require_login  # noqa: E402

_auth = require_login()


# ---------------------------------------------------------------------------
# Authenticated-only setup: DB seed + sidebar widgets
# ---------------------------------------------------------------------------
from app._sidebar import render_usage_block  # noqa: E402
from tadf.config import ROOT  # noqa: E402
from tadf.corpus.preload import preload_corpus, preload_demo  # noqa: E402
from tadf.db.session import init_db  # noqa: E402

init_db()


@st.cache_resource
def _seed_db_once() -> tuple[int, int, int]:
    """Idempotent DB seeding. Returns (corpus_imports, corpus_skips, demo_inserts)."""
    audit_dir = ROOT / "audit"
    if audit_dir.exists():
        imp, skp = preload_corpus(audit_dir)
        return (imp, skp, 0)
    demo_count = preload_demo()
    return (0, 0, demo_count)


_seed_db_once()


with st.sidebar:
    user_display = st.session_state.get("name", "")
    if user_display:
        st.markdown(f"👤 **{user_display}**")
    logout_button(_auth, location="sidebar")
    st.markdown("---")
    render_usage_block()


# Run the active page (declared above)
nav.run()

# Version + copyright pinned to the bottom of the sidebar (CSS-flex pushed
# via margin-top: auto). Rendered after nav.run() so it lands as the last
# child of the sidebar's user-content flex column.
render_sidebar_footer()
