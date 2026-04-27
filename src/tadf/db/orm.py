"""SQLAlchemy ORM tables. Each table mirrors a Pydantic model in tadf.models.

We keep ORM and Pydantic separate so the rendering pipeline (which only
needs Pydantic) doesn't depend on a database connection.
"""

from __future__ import annotations

import json
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class AuditorRow(Base):
    __tablename__ = "auditor"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    company: Mapped[str | None] = mapped_column(String(200))
    company_reg_nr: Mapped[str | None] = mapped_column(String(20))
    kutsetunnistus_no: Mapped[str | None] = mapped_column(String(20))
    qualification: Mapped[str | None] = mapped_column(String(100))
    id_code: Mapped[str | None] = mapped_column(String(20))
    independence_declaration: Mapped[str | None] = mapped_column(Text)
    signature_image_path: Mapped[str | None] = mapped_column(String(500))


class BuildingRow(Base):
    __tablename__ = "building"
    id: Mapped[int] = mapped_column(primary_key=True)
    address: Mapped[str] = mapped_column(String(500))
    kataster_no: Mapped[str | None] = mapped_column(String(50))
    ehr_code: Mapped[str | None] = mapped_column(String(20))
    use_purpose: Mapped[str | None] = mapped_column(String(200))
    construction_year: Mapped[int | None] = mapped_column(Integer)
    last_renovation_year: Mapped[int | None] = mapped_column(Integer)
    designer: Mapped[str | None] = mapped_column(String(200))
    builder: Mapped[str | None] = mapped_column(String(200))
    footprint_m2: Mapped[float | None] = mapped_column()
    height_m: Mapped[float | None] = mapped_column()
    volume_m3: Mapped[float | None] = mapped_column()
    storeys_above: Mapped[int | None] = mapped_column(Integer)
    storeys_below: Mapped[int | None] = mapped_column(Integer)
    fire_class: Mapped[str | None] = mapped_column(String(10))
    pre_2003: Mapped[bool] = mapped_column(default=False)
    substitute_docs_note: Mapped[str | None] = mapped_column(Text)
    site_area_m2: Mapped[float | None] = mapped_column()


class ClientRow(Base):
    __tablename__ = "client"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    reg_code: Mapped[str | None] = mapped_column(String(20))
    contact_email: Mapped[str | None] = mapped_column(String(200))
    contact_phone: Mapped[str | None] = mapped_column(String(50))
    address: Mapped[str | None] = mapped_column(String(500))


class AuditRow(Base):
    __tablename__ = "audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    seq_no: Mapped[int] = mapped_column(Integer)
    year: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(4))
    subtype: Mapped[str] = mapped_column(String(20), default="kasutuseelne")
    purpose: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str | None] = mapped_column(Text)
    methodology_version: Mapped[str] = mapped_column(String(10), default="v1")
    visit_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    composer_id: Mapped[int] = mapped_column(ForeignKey("auditor.id"))
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("auditor.id"))
    building_id: Mapped[int] = mapped_column(ForeignKey("building.id"))
    client_id: Mapped[int | None] = mapped_column(ForeignKey("client.id"))

    composer: Mapped[AuditorRow] = relationship(foreign_keys=[composer_id])
    reviewer: Mapped[AuditorRow] = relationship(foreign_keys=[reviewer_id])
    building: Mapped[BuildingRow] = relationship()
    client: Mapped[ClientRow | None] = relationship()
    findings: Mapped[list[FindingRow]] = relationship(back_populates="audit", cascade="all, delete-orphan")
    photos: Mapped[list[PhotoRow]] = relationship(back_populates="audit", cascade="all, delete-orphan")


class FindingRow(Base):
    __tablename__ = "finding"
    id: Mapped[int] = mapped_column(primary_key=True)
    audit_id: Mapped[int] = mapped_column(ForeignKey("audit.id"))
    section_ref: Mapped[str] = mapped_column(String(20))
    severity: Mapped[str] = mapped_column(String(20), default="info")
    observation_raw: Mapped[str] = mapped_column(Text)
    observation_polished: Mapped[str | None] = mapped_column(Text)
    accepted_polished: Mapped[bool] = mapped_column(default=False)
    recommendation: Mapped[str | None] = mapped_column(Text)
    legal_ref_codes_json: Mapped[str] = mapped_column(Text, default="[]")
    photo_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(20), default="open")

    audit: Mapped[AuditRow] = relationship(back_populates="findings")

    @property
    def legal_ref_codes(self) -> list[str]:
        return json.loads(self.legal_ref_codes_json)

    @property
    def photo_ids(self) -> list[int]:
        return json.loads(self.photo_ids_json)


class PhotoRow(Base):
    __tablename__ = "photo"
    id: Mapped[int] = mapped_column(primary_key=True)
    audit_id: Mapped[int] = mapped_column(ForeignKey("audit.id"))
    path: Mapped[str] = mapped_column(String(500))
    taken_at: Mapped[datetime | None] = mapped_column(DateTime)
    gps_lat: Mapped[float | None] = mapped_column()
    gps_lon: Mapped[float | None] = mapped_column()
    sha256: Mapped[str | None] = mapped_column(String(64))
    caption_auditor: Mapped[str | None] = mapped_column(Text)
    caption_llm_draft: Mapped[str | None] = mapped_column(Text)
    section_ref: Mapped[str | None] = mapped_column(String(20))
    accepted: Mapped[bool] = mapped_column(default=True)

    audit: Mapped[AuditRow] = relationship(back_populates="photos")


class PendingImportRow(Base):
    """One row per inbound import from the bookmarklet / Tampermonkey
    userscript. The Streamlit UI polls this table on every page rerun and
    surfaces unapplied imports as accept/reject preview panels.

    `kind` ∈ {"ehr", "teatmik"}; `payload_json` holds the raw JSON the
    browser-side helper POSTed; `applied_at` is set once the auditor
    accepts the import (so we can keep history without re-prompting).
    """

    __tablename__ = "pending_import"
    id: Mapped[int] = mapped_column(primary_key=True)
    audit_id: Mapped[int] = mapped_column(ForeignKey("audit.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(500))
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime)


class LlmUsageRow(Base):
    """One row per Claude API call. Persists across deploys (lives in the
    SQLite file in tadf-data volume on Hetzner). Replaces the JSONL log
    that lived only in the cache dir."""

    __tablename__ = "llm_usage"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    model: Mapped[str] = mapped_column(String(64), index=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
