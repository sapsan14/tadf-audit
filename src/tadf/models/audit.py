from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from tadf.models.auditor import Auditor
from tadf.models.building import Building
from tadf.models.finding import Finding
from tadf.models.photo import Photo

AuditType = Literal["EA", "EP", "TJ", "TP", "AU"]
AuditSubtype = Literal["kasutuseelne", "korraline", "erakorraline"]
AuditStatus = Literal["draft", "review", "signed", "submitted"]


class Client(BaseModel):
    id: int | None = None
    name: str
    reg_code: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    address: str | None = None


class Audit(BaseModel):
    """A single audit engagement.

    The corpus shows the report has two distinct auditor roles:
      - composer  — `Auditi koostas` (engineer who produces the report)
      - reviewer  — `Auditi kontrollis` / vastutav pädev isik (legally responsible)
    Both are required for the report; usually only `reviewer` is the kutsetunnistus
    holder. They MAY be the same person.
    """

    id: int | None = None
    seq_no: int = Field(description="Sequence number within the year, e.g. 12")
    year: int
    type: AuditType
    subtype: AuditSubtype = "kasutuseelne"
    purpose: str | None = None
    scope: str | None = None
    methodology_version: str = "v1"
    visit_date: date

    composer: Auditor
    reviewer: Auditor
    building: Building
    client: Client | None = None

    findings: list[Finding] = Field(default_factory=list)
    photos: list[Photo] = Field(default_factory=list)

    # Optional auditor-supplied overrides for the per-page header/footer text.
    # When None, the docx renderer falls back to a value computed from the
    # other audit fields (Töö nr / Töö nimetus / Pädev isik). When set, the
    # override is used verbatim. Persisted on the draft so the next save
    # round-trip keeps it.
    header_override: str | None = None
    footer_override: str | None = None

    status: AuditStatus = "draft"
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def display_no(self) -> str:
        """Audit number in the corpus filename style: '012026' = seq 01 / 2026."""
        return f"{self.seq_no:03d}{self.year}"
