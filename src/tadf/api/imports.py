"""Read pending imports from SQLite (Streamlit side) + normalise the
raw EHR / Teatmik JSON into Building / Client field dicts that the
existing extractor preview UI knows how to render.

The browser helper sends RAW JSON / parsed-DOM data — its job is just to
shovel bytes through CORS. All field-mapping happens here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select, update

from tadf.db.orm import PendingImportRow
from tadf.db.session import session_scope


@dataclass
class PendingImport:
    id: int
    audit_id: int
    kind: str  # "ehr" | "teatmik"
    payload: dict[str, Any]
    source_url: str | None
    received_at: datetime


def list_pending(audit_id: int) -> list[PendingImport]:
    """Return unapplied + unrejected imports for an audit, oldest first."""
    with session_scope() as s:
        stmt = (
            select(PendingImportRow)
            .where(
                PendingImportRow.audit_id == audit_id,
                PendingImportRow.applied_at.is_(None),
                PendingImportRow.rejected_at.is_(None),
            )
            .order_by(PendingImportRow.received_at.asc())
        )
        rows = s.scalars(stmt).all()
        return [
            PendingImport(
                id=r.id,
                audit_id=r.audit_id,
                kind=r.kind,
                payload=json.loads(r.payload_json),
                source_url=r.source_url,
                received_at=r.received_at,
            )
            for r in rows
        ]


def mark_applied(import_id: int) -> None:
    with session_scope() as s:
        s.execute(
            update(PendingImportRow)
            .where(PendingImportRow.id == import_id)
            .values(applied_at=datetime.utcnow())
        )


def mark_rejected(import_id: int) -> None:
    with session_scope() as s:
        s.execute(
            update(PendingImportRow)
            .where(PendingImportRow.id == import_id)
            .values(rejected_at=datetime.utcnow())
        )


# ---------------------------------------------------------------------------
# Mappers — raw JSON → Building / Client field dicts.
# ---------------------------------------------------------------------------


_EHR_FIELD_MAP: dict[str, str] = {
    # EHR API field name → our Building model field name. Best-effort,
    # adjusted as we observe real responses (the userscript records
    # source_url so we can iterate without re-hitting the API).
    "address": "address",
    "ehrCode": "ehr_code",
    "ehr_code": "ehr_code",
    "kataster": "kataster_no",
    "kataster_no": "kataster_no",
    "katastrInumber": "kataster_no",
    "useTypeName": "use_purpose",
    "use_purpose": "use_purpose",
    "constructionYear": "construction_year",
    "construction_year": "construction_year",
    "renovationYear": "last_renovation_year",
    "last_renovation_year": "last_renovation_year",
    "footprint": "footprint_m2",
    "footprint_m2": "footprint_m2",
    "ehitisealunePind": "footprint_m2",
    "height": "height_m",
    "height_m": "height_m",
    "korgus": "height_m",
    "volume": "volume_m3",
    "volume_m3": "volume_m3",
    "maht": "volume_m3",
    "storeysAbove": "storeys_above",
    "storeys_above": "storeys_above",
    "korruseteArvMaapeal": "storeys_above",
    "storeysBelow": "storeys_below",
    "storeys_below": "storeys_below",
    "korruseteArvMaaalune": "storeys_below",
    "fireClass": "fire_class",
    "fire_class": "fire_class",
    "tulepusivusKlass": "fire_class",
    "siteArea": "site_area_m2",
    "site_area_m2": "site_area_m2",
}

_FIRE_CLASS_VALID = {"TP-1", "TP-2", "TP-3"}


def map_ehr(payload: dict[str, Any]) -> dict[str, Any]:
    """Best-effort mapping: collect any recognised key under the canonical
    Building field name. Keys we don't recognise are ignored (they show
    up in the debug expander on the Здание page so we can extend the
    map). Numeric strings are coerced to int/float; fire_class is
    normalised to the canonical TP-1/TP-2/TP-3 form."""
    out: dict[str, Any] = {}
    # Some EHR responses nest the building object — try common shapes.
    for candidate in (
        payload,
        payload.get("building") if isinstance(payload, dict) else None,
        payload.get("data") if isinstance(payload, dict) else None,
    ):
        if not isinstance(candidate, dict):
            continue
        for src, dst in _EHR_FIELD_MAP.items():
            if src in candidate and dst not in out:
                out[dst] = candidate[src]
    # Coerce numeric strings.
    for k in ("construction_year", "last_renovation_year", "storeys_above", "storeys_below"):
        if isinstance(out.get(k), str):
            try:
                out[k] = int(out[k])
            except ValueError:
                out.pop(k, None)
    for k in ("footprint_m2", "height_m", "volume_m3", "site_area_m2"):
        if isinstance(out.get(k), str):
            try:
                out[k] = float(out[k].replace(",", "."))
            except ValueError:
                out.pop(k, None)
    # Normalise fire_class.
    fc = out.get("fire_class")
    if isinstance(fc, str):
        norm = fc.upper().replace(" ", "")
        if norm.startswith("TP") and not norm.startswith("TP-"):
            norm = "TP-" + norm[2:]
        out["fire_class"] = norm if norm in _FIRE_CLASS_VALID else None
    return {k: v for k, v in out.items() if v is not None}


def map_teatmik(payload: dict[str, Any]) -> dict[str, Any]:
    """Teatmik payload is a small dict the userscript / bookmarklet
    builds from the company-detail page DOM. Expected keys:
    name, reg_code, address, status, email, phone, legal_form, capital,
    plus an optional `target` hint (`designer` / `builder` / `client`)
    that mirrors which TADF form section the auditor was on when
    they triggered the lookup. Returns the same dict (minus empty
    values) — no field-name rename needed for the Client model."""
    keys = ("name", "reg_code", "address", "status", "email", "phone",
            "legal_form", "capital", "target")
    out = {k: payload.get(k) for k in keys}
    return {k: v for k, v in out.items() if v not in (None, "")}


__all__ = [
    "PendingImport",
    "list_pending",
    "mark_applied",
    "mark_rejected",
    "map_ehr",
    "map_teatmik",
]
