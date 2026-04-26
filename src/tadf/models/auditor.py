from __future__ import annotations

from pydantic import BaseModel, Field


class Auditor(BaseModel):
    """Person who composes or reviews an audit.

    The corpus shows two distinct roles:
      - composer (Auditi koostas) — the engineer who produces the report
      - reviewer (Auditi kontrollis / vastutav pädev isik) — the certified person
        who is legally responsible (this is Fjodor Sokolov, kutsetunnistus 148515)

    The same Auditor record can fill either role for a given audit; roles live
    on the Audit, not on the Auditor.
    """

    id: int | None = None
    full_name: str
    company: str | None = None
    company_reg_nr: str | None = None
    kutsetunnistus_no: str | None = None
    qualification: str | None = Field(
        default=None,
        description="e.g. AA-1-01, AA-1-03, AR-3-01, 'Diplomeeritud insener tase 7'",
    )
    id_code: str | None = Field(default=None, description="Estonian ID code (Isikukood)")
    independence_declaration: str | None = None
    signature_image_path: str | None = None
