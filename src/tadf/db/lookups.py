"""Autocomplete suggestions sourced from the existing audit database.

Used by the form pages to seed `selectbox(accept_new_options=True)` widgets so
the auditor sees previously-entered values when they start typing — addresses,
client names, composer names, kasutusotstarve, etc. — and can either pick or
type a new one.

Also exposes `*_by_name` resolvers that return the FULL most-recent record
matching a name. The form pages use these to autofill companion fields
(reg_code / email / phone / address for clients; kut № / qual / company /
reg. nr for auditors) the moment the auditor picks a past name from the
combobox.
"""

from __future__ import annotations

from sqlalchemy import distinct

from tadf.db.orm import AuditorRow, AuditRow, BuildingRow, ClientRow, LookupHiddenRow
from tadf.db.session import session_scope
from tadf.models import Auditor, Client

# Canonical kind labels for the autocomplete blocklist (`LookupHiddenRow.kind`).
# Centralised so the UI and the lookups stay in sync.
KIND_CLIENT_NAME = "client_name"
KIND_COMPOSER_NAME = "composer_name"
KIND_COMPOSER_COMPANY = "composer_company"
KIND_BUILDING_ADDRESS = "building_address"
KIND_BUILDING_USE_PURPOSE = "building_use_purpose"


def _hidden_values(kind: str) -> set[str]:
    """Returns case-folded blocked values for `kind`."""
    with session_scope() as s:
        rows = (
            s.query(LookupHiddenRow.value)
            .filter(LookupHiddenRow.kind == kind)
            .all()
        )
    return {(r[0] or "").strip().casefold() for r in rows if r[0]}


def _distinct(column, *, kind: str | None = None) -> list[str]:
    with session_scope() as s:
        rows = s.query(distinct(column)).all()
    raw = {(v[0] or "").strip() for v in rows if v[0]}
    if kind is not None:
        hidden = _hidden_values(kind)
        raw = {v for v in raw if v.casefold() not in hidden}
    return sorted(raw)


def building_addresses() -> list[str]:
    return _distinct(BuildingRow.address, kind=KIND_BUILDING_ADDRESS)


def building_use_purposes() -> list[str]:
    return _distinct(BuildingRow.use_purpose, kind=KIND_BUILDING_USE_PURPOSE)


def client_names() -> list[str]:
    return _distinct(ClientRow.name, kind=KIND_CLIENT_NAME)


def composer_names() -> list[str]:
    return _distinct(AuditorRow.full_name, kind=KIND_COMPOSER_NAME)


def composer_companies() -> list[str]:
    return _distinct(AuditorRow.company, kind=KIND_COMPOSER_COMPANY)


# ---------------------------------------------------------------------------
# Blocklist management — `hide_*` / `unhide_*` for the «Manage suggestions» UI
# ---------------------------------------------------------------------------


def hide_lookup(kind: str, value: str) -> None:
    """Add `value` to the blocklist for `kind`. No-op if already hidden."""
    v = (value or "").strip()
    if not v:
        return
    folded = v.casefold()
    with session_scope() as s:
        existing = (
            s.query(LookupHiddenRow)
            .filter(LookupHiddenRow.kind == kind)
            .all()
        )
        for row in existing:
            if (row.value or "").strip().casefold() == folded:
                return  # already hidden — preserve original casing
        s.add(LookupHiddenRow(kind=kind, value=v))


def unhide_lookup(kind: str, value: str) -> None:
    """Remove every blocklist entry matching `value` (case-insensitive)
    under `kind`. Idempotent — silent no-op if nothing matched."""
    v = (value or "").strip()
    if not v:
        return
    folded = v.casefold()
    with session_scope() as s:
        rows = (
            s.query(LookupHiddenRow)
            .filter(LookupHiddenRow.kind == kind)
            .all()
        )
        for row in rows:
            if (row.value or "").strip().casefold() == folded:
                s.delete(row)


def hidden_lookups(kind: str) -> list[str]:
    """List of currently hidden values for `kind`, sorted alphabetically.
    Used by the «Manage suggestions» panel to render the «✓ unhide»
    buttons."""
    with session_scope() as s:
        rows = (
            s.query(LookupHiddenRow.value)
            .filter(LookupHiddenRow.kind == kind)
            .all()
        )
    return sorted({(r[0] or "").strip() for r in rows if r[0]})


# ---------------------------------------------------------------------------
# `by_name` resolvers — the autofill backend
# ---------------------------------------------------------------------------


def client_by_name(name: str) -> Client | None:
    """Return the Client from the most-recently-touched audit that has
    `client.name` matching `name` (case-insensitive, trimmed).

    Used by the form pages to autofill reg_code / email / phone / address
    when the auditor picks a past client name from the combobox dropdown
    (or types an exact existing name). Detached from the session before
    returning so the caller can write into a Pydantic model freely.

    Implementation note: case-folding happens in Python, not in SQL.
    SQLite's `LOWER()` is ASCII-only (it leaves `Ü`/`Õ`/cyrillic as-is),
    so a SQL `func.lower()` comparison would silently miss real-world
    Estonian and Russian names. We fetch a small candidate set (joined
    audits, ordered newest-first) and filter Python-side instead.
    """
    needle = (name or "").strip()
    if not needle:
        return None
    folded = needle.casefold()
    with session_scope() as s:
        candidates = (
            s.query(ClientRow)
            .join(AuditRow, AuditRow.client_id == ClientRow.id)
            .order_by(AuditRow.updated_at.desc(), AuditRow.id.desc())
            .all()
        )
        for row in candidates:
            if (row.name or "").strip().casefold() == folded:
                # Materialise into a Pydantic model BEFORE the session
                # closes — otherwise SQLAlchemy raises
                # DetachedInstanceError on attribute access. We don't
                # carry `id` over so the caller's audit.client.id (from
                # a different ClientRow) isn't accidentally aliased.
                return Client(
                    name=row.name,
                    reg_code=row.reg_code,
                    contact_email=row.contact_email,
                    contact_phone=row.contact_phone,
                    address=row.address,
                )
        return None


def auditor_by_name(full_name: str) -> Auditor | None:
    """Return the Auditor (composer OR reviewer) from the most-recently-
    touched audit whose full_name matches `full_name`.

    Looks at both `AuditRow.composer_id` and `AuditRow.reviewer_id` so the
    autofill works regardless of which slot the past audit used. Returns
    None if no match. Case-folding is Python-side (see
    `client_by_name` for rationale).
    """
    needle = (full_name or "").strip()
    if not needle:
        return None
    folded = needle.casefold()
    with session_scope() as s:
        candidates = (
            s.query(AuditorRow)
            .join(
                AuditRow,
                (AuditRow.composer_id == AuditorRow.id)
                | (AuditRow.reviewer_id == AuditorRow.id),
            )
            .order_by(AuditRow.updated_at.desc(), AuditRow.id.desc())
            .all()
        )
        for row in candidates:
            if (row.full_name or "").strip().casefold() == folded:
                return Auditor(
                    full_name=row.full_name,
                    company=row.company,
                    company_reg_nr=row.company_reg_nr,
                    kutsetunnistus_no=row.kutsetunnistus_no,
                    qualification=row.qualification,
                    id_code=row.id_code,
                    independence_declaration=row.independence_declaration,
                    signature_image_path=row.signature_image_path,
                )
        return None
