"""Page «🗂 Справочник» — manage the named entities behind the form
selection boxes (auditors, clients, designers, builders, use purposes).

These entities live in the `directory_*` tables. Every audit save mirrors
the names + sibling fields into the directory automatically (see
`tadf.db.repo._mirror_to_directory`), so this page is *not* required to
make a new name appear in the dropdown next time. Its purpose is threefold:

  1. **Visibility**: see what the dropdown will offer before opening
     the audit form.
  2. **Edit**: fix typos / update outdated info without having to find
     the audit that created the entry. Saving the audit form would also
     work, but only if you remember which audit it came from.
  3. **Cleanup**: delete stale entries so they stop surfacing as
     suggestions.

Each row has three UI states that share the same `st.container(border=True)`:
idle (label + ✏️ + 🗑), pending-delete (warning + Yes/Cancel), edit-form
(input fields + Save/Cancel). Toggling a state preserves the row's vertical
slot — no layout jumping when the user opens an edit form.
"""

from __future__ import annotations

import pathlib
import sys
from collections.abc import Callable

_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))

import streamlit as st  # noqa: E402

from tadf.db.repo import (  # noqa: E402
    delete_directory_auditor,
    delete_directory_builder,
    delete_directory_client,
    delete_directory_designer,
    delete_directory_use_purpose,
    list_directory_auditors,
    list_directory_builders,
    list_directory_clients,
    list_directory_designers,
    list_directory_use_purposes,
    update_directory_auditor,
    update_directory_builder,
    update_directory_client,
    update_directory_designer,
    update_directory_use_purpose,
)
from tadf.db.session import session_scope  # noqa: E402


def _delete_in_session(fn, key: str) -> None:
    """Delete via a fresh session scope (the original list query's session
    is long gone by the time the user clicks the button on a later rerun)."""
    with session_scope() as s:
        fn(s, key)


def _update_in_session(fn, **kwargs) -> None:
    with session_scope() as s:
        fn(s, **kwargs)


# ---------------------------------------------------------------------------
# Edit forms — one per directory kind. Each renders the input fields,
# returns a tuple `(saved: bool, save_kwargs: dict | None)` so the caller
# can pass the kwargs into the matching `update_directory_*` repo function.
# ---------------------------------------------------------------------------


def _edit_form_auditor(row, key_prefix: str) -> tuple[bool, dict | None, bool]:
    """Returns `(save_clicked, save_kwargs, cancel_clicked)`."""
    name = st.text_input("Имя", value=row.full_name, key=f"{key_prefix}_name")
    c1, c2 = st.columns(2)
    with c1:
        kut = st.text_input(
            "Kutsetunnistus №",
            value=row.kutsetunnistus_no or "",
            key=f"{key_prefix}_kut",
        )
        company = st.text_input(
            "Компания", value=row.company or "", key=f"{key_prefix}_company"
        )
    with c2:
        qual = st.text_input(
            "Квалификация",
            value=row.qualification or "",
            key=f"{key_prefix}_qual",
        )
        reg_nr = st.text_input(
            "Reg. nr",
            value=row.company_reg_nr or "",
            key=f"{key_prefix}_reg",
        )
    save_col, cancel_col = st.columns(2)
    save = save_col.button(
        "Сохранить",
        key=f"{key_prefix}_save",
        type="primary",
        icon=":material/save:",
        use_container_width=True,
    )
    cancel = cancel_col.button(
        "Отмена",
        key=f"{key_prefix}_cancel_edit",
        icon=":material/close:",
        use_container_width=True,
    )
    if save:
        return True, {
            "row_id": row.id,
            "full_name": name,
            "kutsetunnistus_no": kut or None,
            "qualification": qual or None,
            "company": company or None,
            "company_reg_nr": reg_nr or None,
        }, False
    return False, None, cancel


def _edit_form_client(row, key_prefix: str) -> tuple[bool, dict | None, bool]:
    name = st.text_input("Название / имя", value=row.name, key=f"{key_prefix}_name")
    c1, c2 = st.columns(2)
    with c1:
        reg = st.text_input(
            "Reg. kood", value=row.reg_code or "", key=f"{key_prefix}_reg"
        )
        email = st.text_input(
            "E-mail",
            value=row.contact_email or "",
            key=f"{key_prefix}_email",
        )
    with c2:
        phone = st.text_input(
            "Телефон",
            value=row.contact_phone or "",
            key=f"{key_prefix}_phone",
        )
    address = st.text_input(
        "Адрес", value=row.address or "", key=f"{key_prefix}_addr"
    )
    save_col, cancel_col = st.columns(2)
    save = save_col.button(
        "Сохранить",
        key=f"{key_prefix}_save",
        type="primary",
        icon=":material/save:",
        use_container_width=True,
    )
    cancel = cancel_col.button(
        "Отмена",
        key=f"{key_prefix}_cancel_edit",
        icon=":material/close:",
        use_container_width=True,
    )
    if save:
        return True, {
            "row_id": row.id,
            "name": name,
            "reg_code": reg or None,
            "contact_email": email or None,
            "contact_phone": phone or None,
            "address": address or None,
        }, False
    return False, None, cancel


