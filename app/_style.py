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
   Force the WHOLE sidebar to be a full-height flex column so the user
   content area can occupy all remaining vertical space, and the footer's
   margin-top:auto can push it to the viewport bottom. Without this, the
   sidebar's outer container is block-layout and the user content collapses
   to fit-content height — leaving a big empty gap below the footer. */
section[data-testid="stSidebar"] > div:first-child {{
    display: flex !important;
    flex-direction: column !important;
    height: 100% !important;
}}

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

/* ---- Logo: fixed-square, flex-centered ----
   The SVG artwork is square (viewBox 800×800). st.logo() renders the image
   either as <img> or as a div with background-image (varies by Streamlit
   build), so we fix BOTH dimensions explicitly and center the wrapper via
   flex on the header itself (text-align/inline-block didn't center reliably
   because Streamlit's wrapper has its own inline width). */
section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {{
    display: flex !important;
    justify-content: center !important;
    align-items: center !important;
    padding: 1.25rem 0.5rem 0.75rem 0.5rem !important;
}}
section[data-testid="stSidebar"] [data-testid="stLogo"] {{
    height: 96px !important;
    width: 96px !important;
    background-size: contain !important;
    background-position: center !important;
    background-repeat: no-repeat !important;
    object-fit: contain !important;
}}
section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] img {{
    height: 96px !important;
    width: auto !important;
    max-width: 100% !important;
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
