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

/* ---- Sidebar layout ----
   Force the inner container (stSidebarContent) to be a full-height flex
   column so the user-content area can grow to fill remaining vertical
   space — that's what lets the footer's margin-top:auto reach the
   viewport bottom. */
section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{
    display: flex !important;
    flex-direction: column !important;
    height: 100% !important;
    min-height: 100vh !important;
}}

/* User-content area expands and lays out its children as a flex column. */
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{
    display: flex !important;
    flex-direction: column !important;
    flex: 1 1 auto !important;
    min-height: 0 !important;
    padding-top: 1rem !important;
}}

/* Breathing room between the logo+nav block and the user content
   (the usage block sat too close to "Правовая база"). */
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] {{
    margin-bottom: 1rem !important;
}}

/* ---- Logo: fixed-square, flex-centered ----
   Streamlit's testid is `stSidebarLogo` (NOT `stLogo`). The actual <img>
   is an emotion-styled component (`Ms`) whose CSS forces
   `objectPosition: left` — that's why the SVG appeared left-anchored
   in a wider IMG box. We override BOTH the IMG size (force a square)
   and the object-position (center) so the SVG sits centered. The
   `class="stLogo"` selector is redundant with [data-testid] but adds
   specificity that beats emotion's atomic class. */
section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {{
    display: flex !important;
    justify-content: center !important;
    align-items: center !important;
    padding: 1.5rem 0.5rem 1rem 0.5rem !important;
}}
section[data-testid="stSidebar"] [data-testid="stSidebarLogo"],
section[data-testid="stSidebar"] img.stLogo,
section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] img {{
    height: 110px !important;
    max-height: 110px !important;
    width: 110px !important;
    min-width: 110px !important;
    max-width: 110px !important;
    object-fit: contain !important;
    object-position: center !important;
    background-size: contain !important;
    background-position: center !important;
    background-repeat: no-repeat !important;
    margin: 0 auto !important;
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
/* Pin the footer to the very bottom of the sidebar:
   - order: 999 forces its flex item to render visually last regardless of
     where in the DOM it was inserted (the footer is rendered *before* the
     auth gate so it shows on the login screen, but it must still sit
     under the post-auth user/logout block).
   - margin-top: auto consumes any leftover vertical space above it.
   :has() is widely supported (Chrome 105+, Safari 15.4+, Firefox 121+). */
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > *:has(.tadf-sidebar-footer) {{
    order: 999 !important;
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
