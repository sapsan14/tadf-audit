"""Page «🗂 Справочник» — manage the named entities behind the form
selection boxes (auditors, clients, designers, builders, use purposes).

These entities live in the `directory_*` tables. Every time an auditor
saves an audit, the names + sibling fields are upserted into the
directory automatically — so this page is *not* required to make a new
name appear in the dropdown next time. Its purpose is twofold:

  1. **Visibility**: see what the dropdown will offer before opening
     the audit form (handy after merging from another auditor's data).
  2. **Cleanup**: delete stale / typo'd entries so they stop surfacing
     as suggestions.

Editing a field here is intentionally NOT supported — the canonical place
to edit an auditor / client is the audit form itself, where context (which
audit, which side) is clear. Saving the audit re-upserts and overrides
the directory entry. This page is purely view + delete.
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
)
from tadf.db.session import session_scope  # noqa: E402


def _delete_in_session(fn, key: str) -> None:
    """Open a fresh session scope, call `fn(s, key)`, commit. The list+delete
    pattern needs separate sessions because the streamlit click happens on a
    later rerun than the list query — the original session is long gone."""
    with session_scope() as s:
        fn(s, key)


def _render_entry(
    *,
    row_key: str,
    label: str,
    body: str | None,
    on_delete: Callable[[], None],
) -> None:
    """Render one directory row.

    Two states share the same outer container so the row keeps its place
    in the list when the user toggles between them:

      - **Idle**: name + body caption on the left, 🗑 button on the right.
      - **Pending delete**: full-width warning + «Да / Отмена» buttons,
        each `use_container_width=True` so they stretch — no more cramped
        text squeezing into a 1/11-width column (that was the bug in the
        previous revision: the confirm UI was rendered INSIDE the narrow
        right cell of an outer `columns([10, 1])`).

    `row_key` must be unique per entry across the whole page (we suffix
    with the SQL `id`). `on_delete` is the no-arg callback that hits the
    DB; it's invoked synchronously, before `st.rerun()`.
    """
    pending_key = f"_dir_pending_delete_{row_key}"

    with st.container(border=True):
        if st.session_state.get(pending_key):
            st.warning(f"⚠ Удалить из справочника: **{label}**?", icon="🗑️")
            yes_col, no_col = st.columns(2)
            if yes_col.button(
                "✓ Да, удалить",
                key=f"{row_key}_confirm",
                type="primary",
                use_container_width=True,
            ):
                on_delete()
                st.session_state.pop(pending_key, None)
                st.toast(f"Удалено: {label}", icon="🗑️")
                st.rerun()
            if no_col.button(
                "✕ Отмена",
                key=f"{row_key}_cancel",
                use_container_width=True,
            ):
                st.session_state.pop(pending_key, None)
                st.rerun()
            return

        text_col, btn_col = st.columns([10, 1])
        with text_col:
            st.markdown(f"**{label}**")
            if body:
                st.caption(body)
        with btn_col:
            if st.button(
                "🗑",
                key=row_key,
                help=f"Удалить «{label}» из справочника",
                use_container_width=True,
            ):
                st.session_state[pending_key] = True
                st.rerun()


st.title("🗂 Справочник — auditors, clients, designers, builders, use purposes")

st.markdown(
    """
Здесь видны все имена / значения, которые попадают в выпадающие списки
формы аудита. Они автоматически сохраняются и обновляются каждый раз,
когда вы сохраняете аудит на странице «📝 Новый аудит» или «🏠 Здание».

**Удалить** запись — она перестанет показываться как подсказка (но
из самих аудитов, где она использовалась, никуда не денется — это просто
чистка списка предложений).

Чтобы **отредактировать** запись, откройте аудит, в котором она
использовалась, измените поля и сохраните — справочник обновится
автоматически.
"""
)

# ---------------------------------------------------------------------------
# Auditors
# ---------------------------------------------------------------------------

st.header("Аудиторы (Auditi koostas / Auditi kontrollis)")

with session_scope() as s:
    auditors = list_directory_auditors(s)

if not auditors:
    st.caption(":grey[Пусто. Создайте аудит и сохраните — имена появятся здесь.]")
else:
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
        _render_entry(
            row_key=f"del_auditor_{a.id}",
            label=a.full_name,
            body=" · ".join(bits) if bits else None,
            on_delete=lambda name=a.full_name: _delete_in_session(
                delete_directory_auditor, name
            ),
        )

# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

st.header("Заказчики (Tellija)")

with session_scope() as s:
    clients = list_directory_clients(s)

if not clients:
    st.caption(":grey[Пусто.]")
else:
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
        _render_entry(
            row_key=f"del_client_{c.id}",
            label=c.name,
            body=" · ".join(bits) if bits else None,
            on_delete=lambda name=c.name: _delete_in_session(
                delete_directory_client, name
            ),
        )

# ---------------------------------------------------------------------------
# Designers
# ---------------------------------------------------------------------------

st.header("Проектировщики (Projekteerija)")

with session_scope() as s:
    designers = list_directory_designers(s)

if not designers:
    st.caption(":grey[Пусто.]")
else:
    for d in designers:
        body = f"reg. kood {d.reg_code}" if d.reg_code else None
        _render_entry(
            row_key=f"del_designer_{d.id}",
            label=d.name,
            body=body,
            on_delete=lambda name=d.name: _delete_in_session(
                delete_directory_designer, name
            ),
        )

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

st.header("Строители (Ehitaja)")

with session_scope() as s:
    builders = list_directory_builders(s)

if not builders:
    st.caption(":grey[Пусто.]")
else:
    for b in builders:
        body = f"reg. kood {b.reg_code}" if b.reg_code else None
        _render_entry(
            row_key=f"del_builder_{b.id}",
            label=b.name,
            body=body,
            on_delete=lambda name=b.name: _delete_in_session(
                delete_directory_builder, name
            ),
        )

# ---------------------------------------------------------------------------
# Use purposes
# ---------------------------------------------------------------------------

st.header("Назначения зданий (Kasutusotstarve)")

with session_scope() as s:
    use_purposes = list_directory_use_purposes(s)

if not use_purposes:
    st.caption(":grey[Пусто.]")
else:
    for u in use_purposes:
        _render_entry(
            row_key=f"del_use_purpose_{u.id}",
            label=u.value,
            body=None,
            on_delete=lambda val=u.value: _delete_in_session(
                delete_directory_use_purpose, val
            ),
        )
