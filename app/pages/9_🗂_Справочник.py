"""Page «🗂 Справочник» — manage the named entities behind the form
selection boxes (auditors, clients, designers, builders, use purposes).

These entities live in the `directory_*` tables. Every time an auditor
saves an audit, the names + sibling fields are upserted into the
directory automatically — so this page is *not* required to make a new
name appear in the dropdown next time. Its purpose is twofold:

  1. **Visibility**: see what the dropdown will offer before opening
     the audit form (handy after merging from another auditor's data).
  2. **Cleanup**: delete stale / typo'd entries so they stop surfacing
     as suggestions. The legacy `_distinct(AuditorRow.full_name)` query
     made cleanup impossible — that's the main thing this directory
     model unlocks.

Editing a field here is intentionally NOT supported — the canonical place
to edit an auditor / client is the audit form itself, where context (which
audit, which side) is clear. Saving the audit re-upserts and overrides
the directory entry. This page is purely view + delete.
"""

from __future__ import annotations

import pathlib
import sys

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
# Helpers
# ---------------------------------------------------------------------------


def _delete_button(*, key: str, label: str, on_click) -> bool:
    """Render a small ❌ button. Returns True if the user clicked it
    AND confirmed via the second-pass confirmation slot below."""
    pending_key = f"_dir_pending_delete_{key}"

    if st.session_state.get(pending_key):
        c1, c2, c3 = st.columns([3, 1, 1])
        c1.caption(f":orange[Подтвердите удаление: {label}]")
        if c2.button("✓ Да", key=f"{key}_confirm", type="primary"):
            on_click()
            st.session_state.pop(pending_key, None)
            st.toast(f"Удалено: {label}", icon="🗑️")
            st.rerun()
            return True
        if c3.button("✕ Нет", key=f"{key}_cancel"):
            st.session_state.pop(pending_key, None)
            st.rerun()
        return False

    if st.button("🗑", key=key, help=f"Удалить «{label}» из справочника"):
        st.session_state[pending_key] = True
        st.rerun()
    return False


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
        with st.container(border=True):
            c1, c2 = st.columns([10, 1])
            with c1:
                st.markdown(f"**{a.full_name}**")
                bits = []
                if a.kutsetunnistus_no:
                    bits.append(f"kutsetunnistus {a.kutsetunnistus_no}")
                if a.qualification:
                    bits.append(a.qualification)
                if a.company:
                    company_bit = a.company
                    if a.company_reg_nr:
                        company_bit = f"{company_bit} (reg. {a.company_reg_nr})"
                    bits.append(company_bit)
                if bits:
                    st.caption(" · ".join(bits))
            with c2:
                if _delete_button(
                    key=f"del_auditor_{a.id}",
                    label=a.full_name,
                    on_click=lambda name=a.full_name: _delete_in_session(
                        delete_directory_auditor, name
                    ),
                ):
                    pass

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
        with st.container(border=True):
            c1, c2 = st.columns([10, 1])
            with c1:
                st.markdown(f"**{c.name}**")
                bits = []
                if c.reg_code:
                    bits.append(f"reg. kood {c.reg_code}")
                if c.address:
                    bits.append(c.address)
                if c.contact_email:
                    bits.append(c.contact_email)
                if c.contact_phone:
                    bits.append(c.contact_phone)
                if bits:
                    st.caption(" · ".join(bits))
            with c2:
                _delete_button(
                    key=f"del_client_{c.id}",
                    label=c.name,
                    on_click=lambda name=c.name: _delete_in_session(
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
        c1, c2 = st.columns([10, 1])
        c1.markdown(f"- {d.name}")
        with c2:
            _delete_button(
                key=f"del_designer_{d.id}",
                label=d.name,
                on_click=lambda name=d.name: _delete_in_session(
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
        c1, c2 = st.columns([10, 1])
        c1.markdown(f"- {b.name}")
        with c2:
            _delete_button(
                key=f"del_builder_{b.id}",
                label=b.name,
                on_click=lambda name=b.name: _delete_in_session(
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
        c1, c2 = st.columns([10, 1])
        c1.markdown(f"- {u.value}")
        with c2:
            _delete_button(
                key=f"del_use_purpose_{u.id}",
                label=u.value,
                on_click=lambda val=u.value: _delete_in_session(
                    delete_directory_use_purpose, val
                ),
            )
