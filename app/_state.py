"""Shared session-state helpers for Streamlit pages."""

from __future__ import annotations

import hashlib
from datetime import date

import streamlit as st

from tadf.db.repo import delete_audit, list_audits, list_drafts, load_audit, upsert_audit
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
    # Reset the auto-save dedup hash so the next ensure_draft_saved()
    # re-fingerprints against the just-loaded state, not the previous
    # audit's state.
    st.session_state.pop(_AUTO_SAVE_HASH_KEY, None)


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
    st.session_state.pop(_AUTO_SAVE_HASH_KEY, None)


# Session-state key tracking the last-persisted audit fingerprint, so
# `ensure_draft_saved` can skip a DB write when nothing has changed.
_AUTO_SAVE_HASH_KEY = "_audit_last_saved_hash"


def delete_audit_by_id(audit_id: int) -> None:
    """Delete the audit row + its findings/photos via cascade."""
    with session_scope() as s:
        delete_audit(s, audit_id)


def _audit_has_user_data(audit: Audit) -> bool:
    """True if the auditor has typed something meaningful into the form
    (any non-default field). Used by `ensure_draft_saved` so we only
    promote a fresh in-memory draft to a row in the DB after the user
    actually starts working — not on every page load."""
    b = audit.building
    if (b.address or "").strip():
        return True
    if (b.ehr_code or "").strip():
        return True
    if (b.kataster_no or "").strip():
        return True
    if (audit.purpose or "").strip():
        return True
    if (audit.composer.full_name or "").strip():
        return True
    if audit.client and (audit.client.name or "").strip():
        return True
    if audit.findings:
        return True
    return bool(audit.photos)


def ensure_draft_saved(audit: Audit) -> bool:
    """Auto-save the audit whenever its in-memory state diverges from
    what's in the DB.

    Two cases combined:
      1. **New draft (audit.id is None)**: insert as soon as the user
         has typed something meaningful — so downstream features that
         need `audit.id` (Teatmik token-fragment links, EHR import-API
         endpoints, pending_imports rows, et al) start working without
         a manual «Save draft» click.
      2. **Existing draft (audit.id is set)**: update on every meaningful
         in-memory change so edits aren't lost when the auditor closes
         the tab. Dedup'd via a session-state hash — same state →
         no DB write.

    Returns True if a write was issued, False if no-op (no data yet
    for a brand-new draft, or state matches the last successful save).
    """
    if audit.id is None and not _audit_has_user_data(audit):
        return False

    # Fingerprint everything except `audit.id` itself (which differs
    # before/after the first insert and shouldn't influence dedup).
    current_hash = hashlib.sha256(
        audit.model_dump_json(exclude={"id"}).encode("utf-8")
    ).hexdigest()
    last_hash = st.session_state.get(_AUTO_SAVE_HASH_KEY)
    if last_hash == current_hash and audit.id is not None:
        return False  # nothing changed since the last successful save

    with session_scope() as s:
        new_id = upsert_audit(s, audit)
    audit.id = new_id
    set_current(audit)
    st.session_state[_AUTO_SAVE_HASH_KEY] = current_hash
    return True
