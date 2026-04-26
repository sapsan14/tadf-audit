"""Coverage check for an Audit context against the mandatory fields enumerated in
§5 of MKM määrus 'Ehitise auditi tegemise kord' (RT 120102020004) and the related
provisions of Ehitusseadustik (105032015001).

This is the gate that runs immediately before render. A failing check returns
the list of missing items so the UI can point the auditor back to the relevant
form page.
"""

from __future__ import annotations

from dataclasses import dataclass

from tadf.models import Audit


@dataclass(frozen=True)
class CheckResult:
    field: str
    section_hint: str
    why: str

    def __str__(self) -> str:
        return f"[{self.field}] missing: {self.why}  (form section: {self.section_hint})"


def check(audit: Audit) -> list[CheckResult]:
    """Return a list of missing required items. Empty list = pass."""
    missing: list[CheckResult] = []

    if not audit.purpose:
        missing.append(
            CheckResult("audit.purpose", "Üldosa", "§5 requires audit objective (auditi eesmärk)")
        )
    if not audit.scope:
        missing.append(
            CheckResult("audit.scope", "Üldosa", "§5 requires audit scope (auditi ulatus)")
        )
    if not audit.visit_date:
        missing.append(
            CheckResult(
                "audit.visit_date",
                "Üldosa",
                "§5 requires visual inspection date (paikvaatluse kuupäev)",
            )
        )

    if not audit.reviewer.full_name:
        missing.append(
            CheckResult(
                "reviewer.full_name", "Allkirjad", "§5 requires the responsible auditor's full name"
            )
        )
    if not audit.reviewer.kutsetunnistus_no:
        missing.append(
            CheckResult(
                "reviewer.kutsetunnistus_no",
                "Allkirjad",
                "§5 requires the responsible auditor's kutsetunnistus number",
            )
        )

    if not audit.composer.full_name:
        missing.append(
            CheckResult(
                "composer.full_name", "Allkirjad", "§5 requires the composing auditor's full name"
            )
        )

    b = audit.building
    if not b.address:
        missing.append(
            CheckResult(
                "building.address", "Ehitis", "§5 requires building identification (address)"
            )
        )
    if not b.kataster_no and not b.ehr_code:
        missing.append(
            CheckResult(
                "building.kataster_no | ehr_code",
                "Ehitis",
                "§5 requires unique building identifier (katastritunnus or ehitisregistri kood)",
            )
        )
    if b.construction_year is None and not b.substitute_docs_note:
        missing.append(
            CheckResult(
                "building.construction_year",
                "Ehitis",
                "§5 requires construction date; if unknown, fill substitute_docs_note (EhSRS § 28)",
            )
        )
    if b.footprint_m2 is None:
        missing.append(
            CheckResult(
                "building.footprint_m2",
                "Tehnilised näitajad",
                "RT 110062015008 requires ehitisealune pind",
            )
        )

    # Sections 11 (Kokkuvõte) and 14 (Lõpphinnang) — auditor-only, must be present
    # as findings or free-text in the Audit before render.
    has_summary = any(f.section_ref.startswith("11") for f in audit.findings)
    has_final = any(f.section_ref.startswith("14") for f in audit.findings)
    if not has_summary:
        missing.append(
            CheckResult(
                "findings[section=11]",
                "Kokkuvõte",
                "Kokkuvõte (section 11) must contain at least one auditor-written finding",
            )
        )
    if not has_final:
        missing.append(
            CheckResult(
                "findings[section=14]",
                "Lõpphinnang",
                "Lõpphinnang (section 14) must contain at least one auditor-written finding",
            )
        )

    # Conditional: fire-safety section (8) only when fire_class is set
    # — flag warning if fire_class is set but no findings exist for section 8.
    if b.fire_class is not None:
        has_fire = any(f.section_ref.startswith("8") for f in audit.findings)
        if not has_fire:
            missing.append(
                CheckResult(
                    "findings[section=8]",
                    "Tulekaitse",
                    "fire_class is set but no fire-safety findings — required by Tuleohutuse seadus",
                )
            )

    return missing


def passes(audit: Audit) -> bool:
    return len(check(audit)) == 0
