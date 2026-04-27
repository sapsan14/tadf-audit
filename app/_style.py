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
   Streamlit's defaults (verified by reading the static bundle):
     - stSidebarContent (Es)        position:relative; height:100%; overflow:auto
     - stSidebarHeader  (Os)        display:flex; justify-content:space-between;
                                    height:spacing.headerHeight   (≈3rem — clips a tall logo)
     - stSidebarUserContent (Ts)    plain block, no flex
   The footer pin is achieved by an explicit flex spacer rendered between
   the usage block and the footer in main.py — the spacer's stMarkdown
   wrapper gets flex:1 below, growing to consume all remaining vertical
   space. Auto-margin and absolute-positioning approaches both lost to
   Streamlit's stVerticalBlock wrapper between user content and the
   markdown elements. */

/* Sidebar inner container becomes a full-height flex column so user
   content can grow to fill remaining vertical space. */
section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{
    display: flex !important;
    flex-direction: column !important;
    min-height: 100vh !important;
}}

/* User content area: flex column that fills remaining space. The
   children (and Streamlit's stVerticalBlock wrapper) inherit this so
   the spacer below can grow. */
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{
    display: flex !important;
    flex-direction: column !important;
    flex: 1 1 auto !important;
    min-height: 0 !important;
}}

/* Streamlit wraps the sidebar children in a stVerticalBlock that's
   itself a flex column — make it grow to fill the user-content area. */
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > div {{
    display: flex !important;
    flex-direction: column !important;
    flex: 1 1 auto !important;
    min-height: 0 !important;
}}

/* The flex spacer (an empty div rendered between usage and footer in
   main.py) grows to push the footer all the way down. We target the
   stMarkdown wrapper that contains it. */
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] *:has(> .tadf-sidebar-spacer) {{
    flex: 1 1 auto !important;
    min-height: 1rem !important;
}}
.tadf-sidebar-spacer {{
    height: 100%;
    min-height: 1rem;
}}

/* ---- Logo header: taller, centered, allow the SVG full height ---- */
section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {{
    display: flex !important;
    justify-content: center !important;
    align-items: center !important;
    height: auto !important;
    min-height: 140px !important;
    padding: 1.25rem 0.5rem 0.75rem 0.5rem !important;
    margin-bottom: 0.5rem !important;
}}

/* ---- Logo: 110×110, centered ----
   Streamlit's testid is `stSidebarLogo`. The <img> emotion style sets
   `object-position: left` and a height keyed to theme.sizes.largeLogoHeight,
   with no width — so the IMG box could expand wider than its content and
   the SVG stuck to the left. Lock both dimensions and center it. */
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

/* No extra margin under the nav — usage block lands directly under
   "Правовая база" (the last menu item). */
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] {{
    margin-bottom: 0 !important;
}}

/* ---- Footer styling (positioning handled by the spacer above) ---- */
.tadf-sidebar-footer {{
    padding: 0.75rem 0.5rem 0.75rem 0.5rem;
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
