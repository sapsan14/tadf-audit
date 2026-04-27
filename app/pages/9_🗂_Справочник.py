"""Page «🗂 Справочник» — manage the named entities behind the form
selection boxes (auditors, clients, designers, builders, use purposes).

These entities live in the `directory_*` tables. Every audit save mirrors
the names + sibling fields into the directory automatically (see
`tadf.db.repo._mirror_to_directory`), so this page is *not* required to
make a new name appear in the dropdown next time. Its purpose is twofold:

  1. **Visibility**: see what the dropdown will offer before opening
     the audit form.
  2. **Cleanup**: delete stale / typo'd entries so they stop surfacing
     as suggestions.

Editing a field here is intentionally NOT supported — the canonical place
to edit an auditor / client is the audit form itself, where context (which
audit, which side) is clear. Saving the audit re-upserts and overrides
the directory entry.
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

      - **Idle**: name + body caption on the left, delete icon-only button
        on the right.
      - **Pending delete**: full-width warning + «Да / Отмена» buttons,
        each `use_container_width=True` so they stretch — no nested-narrow
        column squeezing.
    """
    pending_key = f"_dir_pending_delete_{row_key}"

    with st.container(border=True):
        if st.session_state.get(pending_key):
            st.warning(f"Удалить из справочника: **{label}**?", icon="⚠️")
            yes_col, no_col = st.columns(2)
            if yes_col.button(
                "Да, удалить",
                key=f"{row_key}_confirm",
                type="primary",
                icon=":material/delete:",
                use_container_width=True,
            ):
                on_delete()
                st.session_state.pop(pending_key, None)
                st.toast(f"Удалено: {label}", icon="🗑️")
                st.rerun()
            if no_col.button(
                "Отмена",
                key=f"{row_key}_cancel",
                icon=":material/close:",
                use_container_width=True,
            ):
                st.session_state.pop(pending_key, None)
                st.rerun()
            return

        text_col, btn_col = st.columns([12, 1])
        with text_col:
            st.markdown(f"**{label}**")
            if body:
                st.caption(body)
        with btn_col:
            if st.button(
                "",
                key=row_key,
                help=f"Удалить «{label}» из справочника",
                icon=":material/delete_outline:",
                use_container_width=True,
            ):
                st.session_state[pending_key] = True
                st.rerun()


# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------

st.title("🗂 Справочник")
st.caption(
    "Имена и значения, которые попадают в выпадающие списки формы аудита. "
    "Запись добавляется и обновляется автоматически при сохранении аудита. "
    "Удаление здесь убирает запись из подсказок (но не из самих аудитов, "
    "где она использовалась)."
)

# ---------------------------------------------------------------------------
# Single round-trip: read counts + lists at once.
# ---------------------------------------------------------------------------

with session_scope() as s:
    auditors = list_directory_auditors(s)
    clients = list_directory_clients(s)
    designers = list_directory_designers(s)
    builders = list_directory_builders(s)
    use_purposes = list_directory_use_purposes(s)

    # Detach so the views below survive after the session closes.
    for row in (*auditors, *clients, *designers, *builders, *use_purposes):
        s.expunge(row)

# ---------------------------------------------------------------------------
# Counts
# ---------------------------------------------------------------------------

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

st.subheader("📐 Проектировщики")
if not designers:
    _empty()
for d in designers:
    _render_entry(
        row_key=f"del_designer_{d.id}",
        label=d.name,
        body=f"reg. kood {d.reg_code}" if d.reg_code else None,
        on_delete=lambda name=d.name: _delete_in_session(
            delete_directory_designer, name
        ),
    )

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

st.subheader("🏗 Строители")
if not builders:
    _empty()
for b in builders:
    _render_entry(
        row_key=f"del_builder_{b.id}",
        label=b.name,
        body=f"reg. kood {b.reg_code}" if b.reg_code else None,
        on_delete=lambda name=b.name: _delete_in_session(
            delete_directory_builder, name
        ),
    )

# ---------------------------------------------------------------------------
# Use purposes
# ---------------------------------------------------------------------------

st.subheader("🏷 Назначения зданий")
if not use_purposes:
    _empty()
for u in use_purposes:
    _render_entry(
        row_key=f"del_use_purpose_{u.id}",
        label=u.value,
        body=None,
        on_delete=lambda val=u.value: _delete_in_session(
            delete_directory_use_purpose, val
        ),
    )
