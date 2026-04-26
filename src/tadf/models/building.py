from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

FireClass = Literal["TP-1", "TP-2", "TP-3"]


class Building(BaseModel):
    """The audit object — a building, structure, or part thereof.

    Fields are aligned with EHR (ehitisregister) terminology and with
    RT 110062015008 'Ehitise tehniliste andmete loetelu' for measurements.
    """

    id: int | None = None
    address: str
    kataster_no: str | None = Field(
        default=None, description="Kinnistu katastritunnus, e.g. 85101:004:0020"
    )
    ehr_code: str | None = Field(default=None, description="Ehitisregistri kood, 7-12 digits")
    use_purpose: str | None = Field(default=None, description="Ehitise kasutusotstarve")
    construction_year: int | None = None
    last_renovation_year: int | None = None
    designer: str | None = None
    builder: str | None = None
    footprint_m2: float | None = Field(default=None, description="Ehitisealune pind (m²)")
    height_m: float | None = None
    volume_m3: float | None = Field(default=None, description="Maht (m³)")
    storeys_above: int | None = Field(default=None, description="Maapealsete korruste arv")
    storeys_below: int | None = Field(default=None, description="Maa-aluste korruste arv")
    fire_class: FireClass | None = Field(default=None, description="Tulepüsivusklass")
    pre_2003: bool = Field(
        default=False,
        description="Pre-2003 structure under EhSRS — audit substitutes for missing documentation",
    )
    substitute_docs_note: str | None = None
    site_area_m2: float | None = Field(default=None, description="Kinnistu pindala (m²)")
