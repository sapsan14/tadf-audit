"""Shared session-state helpers for Streamlit pages."""

from __future__ import annotations

from datetime import date

import streamlit as st

from tadf.db.repo import delete_audit, list_audits, list_drafts, load_audit
from tadf.db.session import session_scope
from tadf.models import Audit, Auditor, Building, Client


def _new_audit() -> Audit:
    return Audit(
        seq_no=1,
        year=date.today().year,
        type="EA",
        subtype="kasutuseelne",
        visit_date=date.today(),
        composer=Auditor(full_name=""),
        reviewer=Auditor(full_name="Fjodor Sokolov", kutsetunnistus_no="148515"),
        building=Building(address=""),
        client=Client(name=""),
    )


def get_current() -> Audit:
    if "audit" not in st.session_state:
        st.session_state["audit"] = _new_audit()
    return st.session_state["audit"]


def set_current(audit: Audit) -> None:
    st.session_state["audit"] = audit


def reload_from_db(audit_id: int) -> None:
    with session_scope() as s:
        st.session_state["audit"] = load_audit(s, audit_id)
        st.session_state["loaded_id"] = audit_id


def all_saved_audits() -> list[Audit]:
    with session_scope() as s:
        return list_audits(s)


def all_saved_drafts() -> list[Audit]:
    """Drafts only (status='draft'), newest-first by updated_at."""
    with session_scope() as s:
        return list_drafts(s)


def start_new_draft() -> None:
    """Reset session state to a brand-new in-memory audit."""
    st.session_state["audit"] = _new_audit()
    st.session_state.pop("loaded_id", None)


def delete_audit_by_id(audit_id: int) -> None:
    """Delete the audit row + its findings/photos via cascade."""
    with session_scope() as s:
        delete_audit(s, audit_id)
