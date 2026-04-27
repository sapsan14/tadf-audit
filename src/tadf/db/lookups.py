"""Autocomplete suggestions sourced from the directory tables.

Used by the form pages to seed `selectbox(accept_new_options=True)` widgets so
the auditor sees previously-entered values when they start typing — addresses,
client names, composer names, kasutusotstarve, etc. — and can either pick or
type a new one.

Source of truth is the `directory_*` tables (one row per unique name/value),
NOT the per-audit AuditorRow / BuildingRow / ClientRow rows. Those still
exist for audit history; the directory mirrors the most-recent values per
name and is mirrored on every save (`repo._mirror_to_directory`). Switching
to the directory means:

  * the dropdown stays small and curated (no DISTINCT-over-history scan),
  * the auditor can explicitly delete a stale entry — that's impossible
    with the legacy `_distinct(AuditorRow.full_name)` query, which would
    re-surface the deleted name on the next save,
  * autofill returns one canonical value per name (no "latest of N audits
    that all spelled the same name slightly differently").
"""

from __future__ import annotations

from sqlalchemy import distinct

from tadf.db.orm import (
    AuditRow,
    BuildingRow,
    DirectoryAuditorRow,
    DirectoryBuilderRow,
    DirectoryClientRow,
    DirectoryDesignerRow,
    DirectoryUsePurposeRow,
)
from tadf.db.session import session_scope


def _names(model, attr: str) -> list[str]:
    with session_scope() as s:
        rows = s.query(getattr(model, attr)).order_by(getattr(model, attr)).all()
    return [(v[0] or "").strip() for v in rows if v[0] and v[0].strip()]


def building_addresses() -> list[str]:
    """Addresses still come from per-audit BuildingRow rows. We don't keep a
    directory of addresses — each audit has its own (the in-ADS address
    picker on the page is the canonical source for new addresses).
    """
    with session_scope() as s:
        rows = s.query(distinct(BuildingRow.address)).all()
    return sorted({(v[0] or "").strip() for v in rows if v[0]})


def building_use_purposes() -> list[str]:
    return _names(DirectoryUsePurposeRow, "value")


def client_names() -> list[str]:
    return _names(DirectoryClientRow, "name")


def composer_names() -> list[str]:
    return _names(DirectoryAuditorRow, "full_name")


def composer_companies() -> list[str]:
    """Companies aggregated from all known auditors. We don't keep a separate
    directory_company table — the same company may appear under multiple
    auditors, and Ariregister already provides the authoritative source via
    `tadf.external.ariregister_client`. Sorted, deduped, empty-stripped."""
    with session_scope() as s:
        rows = s.query(distinct(DirectoryAuditorRow.company)).all()
    return sorted({(v[0] or "").strip() for v in rows if v[0] and v[0].strip()})


def designer_names() -> list[str]:
    return _names(DirectoryDesignerRow, "name")


def builder_names() -> list[str]:
    return _names(DirectoryBuilderRow, "name")


def latest_auditor_by_name(full_name: str | None) -> dict | None:
    """Return the directory record for `full_name` as a plain dict (id
    excluded), or None if no match.

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
            s.query(DirectoryAuditorRow)
            .filter(DirectoryAuditorRow.full_name == name)
            .one_or_none()
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
    """Return the directory record for `name` (case-insensitive after strip),
    as a plain dict (id excluded), or None if no match."""
    cleaned = (name or "").strip()
    if not cleaned:
        return None
    with session_scope() as s:
        row = (
            s.query(DirectoryClientRow)
            .filter(DirectoryClientRow.name == cleaned)
            .one_or_none()
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
