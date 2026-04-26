"""Autocomplete suggestions sourced from the existing audit database.

Used by the form pages to seed `selectbox(accept_new_options=True)` widgets so
the auditor sees previously-entered values when they start typing — addresses,
client names, composer names, kasutusotstarve, etc. — and can either pick or
type a new one.
"""

from __future__ import annotations

from sqlalchemy import distinct

from tadf.db.orm import AuditorRow, BuildingRow, ClientRow
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
