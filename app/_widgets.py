"""Form-widget helpers shared across pages.

`combobox` is a thin wrapper around `st.selectbox(accept_new_options=True)`
(Streamlit ≥ 1.50) that:
  - shows previously-entered DB values as suggestions
  - lets the user type a brand-new value
  - returns the chosen string (None for empty)

If the running Streamlit version doesn't support `accept_new_options`, falls
back to a plain `text_input` so the form still works.
"""

from __future__ import annotations

import streamlit as st


def combobox(
    label: str,
    *,
    suggestions: list[str],
    value: str | None,
    key: str,
    help: str | None = None,
    placeholder: str | None = None,
) -> str | None:
    """Combo-box: pick from `suggestions` OR type a new value."""
    options = sorted({*suggestions, value} - {None, ""})
    initial = value if value in options else (value or None)

    try:
        result = st.selectbox(
            label,
            options=options,
            index=options.index(initial) if initial in options else None,
            key=key,
            help=help,
            placeholder=placeholder or "Введите или выберите из существующих…",
            accept_new_options=True,
        )
    except TypeError:
        # Older Streamlit without accept_new_options — degrade to text_input.
        result = st.text_input(label, value=value or "", key=key, help=help) or None

    if isinstance(result, str):
        return result.strip() or None
    return result
