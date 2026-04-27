"""Shared session-state helpers for Streamlit pages."""

from __future__ import annotations

import contextlib
import hashlib
from datetime import date, datetime

import streamlit as st

from tadf.db.repo import (
    delete_all_snapshots,
    delete_audit,
    delete_snapshot,
    list_audits,
    list_drafts,
    list_snapshots,
    load_audit,
    load_snapshot,
    next_seq_no,
    save_snapshot,
    upsert_audit,
)
from tadf.db.session import session_scope
from tadf.models import Audit, Auditor, Building, Client


def _new_audit() -> Audit:
    year = date.today().year
    with session_scope() as s:
        seq_no = next_seq_no(s, year)
    return Audit(
        seq_no=seq_no,
        year=year,
        type="EA",
        # Per father's preference (most common subtype in his practice).
        # `kasutuseelne` and `korraline` remain as picker options.
        subtype="erakorraline",
        visit_date=date.today(),
        composer=Auditor(full_name=""),
        reviewer=Auditor(full_name="Fjodor Sokolov", kutsetunnistus_no="148515"),
        building=Building(address=""),
        client=Client(name=""),
    )


def get_current() -> Audit:
    if "audit" in st.session_state:
        cached = st.session_state["audit"]
        # Mirror the audit id back into the URL on every page render so
        # that navigating between pages — or refreshing — never loses
        # the «which draft is open» pin. Cheap (no DB call), and a no-op
        # if the URL already has the right value.
        if cached.id is not None:
            _sync_audit_id_query_param(cached.id)
        return cached

    # Browser refresh / new session — try to restore from URL ?audit_id=N.
    # `st.query_params` was added in 1.30; fall back gracefully.
    try:
        qp = st.query_params  # type: ignore[attr-defined]
        raw = qp.get("audit_id")
        if raw is not None:
            try:
                aid = int(raw)
            except (TypeError, ValueError):
                aid = None
            if aid is not None:
                with session_scope() as s:
                    try:
                        st.session_state["audit"] = load_audit(s, aid)
                        st.session_state["loaded_id"] = aid
                        return st.session_state["audit"]
                    except ValueError:
                        # The audit_id in the URL no longer exists (deleted
                        # in another tab). Fall through to a fresh draft;
                        # also clear the stale query param so a subsequent
                        # refresh doesn't keep failing.
                        with contextlib.suppress(AttributeError, KeyError):
                            qp.pop("audit_id")
    except Exception:
        # Streamlit version doesn't support st.query_params, or it raised
        # in an unexpected way — start a fresh draft.
        pass

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
    # Mirror into the URL so a browser refresh restores the same draft.
    _sync_audit_id_query_param(audit_id)


def _sync_audit_id_query_param(audit_id: int | None) -> None:
    """Best-effort URL ?audit_id=N updater. Silently no-op on Streamlit
    versions that don't expose st.query_params."""
    try:
        qp = st.query_params  # type: ignore[attr-defined]
    except AttributeError:
        return
    try:
        if audit_id is None:
            qp.pop("audit_id", None)  # type: ignore[arg-type]
        else:
            qp["audit_id"] = str(audit_id)
    except Exception:
        pass


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
    _sync_audit_id_query_param(None)


# Session-state key tracking the last-persisted audit fingerprint, so
# `ensure_draft_saved` can skip a DB write when nothing has changed.
_AUTO_SAVE_HASH_KEY = "_audit_last_saved_hash"


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

    snapshot_json = audit.model_dump_json()
    was_new_draft = audit.id is None
    with session_scope() as s:
        new_id = upsert_audit(s, audit)
        # Write a history snapshot in the same transaction so a partial
        # crash never leaves a save without its history entry.
        save_snapshot(s, new_id, snapshot_json)
    audit.id = new_id
    set_current(audit)
    st.session_state[_AUTO_SAVE_HASH_KEY] = current_hash
    if was_new_draft:
        # First save assigned an id — pin it in the URL so a browser
        # refresh restores the same draft.
        st.session_state["loaded_id"] = new_id
        _sync_audit_id_query_param(new_id)
    return True


def list_audit_snapshots(audit_id: int) -> list[tuple[int, int, datetime]]:
    """Return [(snapshot_id, version_no, created_at)] newest-first.
    Used by the Новый аудит page to render the «🕘 История» expander
    without reading every snapshot's JSON upfront."""
    with session_scope() as s:
        rows = list_snapshots(s, audit_id)
        return [(r.id, r.version_no, r.created_at) for r in rows]


def restore_audit_snapshot(snapshot_id: int) -> bool:
    """Replace `st.session_state["audit"]` with the audit deserialised
    from the given snapshot. Returns False if the snapshot is missing /
    malformed (caller shows an error). The next `ensure_draft_saved`
    will then write a NEW snapshot of the restored state — so the
    auditor can undo the restore by going to history again."""
    with session_scope() as s:
        restored = load_snapshot(s, snapshot_id)
    if restored is None:
        return False
    st.session_state["audit"] = restored
    st.session_state["loaded_id"] = restored.id
    # Force the next ensure_draft_saved to actually save (write a new
    # snapshot) instead of treating the restore as a no-op.
    st.session_state.pop(_AUTO_SAVE_HASH_KEY, None)
    return True


def delete_audit_snapshot(snapshot_id: int) -> bool:
    """Hard-delete one history version of any audit. Returns True when
    a row was actually removed. The currently-loaded audit (if any) is
    left untouched — only the history record disappears."""
    with session_scope() as s:
        return delete_snapshot(s, snapshot_id)


def clear_audit_snapshots(audit_id: int) -> int:
    """Wipe all history snapshots of one audit. Returns the count
    deleted. The audit row itself stays editable; its «🕘 История»
    list will be empty until the next auto-save creates a fresh v1."""
    with session_scope() as s:
        return delete_all_snapshots(s, audit_id)
