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

/* Make the sidebar's user-content area a full-height flex column so the
   version footer at the bottom can be pushed there with margin-top: auto.
   Targets multiple Streamlit DOM versions (1.40+ uses stSidebarUserContent). */
[data-testid="stSidebarUserContent"],
[data-testid="stSidebar"] > div:first-child > div:nth-child(2) {{
    display: flex;
    flex-direction: column;
    min-height: calc(100vh - 4rem);
}}

/* Tighter sidebar padding so the logo + nav fit without scrolling. */
[data-testid="stSidebarUserContent"] {{
    padding-top: 1rem;
}}

/* Logo lives at the very top of the sidebar. */
.tadf-sidebar-logo {{
    text-align: center;
    margin-bottom: 0.75rem;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid rgba(128, 128, 128, 0.2);
}}
.tadf-sidebar-logo svg {{
    width: 70%;
    max-width: 180px;
    height: auto;
}}

/* Version footer pinned to the bottom of the sidebar by margin-top: auto. */
.tadf-sidebar-footer {{
    margin-top: auto;
    padding-top: 0.75rem;
    border-top: 1px solid rgba(128, 128, 128, 0.2);
    font-size: 0.72rem;
    color: rgba(128, 128, 128, 0.85);
    text-align: center;
    line-height: 1.4;
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
    """Logo at the top of the sidebar. Inlined as SVG so it inherits
    currentColor (works in light + dark theme without extra files)."""
    if not LOGO_PATH.exists():
        return
    svg = LOGO_PATH.read_text(encoding="utf-8")
    # Strip the XML prolog so the SVG can be inlined inside HTML
    if svg.startswith("<?xml"):
        svg = svg.split("?>", 1)[1].lstrip()
    st.sidebar.markdown(
        f'<div class="tadf-sidebar-logo">{svg}</div>',
        unsafe_allow_html=True,
    )


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
