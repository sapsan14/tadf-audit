from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Photo(BaseModel):
    id: int | None = None
    audit_id: int | None = None
    path: str
    taken_at: datetime | None = None
    gps_lat: float | None = None
    gps_lon: float | None = None
    sha256: str | None = None
    caption_auditor: str | None = None
    caption_llm_draft: str | None = None
    section_ref: str | None = None  # e.g. "6.1" — links to a Section subkey
    accepted: bool = True
