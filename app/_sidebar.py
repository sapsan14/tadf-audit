"""Sidebar widgets shared across all pages — usage tracker etc.

Called from `app/main.py` (the navigation entry) so the sidebar block
renders identically on every page in the app.
"""

from __future__ import annotations

import streamlit as st

from tadf.llm import is_available as _llm_available
from tadf.llm.usage import summarise as _llm_summary


def _fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def render_usage_block() -> None:
    """Compact Claude API usage tracker — drop into st.sidebar."""
    if not _llm_available():
        st.caption("🤖 ИИ выключен — нет ключа Anthropic.")
        return

    s = _llm_summary()
    st.markdown("**🤖 Расход Claude API**")
    if s.calls == 0:
        st.caption("Пока ни одного вызова — расход $0.00")
    else:
        cost_eur = s.cost_usd * 0.92  # rough EUR/USD
        cache_part = (
            f"  ·  кеш ↑{_fmt(s.cache_write_tokens)} ↓{_fmt(s.cache_read_tokens)}"
            if s.cache_read_tokens or s.cache_write_tokens
            else ""
        )
        st.markdown(
            f"≈ **\\${s.cost_usd:.4f}** / €{cost_eur:.4f}  ·  {s.calls} вызов(ов)  \n"
            f"<small>↑ {_fmt(s.input_tokens)} вход · ↓ {_fmt(s.output_tokens)} выход"
            f"{cache_part}</small>",
            unsafe_allow_html=True,
        )
        with st.expander("По моделям", expanded=False):
            for model, m in s.by_model.items():
                st.markdown(
                    f"**{model}** · {int(m['calls'])} вызов(ов) · \\${m['cost']:.4f}  \n"
                    f"<small>↑ {_fmt(int(m['input']))} ↓ {_fmt(int(m['output']))}</small>",
                    unsafe_allow_html=True,
                )
    st.caption(
        "Цены оценочные (Sonnet \\$3/\\$15, Haiku \\$1/\\$5 за 1M токенов; "
        "кеш ×0.1/×1.25)."
    )
