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
    padding-bottom: 5rem;
    padding-left: 2rem;
    padding-right: 2rem;
}}

/* Persistent footer at the very bottom of the main column. */
.tadf-footer {{
    margin-top: 4rem;
    padding-top: 1.25rem;
    border-top: 1px solid rgba(128, 128, 128, 0.25);
    color: rgba(128, 128, 128, 0.85);
    font-size: 0.82rem;
    text-align: center;
}}
.tadf-footer a {{
    color: inherit;
    text-decoration: none;
    border-bottom: 1px dotted rgba(128, 128, 128, 0.5);
}}
</style>
""",
        unsafe_allow_html=True,
    )


def render_footer() -> None:
    """Version + copyright line at the bottom of every page. Call last."""
    st.markdown(
        f"""
<div class="tadf-footer">
    <strong>TADF Аудит</strong> v{__version__}  ·  {__copyright__}  ·
    <a href="https://github.com/sapsan14/tadf-audit" target="_blank">GitHub</a>
</div>
""",
        unsafe_allow_html=True,
    )