def _edit_form_named_with_reg(row, key_prefix: str) -> tuple[bool, dict | None, bool]:
    """Shared form for designer / builder (name + optional reg_code)."""
    name = st.text_input("Название", value=row.name, key=f"{key_prefix}_name")
    reg = st.text_input(
        "Reg. kood (если известен)",
        value=row.reg_code or "",
        key=f"{key_prefix}_reg",
    )
    save_col, cancel_col = st.columns(2)
    save = save_col.button(
        "Сохранить",
        key=f"{key_prefix}_save",
        type="primary",
        icon=":material/save:",
        use_container_width=True,
    )
    cancel = cancel_col.button(
        "Отмена",
        key=f"{key_prefix}_cancel_edit",
        icon=":material/close:",
        use_container_width=True,
    )
    if save:
        return True, {"row_id": row.id, "name": name, "reg_code": reg or None}, False
    return False, None, cancel


def _edit_form_use_purpose(row, key_prefix: str) -> tuple[bool, dict | None, bool]:
    value = st.text_input("Значение", value=row.value, key=f"{key_prefix}_val")
    save_col, cancel_col = st.columns(2)
    save = save_col.button(
        "Сохранить",
        key=f"{key_prefix}_save",
        type="primary",
        icon=":material/save:",
        use_container_width=True,
    )
    cancel = cancel_col.button(
        "Отмена",
        key=f"{key_prefix}_cancel_edit",
        icon=":material/close:",
        use_container_width=True,
    )
    if save:
        return True, {"row_id": row.id, "value": value}, False
    return False, None, cancel


# ---------------------------------------------------------------------------
# Generic row renderer with three states (idle / edit / pending-delete).
# ---------------------------------------------------------------------------


def _render_row(
    *,
    row,
    label: str,
    body: str | None,
    delete_key: str,
    edit_form: Callable[[object, str], tuple[bool, dict | None, bool]],
    update_fn: Callable,
    delete_fn: Callable[[object, str], bool],
) -> None:
    edit_state_key = f"_dir_edit_{delete_key}"
    delete_state_key = f"_dir_pending_delete_{delete_key}"
    error_state_key = f"_dir_edit_error_{delete_key}"

    with st.container(border=True):
        # ---------- Pending delete ----------
        if st.session_state.get(delete_state_key):
            st.warning(f"Удалить из справочника: **{label}**?", icon="⚠️")
            yes_col, no_col = st.columns(2)
            if yes_col.button(
                "Да, удалить",
                key=f"{delete_key}_confirm",
                type="primary",
                icon=":material/delete:",
                use_container_width=True,
            ):
                _delete_in_session(delete_fn, label)
                st.session_state.pop(delete_state_key, None)
                st.toast(f"Удалено: {label}", icon="🗑️")
                st.rerun()
            if no_col.button(
                "Отмена",
                key=f"{delete_key}_cancel",
                icon=":material/close:",
                use_container_width=True,
            ):
                st.session_state.pop(delete_state_key, None)
                st.rerun()
            return

        # ---------- Edit ----------
        if st.session_state.get(edit_state_key):
            saved, kwargs, cancelled = edit_form(row, f"{delete_key}_form")
            if cancelled:
                st.session_state.pop(edit_state_key, None)
                st.session_state.pop(error_state_key, None)
                st.rerun()
            if saved:
                try:
                    _update_in_session(update_fn, **kwargs)
                except ValueError as e:
                    st.session_state[error_state_key] = str(e)
                    st.rerun()
                else:
                    st.session_state.pop(edit_state_key, None)
                    st.session_state.pop(error_state_key, None)
                    st.toast(f"Сохранено: {label}", icon="💾")
                    st.rerun()
            if msg := st.session_state.get(error_state_key):
                st.error(msg)
            return

        # ---------- Idle ----------
        text_col, edit_col, del_col = st.columns([12, 1, 1])
        with text_col:
            st.markdown(f"**{label}**")
            if body:
                st.caption(body)
        with edit_col:
            if st.button(
                "",
                key=f"{delete_key}_edit",
                help=f"Редактировать «{label}»",
                icon=":material/edit:",
                use_container_width=True,
            ):
                st.session_state[edit_state_key] = True
                st.rerun()
        with del_col:
            if st.button(
                "",
                key=delete_key,
                help=f"Удалить «{label}» из справочника",
                icon=":material/delete_outline:",
                use_container_width=True,
            ):
                st.session_state[delete_state_key] = True
                st.rerun()


# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------

st.title("🗂 Справочник")
st.caption(
    "Имена и значения, которые попадают в выпадающие списки формы аудита. "
    "Запись добавляется автоматически при сохранении аудита; здесь её можно "
    "отредактировать или удалить — изменения сразу попадают во все следующие "
    "подсказки. На уже сохранённые аудиты это не влияет."
)

# ---------------------------------------------------------------------------
# Single round-trip: read all categories at once.
# ---------------------------------------------------------------------------

with session_scope() as s:
    auditors = list_directory_auditors(s)
    clients = list_directory_clients(s)
    designers = list_directory_designers(s)
    builders = list_directory_builders(s)
    use_purposes = list_directory_use_purposes(s)
    for row in (*auditors, *clients, *designers, *builders, *use_purposes):
        s.expunge(row)

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("👤 Аудиторы", len(auditors))
m2.metric("🏢 Заказчики", len(clients))
m3.metric("📐 Проектировщики", len(designers))
m4.metric("🏗 Строители", len(builders))
m5.metric("🏷 Назначения", len(use_purposes))

st.divider()


def _empty(text: str = "Пусто.") -> None:
    st.caption(f":grey[{text}]")


# ---------------------------------------------------------------------------
# Auditors
# ---------------------------------------------------------------------------

st.subheader("👤 Аудиторы")
if not auditors:
    _empty("Создайте аудит и сохраните — имена появятся здесь.")
for a in auditors:
    bits: list[str] = []
    if a.kutsetunnistus_no:
        bits.append(f"kutsetunnistus {a.kutsetunnistus_no}")
    if a.qualification:
        bits.append(a.qualification)
    if a.company:
        company_bit = a.company
        if a.company_reg_nr:
            company_bit = f"{company_bit} (reg. {a.company_reg_nr})"
        bits.append(company_bit)
    _render_row(
        row=a,
        label=a.full_name,
        body=" · ".join(bits) if bits else None,
        delete_key=f"auditor_{a.id}",
        edit_form=_edit_form_auditor,
        update_fn=update_directory_auditor,
        delete_fn=delete_directory_auditor,
    )

# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

st.subheader("🏢 Заказчики")
if not clients:
    _empty()
for c in clients:
    bits = []
    if c.reg_code:
        bits.append(f"reg. kood {c.reg_code}")
    if c.address:
        bits.append(c.address)
    if c.contact_email:
        bits.append(c.contact_email)
    if c.contact_phone:
        bits.append(c.contact_phone)
    _render_row(
        row=c,
        label=c.name,
        body=" · ".join(bits) if bits else None,
        delete_key=f"client_{c.id}",
        edit_form=_edit_form_client,
        update_fn=update_directory_client,
        delete_fn=delete_directory_client,
    )

# ---------------------------------------------------------------------------
# Designers
# ---------------------------------------------------------------------------

st.subheader("📐 Проектировщики")
if not designers:
    _empty()
for d in designers:
    _render_row(
        row=d,
        label=d.name,
        body=f"reg. kood {d.reg_code}" if d.reg_code else None,
        delete_key=f"designer_{d.id}",
        edit_form=_edit_form_named_with_reg,
        update_fn=update_directory_designer,
        delete_fn=delete_directory_designer,
    )

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

st.subheader("🏗 Строители")
if not builders:
    _empty()
for b in builders:
    _render_row(
        row=b,
        label=b.name,
        body=f"reg. kood {b.reg_code}" if b.reg_code else None,
        delete_key=f"builder_{b.id}",
        edit_form=_edit_form_named_with_reg,
        update_fn=update_directory_builder,
        delete_fn=delete_directory_builder,
    )

# ---------------------------------------------------------------------------
# Use purposes
# ---------------------------------------------------------------------------

st.subheader("🏷 Назначения зданий")
if not use_purposes:
    _empty()
for u in use_purposes:
    _render_row(
        row=u,
        label=u.value,
        body=None,
        delete_key=f"use_purpose_{u.id}",
        edit_form=_edit_form_use_purpose,
        update_fn=update_directory_use_purpose,
        delete_fn=delete_directory_use_purpose,
    )
