"""Shared page setup — consistent layout + max-width across entry + all pages.

Streamlit's `set_page_config` only applies to the script that calls it.
With the auto-discovered `pages/` directory, navigating to a sub-page does
NOT re-run the entry script, so any layout config on the entry alone
doesn't propagate. Each page must call `apply_consistent_layout()` first.

The CSS pins `.block-container` to a comfortable centered width
(neither Streamlit's narrow default nor edge-to-edge wide).
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from tadf import __copyright__, __version__

PAGE_MAX_WIDTH_PX = 1100
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
FAVICON_PATH = ASSETS_DIR / "favicon.svg"
LOGO_PATH = ASSETS_DIR / "logo.svg"


def _page_icon():
    """Use the bundled SVG favicon when present, fall back to an emoji.

    Streamlit accepts a string path, an emoji, or a PIL Image. The SVG is
    smaller than a PNG and scales to any tab/touchbar size.
    """
    if FAVICON_PATH.exists():
        return str(FAVICON_PATH)
    return "🏗️"


def apply_consistent_layout(page_title: str = "TADF Ehitus") -> None:
    """Call as the FIRST st.* command in every page script."""
    st.set_page_config(
        page_title=page_title,
        page_icon=_page_icon(),
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(
        f"""
<style>
[data-testid="stMainBlockContainer"], .main .block-container {{
    max-width: {PAGE_MAX_WIDTH_PX}px;
    margin: 0 auto;
    padding-top: 2rem;
    padding-bottom: 3rem;
    padding-left: 2rem;
    padding-right: 2rem;
}}

/* ---- Sidebar layout ---- */

/* Make the user-content area a flex column that fills the remaining space
   below the logo + nav. Footer with margin-top:auto then pins to the
   bottom; logout/usage stack at the top, just below the nav. */
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{
    display: flex !important;
    flex-direction: column !important;
    flex: 1 1 auto !important;
    min-height: 0 !important;
    padding-top: 0.5rem !important;
}}

/* Tighten the gap between nav and the logout/usage block. */
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] {{
    margin-bottom: 0.25rem !important;
}}

/* ---- Logo: stretch to full sidebar width ---- */
section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {{
    padding: 0.75rem 0.75rem 0.5rem 0.75rem !important;
}}
section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] > a,
section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] > div {{
    width: 100% !important;
    max-width: 100% !important;
    display: block !important;
}}
section[data-testid="stSidebar"] [data-testid="stLogo"],
section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] img {{
    width: 100% !important;
    max-width: 100% !important;
    height: auto !important;
    max-height: none !important;
    display: block !important;
    object-fit: contain !important;
}}

/* ---- Footer pinned at the very bottom of the sidebar ---- */
.tadf-sidebar-footer {{
    padding: 0.75rem 0.5rem 0.5rem 0.5rem;
    border-top: 1px solid rgba(128, 128, 128, 0.2);
    font-size: 0.72rem;
    color: rgba(128, 128, 128, 0.85);
    text-align: center;
    line-height: 1.5;
}}
.tadf-sidebar-footer a {{
    color: inherit;
    text-decoration: none;
    border-bottom: 1px dotted rgba(128, 128, 128, 0.5);
}}
/* Push the footer's wrapper element (and any of its parents up to the
   stSidebarUserContent flex column) to the bottom via margin-top:auto.
   :has() is widely supported (Chrome 105+, Safari 15.4+, Firefox 121+). */
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > *:has(.tadf-sidebar-footer),
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > *:last-child {{
    margin-top: auto !important;
}}
</style>
""",
        unsafe_allow_html=True,
    )


def render_sidebar_logo() -> None:
    """Logo at the very top of the sidebar — *above* st.navigation.

    Uses st.logo() (Streamlit ≥ 1.34), which has a privileged slot at the
    top of the sidebar that custom widgets can't reach. The icon_image is
    used when the sidebar is collapsed.
    """
    if not LOGO_PATH.exists():
        return
    kwargs: dict = {"size": "large"}
    if FAVICON_PATH.exists():
        kwargs["icon_image"] = str(FAVICON_PATH)
    try:
        st.logo(str(LOGO_PATH), **kwargs)
    except Exception:
        # Older Streamlit without st.logo() — fall back to st.image.
        st.sidebar.image(str(LOGO_PATH), width="stretch")


def render_sidebar_footer() -> None:
    """Version + copyright pinned to the bottom of the sidebar."""
    st.sidebar.markdown(
        f"""
<div class="tadf-sidebar-footer">
    <strong>TADF Аудит</strong> v{__version__}<br>
    {__copyright__}<br>
    <a href="https://github.com/sapsan14/tadf-audit" target="_blank">GitHub</a>
</div>
""",
        unsafe_allow_html=True,
    )
