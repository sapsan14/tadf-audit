"""Autocomplete suggestions sourced from the existing audit database.

Used by the form pages to seed `selectbox(accept_new_options=True)` widgets so
the auditor sees previously-entered values when they start typing — addresses,
client names, composer names, kasutusotstarve, etc. — and can either pick or
type a new one.
"""

from __future__ import annotations

from sqlalchemy import distinct

from tadf.db.orm import AuditorRow, AuditRow, BuildingRow, ClientRow
from tadf.db.session import session_scope


def _distinct(column) -> list[str]:
    with session_scope() as s:
        rows = s.query(distinct(column)).all()
    out = sorted({(v[0] or "").strip() for v in rows if v[0]})
    return out


def building_addresses() -> list[str]:
    return _distinct(BuildingRow.address)


def building_use_purposes() -> list[str]:
    return _distinct(BuildingRow.use_purpose)


def client_names() -> list[str]:
    return _distinct(ClientRow.name)


def composer_names() -> list[str]:
    return _distinct(AuditorRow.full_name)


def composer_companies() -> list[str]:
    return _distinct(AuditorRow.company)


def latest_auditor_by_name(full_name: str | None) -> dict | None:
    """Return the most-recent AuditorRow that matches `full_name` as a
    plain dict (id excluded), or None if no match.

    Used by the «Новый аудит» page to auto-fill the rest of the auditor
    fields the moment the user picks a previously-entered name from the
    combobox — saves ~3 clicks/audit and prevents subtle typo divergence
    between two audits attributed to the same person.
    """
    name = (full_name or "").strip()
    if not name:
        return None
    with session_scope() as s:
        row = (
            s.query(AuditorRow)
            .filter(AuditorRow.full_name == name)
            .order_by(AuditorRow.id.desc())
            .first()
        )
        if row is None:
            return None
        return {
            "full_name": row.full_name,
            "company": row.company,
            "company_reg_nr": row.company_reg_nr,
            "kutsetunnistus_no": row.kutsetunnistus_no,
            "qualification": row.qualification,
            "id_code": row.id_code,
            "independence_declaration": row.independence_declaration,
            "signature_image_path": row.signature_image_path,
        }


def latest_header_override(exclude_audit_id: int | None = None) -> str | None:
    """Return the most-recently-used non-empty `header_override` from any
    saved audit. Used as the default for a brand-new draft so the auditor
    doesn't have to re-type the same Töö nr/Töö nimetus skeleton on
    every audit. Optionally exclude the current audit (we want the LAST
    one OTHER than this draft)."""
    return _latest_override("header_override", exclude_audit_id)


def latest_footer_override(exclude_audit_id: int | None = None) -> str | None:
    return _latest_override("footer_override", exclude_audit_id)


def _latest_override(column: str, exclude_audit_id: int | None) -> str | None:
    col = getattr(AuditRow, column)
    with session_scope() as s:
        q = s.query(col).filter(col.isnot(None)).filter(col != "")
        if exclude_audit_id is not None:
            q = q.filter(AuditRow.id != exclude_audit_id)
        row = q.order_by(AuditRow.updated_at.desc(), AuditRow.id.desc()).first()
        return row[0] if row else None


def latest_client_by_name(name: str | None) -> dict | None:
    """Return the most-recent ClientRow that matches `name` (case-insensitive,
    after strip), as a plain dict (id excluded), or None if no match."""
    cleaned = (name or "").strip()
    if not cleaned:
        return None
    with session_scope() as s:
        row = (
            s.query(ClientRow)
            .filter(ClientRow.name == cleaned)
            .order_by(ClientRow.id.desc())
            .first()
        )
        if row is None:
            return None
        return {
            "name": row.name,
            "reg_code": row.reg_code,
            "contact_email": row.contact_email,
            "contact_phone": row.contact_phone,
            "address": row.address,
        }
