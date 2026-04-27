"""Shared session-state helpers for Streamlit pages."""

from __future__ import annotations

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


def clone_as_new_draft(audit_id: int) -> None:
    """Load an existing audit and use it as a template for a new draft.

    Carries forward the parts that repeat across audits in the same area
    (auditor block, audit type/subtype, methodology version) and resets
    everything that's per-building (address/EHR/kataster, findings, photos,
    visit date). The client is also reset since the next audit usually has
    a different owner.
    """
    with session_scope() as s:
        src = load_audit(s, audit_id)
    src.id = None
    src.created_at = None
    src.updated_at = None
    src.status = "draft"
    src.findings = []
    src.photos = []
    src.visit_date = date.today()
    # Building: reuse use_purpose / fire_class style metadata defaults but
    # null out anything that uniquely identifies the previous object.
    b = src.building
    b.id = None
    b.address = ""
    b.ehr_code = None
    b.kataster_no = None
    b.designer = None
    b.builder = None
    b.construction_year = None
    b.last_renovation_year = None
    b.footprint_m2 = None
    b.height_m = None
    b.volume_m3 = None
    b.site_area_m2 = None
    b.substitute_docs_note = None
    # Client: a different audit usually means a different owner.
    src.client = Client(name="")
    # Increment seq_no within the current year so the cloned draft doesn't
    # collide with the source's audit number.
    src.seq_no = src.seq_no + 1
    src.year = date.today().year

    st.session_state["audit"] = src
    st.session_state.pop("loaded_id", None)


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
    """Auto-save an unsaved draft as soon as the user has typed anything,
    so `audit.id` is set and downstream features (Teatmik token-fragment
    links, EHR import-API endpoints, pending_imports rows) start
    working without a manual «Save draft» click.

    Returns True if a new row was created, False if no-op (already saved
    or no data yet).
    """
    if audit.id is not None:
        return False
    if not _audit_has_user_data(audit):
        return False
    with session_scope() as s:
        new_id = upsert_audit(s, audit)
    audit.id = new_id
    set_current(audit)
    return True
