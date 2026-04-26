from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["info", "nonconf_minor", "nonconf_major", "hazard"]
FindingStatus = Literal["open", "resolved"]


class Finding(BaseModel):
    """A single observation from the audit, attached to a section.

    The auditor types `observation_raw` as bullet notes; LLM (Phase 2) may
    produce `observation_polished` as Estonian prose. Only one of the two
    reaches the rendered DOCX, controlled by `accepted_polished`.
    """

    id: int | None = None
    audit_id: int | None = None
    section_ref: str = Field(description="Section/subsection key, e.g. '6.1', '7.2'")
    severity: Severity = "info"
    observation_raw: str
    observation_polished: str | None = None
    accepted_polished: bool = False
    recommendation: str | None = None
    legal_ref_codes: list[str] = Field(default_factory=list)
    photo_ids: list[int] = Field(default_factory=list)
    status: FindingStatus = "open"
