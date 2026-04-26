"""Shared page setup — consistent layout + max-width across entry + all pages.

Streamlit's `set_page_config` only applies to the script that calls it.
With the auto-discovered `pages/` directory, navigating to a sub-page does
NOT re-run the entry script, so any layout config on the entry alone
doesn't propagate. Each page must call `apply_consistent_layout()` first.

The CSS pins `.block-container` to a comfortable centered width
(neither Streamlit's narrow default nor edge-to-edge wide).
"""

from __future__ import annotations

import streamlit as st

PAGE_MAX_WIDTH_PX = 1100


def apply_consistent_layout(page_title: str = "TADF Ehitus") -> None:
    """Call as the FIRST st.* command in every page script."""
    st.set_page_config(
        page_title=page_title,
        page_icon="🏗️",
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
</style>
""",
        unsafe_allow_html=True,
    )
