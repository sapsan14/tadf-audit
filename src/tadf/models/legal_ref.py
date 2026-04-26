from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class LegalReference(BaseModel):
    """Canonical pointer to an Estonian act, decree or standard.

    The LLM (Phase 2) is only allowed to **rank** these — never to invent new
    citations. Seeded from `legal/references.yaml`.
    """

    code: str = Field(description="Short code, e.g. 'EhS § 11', 'EVS 812-7'")
    title_et: str
    url: str | None = None
    section_keys: list[str] = Field(
        default_factory=list,
        description="Report sections this reference is relevant to, e.g. ['8', '9']",
    )
    audit_types: list[str] = Field(
        default_factory=list,
        description="Restricts to specific audit types ('EA', 'EP', ...); empty = all",
    )
    effective_from: date | None = None
    superseded_by: str | None = None
