"""Form-widget helpers shared across pages.

`combobox` is a thin wrapper around `st.selectbox(accept_new_options=True)`
(Streamlit ≥ 1.50) that:
  - shows previously-entered DB values as suggestions
  - lets the user type a brand-new value
  - returns the chosen string (None for empty)

`improve_button_for` renders a single «✨ Улучшить» button under any free-form
text field. Behind that button, `tadf.llm.improve.improve_text` auto-picks
between Estonian polish, RU→ET translation, or bullet→prose drafting and
shows a Was/Now diff with accept/reject — same UX as the existing polish
flow on the Findings page.

If the running Streamlit version doesn't support `accept_new_options`, falls
back to a plain `text_input` so the form still works.
"""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from tadf.llm import improve_text, is_available, is_locked


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


_PENDING_PREFIX = "_imp_pending_widget_"


def flush_improve_pending() -> None:
    """Apply queued widget updates from improve_button_for accept handlers.

    Must be called at the TOP of any page that uses `improve_button_for`,
    before any widgets render. Streamlit forbids writing
    `st.session_state[widget_key]` after the widget for that key has been
    instantiated in the same script run, so deferred updates are queued
    under `_imp_pending_widget_<key>` and applied here on the next rerun.
    """
    pending = [k for k in list(st.session_state.keys()) if k.startswith(_PENDING_PREFIX)]
    for pkey in pending:
        widget_key = pkey[len(_PENDING_PREFIX):]
        st.session_state[widget_key] = st.session_state.pop(pkey)


def improve_button_for(
    *,
    text: str,
    state_key_prefix: str,
    apply: Callable[[str], None],
    section_ref: str | None = None,
    text_widget_key: str | None = None,
    label: str = "✨ Улучшить",
) -> None:
    """One-click LLM helper: polish / RU→ET translate / bullets→prose.

    Behaviour:
      - If LLM is unavailable (no API key) → nothing renders. Auditor sees
        the page exactly as before.
      - If `section_ref` is locked (11/14) → button disabled with auditor-only
        tooltip — matches the existing rule in polish_text/draft_narrative.
      - If `text` is empty → button disabled with hint to type something.
      - Otherwise: click runs `improve_text`, stores result in session state,
        a Was/Now panel appears below with ✅ Принять / ❌ Отклонить.

    `apply` is a callback receiving the improved string — typically
    `lambda v: setattr(audit, "purpose", v)` or `setattr(f, "recommendation", v)`.
    `text_widget_key`, if given, is `st.session_state.pop`'d on accept so the
    underlying text_area/text_input re-seeds from the new model value
    (Streamlit forbids writing a widget's session_state key after render).
    """
    if not is_available():
        return

    result_key = f"_{state_key_prefix}_result"
    error_key = f"_{state_key_prefix}_error"

    locked = bool(section_ref) and is_locked(section_ref)
    is_empty = not text.strip()

    if locked:
        help_text = "Разделы 11 и 14 — только аудитор, без ИИ."
    elif is_empty:
        help_text = "Сначала введите текст в поле выше."
    else:
        help_text = (
            "ИИ сам выберет действие: правка эстонской грамматики, "
            "перевод RU→ET или раскрытие тезисов в параграф. "
            "Результат покажется как diff — Вы сами решаете, принимать ли."
        )

    clicked = st.button(
        label,
        key=f"{state_key_prefix}_btn",
        disabled=locked or is_empty,
        help=help_text,
    )

    if clicked:
        with st.status("Claude обрабатывает…", expanded=False) as status:
            try:
                result = improve_text(text, section_ref=section_ref)
                st.session_state[result_key] = result
                st.session_state.pop(error_key, None)
                status.update(label=f"Готово ✅ ({result.label_ru})", state="complete")
            except Exception as e:  # noqa: BLE001
                st.session_state[error_key] = f"{type(e).__name__}: {e}"
                status.update(label="Ошибка ❌", state="error", expanded=True)
        st.rerun()

    if error_key in st.session_state:
        st.error(st.session_state[error_key])

    if result_key in st.session_state:
        result = st.session_state[result_key]
        if result.improved.strip() == result.original.strip():
            st.info("✅ ИИ: правок не требуется — текст уже чистый.")
            if st.button("OK", key=f"{state_key_prefix}_ok"):
                del st.session_state[result_key]
                st.rerun()
        else:
            st.markdown(f"**Предложение ИИ — {result.label_ru}:**")
            cwas, cnow = st.columns(2)
            with cwas:
                st.caption("Было:")
                st.markdown(f"> {result.original}")
            with cnow:
                st.caption("Стало:")
                st.markdown(f"> {result.improved}")
            ca, cr = st.columns(2)
            if ca.button("✅ Принять", key=f"{state_key_prefix}_accept", type="primary"):
                apply(result.improved)
                if text_widget_key:
                    # Defer to next run via flush_improve_pending() at page top —
                    # we can't write to a widget's session_state after it rendered.
                    st.session_state[f"{_PENDING_PREFIX}{text_widget_key}"] = result.improved
                del st.session_state[result_key]
                st.rerun()
            if cr.button("❌ Отклонить", key=f"{state_key_prefix}_reject"):
                del st.session_state[result_key]
                st.rerun()
