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

from tadf.external.ariregister_client import CompanyHit, search_company
from tadf.external.inaadress_client import AddressHit, search_address
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


def address_picker(
    *,
    key_prefix: str,
    on_select: Callable[[AddressHit], None],
    label: str = "🔎 Поиск адреса в Maa-amet (in-ADS)",
    placeholder: str = "Например: Auga 8 Narva-Jõesuu или Tartu mnt 84a",
    help_text: str | None = (
        "Печатаете часть адреса (минимум 2 символа) и жмёте «Искать». "
        "in-ADS — официальный адресный регистр Эстонии (Maa-amet), "
        "результаты — нормализованный адрес + кадастровый номер. "
        "Кэш на 30 дней — повторные поиски работают офлайн."
    ),
) -> None:
    """Render an in-ADS address search row + results list.

    The caller passes `on_select` which is invoked with the chosen
    `AddressHit`. Typical use: queue field updates into the page's
    `_PENDING_KEY` slot and call `st.rerun()` from inside the callback.

    State lives under `st.session_state[f"_addr_search_{key_prefix}"]`
    so two pickers on the same page never collide. Search results are
    held in session state until the user clicks an item or clears the
    query — Streamlit reruns don't drop them.
    """
    state_key = f"_addr_search_{key_prefix}"
    query_key = f"_addr_q_{key_prefix}"

    cols = st.columns([5, 1, 1])
    query = cols[0].text_input(
        label,
        value=st.session_state.get(query_key, ""),
        key=query_key,
        placeholder=placeholder,
        help=help_text,
    )
    do_search = cols[1].button(
        "Искать",
        key=f"{state_key}_btn",
        use_container_width=True,
        disabled=len((query or "").strip()) < 2,
    )
    do_clear = cols[2].button(
        "Очистить",
        key=f"{state_key}_clear",
        use_container_width=True,
        disabled=state_key not in st.session_state,
    )

    if do_clear:
        st.session_state.pop(state_key, None)
        st.session_state.pop(query_key, None)
        st.rerun()

    if do_search:
        hits = search_address(query)
        st.session_state[state_key] = [_hit_to_state(h) for h in hits]

    hits_state = st.session_state.get(state_key)
    if not hits_state:
        if hits_state == []:  # explicit empty (search ran, no matches)
            st.caption(":orange[Ничего не найдено. Уточните запрос.]")
        return

    st.caption(f"Найдено {len(hits_state)}. Выберите нужный адрес:")
    for i, h_state in enumerate(hits_state):
        h = _state_to_hit(h_state)
        line = h.address
        if h.kataster:
            line = f"{line} · {h.kataster}"
        if st.button(
            f"📍 {line}",
            key=f"{state_key}_pick_{i}",
            use_container_width=True,
        ):
            on_select(h)


def company_picker(
    *,
    key_prefix: str,
    on_select: Callable[[CompanyHit], None],
    label: str = "🔎 Поиск в Ariregister (e-äriregister)",
    placeholder: str = "Название или 8-значный рег-код (например: TADF Ehitus или 12503172)",
    help_text: str | None = (
        "Печатаете название или рег-код (минимум 2 символа) и жмёте «Искать». "
        "Ariregister — официальный реестр RIK, источник реквизитов компаний. "
        "Кэш на 7 дней — повторные поиски работают офлайн."
    ),
) -> None:
    """Render an Ariregister autocomplete row + results list.

    `on_select(CompanyHit)` is invoked when the auditor picks a hit.
    State lives under unique session keys per `key_prefix` so two
    pickers on the same page never collide.
    """
    state_key = f"_co_search_{key_prefix}"
    query_key = f"_co_q_{key_prefix}"

    cols = st.columns([5, 1, 1])
    query = cols[0].text_input(
        label,
        value=st.session_state.get(query_key, ""),
        key=query_key,
        placeholder=placeholder,
        help=help_text,
    )
    do_search = cols[1].button(
        "Искать",
        key=f"{state_key}_btn",
        use_container_width=True,
        disabled=len((query or "").strip()) < 2,
    )
    do_clear = cols[2].button(
        "Очистить",
        key=f"{state_key}_clear",
        use_container_width=True,
        disabled=state_key not in st.session_state,
    )

    if do_clear:
        st.session_state.pop(state_key, None)
        st.session_state.pop(query_key, None)
        st.rerun()

    if do_search:
        hits = search_company(query)
        st.session_state[state_key] = [_co_to_state(h) for h in hits]

    hits_state = st.session_state.get(state_key)
    if not hits_state:
        if hits_state == []:
            st.caption(":orange[Ничего не найдено в Ariregister.]")
        return

    st.caption(f"Найдено {len(hits_state)}. Выберите компанию:")
    for i, h_state in enumerate(hits_state):
        h = _state_to_company(h_state)
        line = f"{h.name} · {h.reg_code}"
        if h.legal_form:
            line = f"{line} · {h.legal_form}"
        if h.status_label and h.status != "R":
            line = f"{line} · {h.status_label}"
        if h.address:
            line = f"{line}\n📍 {h.address}"
        if st.button(
            line,
            key=f"{state_key}_pick_{i}",
            use_container_width=True,
        ):
            on_select(h)


def _co_to_state(h: CompanyHit) -> dict:
    return {
        "reg_code": h.reg_code,
        "name": h.name,
        "legal_form": h.legal_form,
        "legal_form_code": h.legal_form_code,
        "status": h.status,
        "status_label": h.status_label,
        "address": h.address,
        "zip_code": h.zip_code,
        "url": h.url,
    }


def _state_to_company(d: dict) -> CompanyHit:
    return CompanyHit(
        reg_code=d.get("reg_code") or "",
        name=d.get("name") or "",
        legal_form=d.get("legal_form"),
        legal_form_code=d.get("legal_form_code"),
        status=d.get("status"),
        status_label=d.get("status_label"),
        address=d.get("address"),
        zip_code=d.get("zip_code"),
        url=d.get("url"),
        raw={},
    )


def _hit_to_state(h: AddressHit) -> dict:
    return {
        "address": h.address,
        "short": h.short,
        "ads_id": h.ads_id,
        "kataster": h.kataster,
        "coords": list(h.coords) if h.coords else None,
    }


def _state_to_hit(d: dict) -> AddressHit:
    coords = d.get("coords")
    return AddressHit(
        address=d.get("address") or "",
        short=d.get("short"),
        ads_id=d.get("ads_id"),
        kataster=d.get("kataster"),
        coords=tuple(coords) if isinstance(coords, list) and len(coords) == 2 else None,
        raw={},
    )


def hint_caption(message: str | None) -> None:
    """Render a small orange caption below an input when `message` is not empty.

    Used for inline validation hints (reg-code checksum, isikukood checksum)
    where we don't want to block the form but still surface the typo.
    """
    if message:
        st.caption(f":orange[⚠ {message}]")


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
