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

# Ensure `src/` is on sys.path so `from tadf...` works even when the package
# is not pip-installed (e.g. Streamlit Community Cloud builds).
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from app._style import apply_consistent_layout  # noqa: E402

apply_consistent_layout("TADF Ehitus")

from app._auth import logout_button, require_login  # noqa: E402

_auth = require_login()  # blocks rendering until the user is authenticated

import streamlit as st  # noqa: E402

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


# ---------------------------------------------------------------------------
# Sidebar (renders on every page)
# ---------------------------------------------------------------------------
with st.sidebar:
    user_display = st.session_state.get("name", "")
    if user_display:
        st.markdown(f"👤 **{user_display}**")
    logout_button(_auth, location="sidebar")
    st.markdown("---")
    render_usage_block()


# ---------------------------------------------------------------------------
# Navigation — explicit page declarations so we control titles + icons
# (filenames have to stay in app/pages/ for backward compatibility with the
# auto-discovery code path)
# ---------------------------------------------------------------------------
pages = [
    st.Page("TADF_Ehitus.py", title="Главная", icon="🏗️", default=True),
    st.Page("pages/1_📝_Новый_аудит.py", title="Новый аудит", icon="📝"),
    st.Page("pages/2_🏠_Здание.py", title="Здание", icon="🏠"),
    st.Page("pages/3_🔍_Находки.py", title="Находки", icon="🔍"),
    st.Page("pages/4_📸_Фото.py", title="Фото", icon="📸"),
    st.Page("pages/5_📄_Готовый_отчёт.py", title="Готовый отчёт", icon="📄"),
    st.Page("pages/6_📚_Правовая_база.py", title="Правовая база", icon="📚"),
]

st.navigation(pages, position="sidebar").run()
