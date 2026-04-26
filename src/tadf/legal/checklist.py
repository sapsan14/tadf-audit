"""Coverage check for an Audit context against the mandatory fields enumerated in
§5 of MKM määrus 'Ehitise auditi tegemise kord' (RT 120102020004) and the related
provisions of Ehitusseadustik (105032015001).

This is the gate that runs immediately before render. A failing check returns
the list of missing items so the UI can point the auditor back to the relevant
form page.

Each CheckResult provides bilingual `why` text (Estonian + Russian) so the §5
report panel is readable in either language.
"""

from __future__ import annotations

from dataclasses import dataclass

from tadf.models import Audit


@dataclass(frozen=True)
class CheckResult:
    field: str
    section_hint: str
    why_et: str
    why_ru: str

    @property
    def why(self) -> str:
        """Two-line bilingual message: Estonian first, then Russian."""
        return f"🇪🇪 {self.why_et}\n🇷🇺 {self.why_ru}"

    def __str__(self) -> str:
        return f"[{self.field}] {self.why_et} / {self.why_ru}  (form: {self.section_hint})"


def check(audit: Audit) -> list[CheckResult]:
    """Return a list of missing required items. Empty list = pass."""
    missing: list[CheckResult] = []

    if not audit.purpose:
        missing.append(
            CheckResult(
                "audit.purpose",
                "Üldosa",
                "§5 nõuab auditi eesmärki (auditi liik ja põhjus)",
                "§5 требует указать цель аудита (вид и причину)",
            )
        )
    if not audit.scope:
        missing.append(
            CheckResult(
                "audit.scope",
                "Üldosa",
                "§5 nõuab auditi ulatuse kirjeldust",
                "§5 требует описание области аудита",
            )
        )
    if not audit.visit_date:
        missing.append(
            CheckResult(
                "audit.visit_date",
                "Üldosa",
                "§5 nõuab paikvaatluse kuupäeva",
                "§5 требует дату визуального осмотра",
            )
        )

    if not audit.reviewer.full_name:
        missing.append(
            CheckResult(
                "reviewer.full_name",
                "Allkirjad",
                "§5 nõuab vastutava pädeva isiku täisnime",
                "§5 требует ФИО ответственного лица (vastutav pädev isik)",
            )
        )
    if not audit.reviewer.kutsetunnistus_no:
        missing.append(
            CheckResult(
                "reviewer.kutsetunnistus_no",
                "Allkirjad",
                "§5 nõuab vastutava pädeva isiku kutsetunnistuse numbrit",
                "§5 требует номер kutsetunnistus ответственного лица",
            )
        )

    if not audit.composer.full_name:
        missing.append(
            CheckResult(
                "composer.full_name",
                "Allkirjad",
                "§5 nõuab auditi koostaja täisnime",
                "§5 требует ФИО составителя аудита (Auditi koostas)",
            )
        )

    b = audit.building
    if not b.address:
        missing.append(
            CheckResult(
                "building.address",
                "Ehitis",
                "§5 nõuab ehitise aadressi",
                "§5 требует адрес объекта",
            )
        )
    if not b.kataster_no and not b.ehr_code:
        missing.append(
            CheckResult(
                "building.kataster_no | ehr_code",
                "Ehitis",
                "§5 nõuab unikaalset identifikaatorit (katastritunnus või EHR-kood)",
                "§5 требует уникальный идентификатор (katastritunnus или EHR-код)",
            )
        )
    if b.construction_year is None and not b.substitute_docs_note:
        missing.append(
            CheckResult(
                "building.construction_year",
                "Ehitis",
                (
                    "§5 nõuab ehitusaastat; kui see puudub, täida 'Pre-2003 ehitis' "
                    "ja substitute_docs_note (EhSRS § 28)"
                ),
                (
                    "§5 требует год постройки; если не известно — поставьте "
                    "'Pre-2003 ehitis' и заполните substitute_docs_note (EhSRS § 28)"
                ),
            )
        )
    if b.footprint_m2 is None:
        missing.append(
            CheckResult(
                "building.footprint_m2",
                "Tehnilised näitajad",
                "RT 110062015008 nõuab ehitisealust pinda (m²)",
                "RT 110062015008 требует ehitisealune pind (площадь застройки, m²)",
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
                "Kokkuvõte (jaotus 11) peab sisaldama vähemalt ühte audiitori-koostatud lõiku",
                "Kokkuvõte (раздел 11) должен содержать хотя бы одну запись от аудитора",
            )
        )
    if not has_final:
        missing.append(
            CheckResult(
                "findings[section=14]",
                "Lõpphinnang",
                "Lõpphinnang (jaotus 14) peab sisaldama vähemalt ühte audiitori-koostatud lõiku",
                "Lõpphinnang (раздел 14) должен содержать хотя бы одну запись от аудитора",
            )
        )

    # Conditional: fire-safety section (8) only when fire_class is set
    if b.fire_class is not None:
        has_fire = any(f.section_ref.startswith("8") for f in audit.findings)
        if not has_fire:
            missing.append(
                CheckResult(
                    "findings[section=8]",
                    "Tulekaitse",
                    (
                        "Tulepüsivusklass on määratud, kuid tuleohutuse jaotuses (8) "
                        "ei ole ühtegi leidu — Tuleohutuse seadus nõuab"
                    ),
                    (
                        "Указан класс огнестойкости, но в разделе пожарной безопасности (8) "
                        "нет ни одной находки — требуется по Tuleohutuse seadus"
                    ),
                )
            )

    return missing


def passes(audit: Audit) -> bool:
    return len(check(audit)) == 0
