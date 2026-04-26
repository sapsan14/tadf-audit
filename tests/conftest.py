from __future__ import annotations

from datetime import date

import pytest

from tadf.models import Audit, Auditor, Building, Client, Finding


def make_minimal_audit() -> Audit:
    """Audit with all §5-mandatory fields filled — should pass the checklist."""
    return Audit(
        seq_no=1,
        year=2026,
        type="EP",
        subtype="kasutuseelne",
        visit_date=date(2026, 1, 20),
        purpose="Hinnata aiamaja vastavust nõuetele.",
        scope="Hoone konstruktsioonid, tehnosüsteemid ja tuleohutus.",
        composer=Auditor(full_name="Aleksei Sholokhov", company="UNTWERP OÜ"),
        reviewer=Auditor(
            full_name="Fjodor Sokolov",
            kutsetunnistus_no="148515",
            qualification="Diplomeeritud insener tase 7",
        ),
        building=Building(
            address="Ida-Viru maakond, Sillamäe linn, Linna AÜ 1062",
            ehr_code="102032773",
            kataster_no="85101:004:0020",
            construction_year=1985,
            footprint_m2=75.5,
            volume_m3=210.0,
            storeys_above=2,
            storeys_below=0,
            fire_class="TP-3",
            use_purpose="aiamaja",
        ),
        client=Client(name="Test Tellija OÜ"),
        findings=[
            Finding(section_ref="6.1", observation_raw="Vundament heas seisus."),
            Finding(section_ref="8.1", observation_raw="Evakuatsioon nõuetele vastav."),
            Finding(section_ref="11", observation_raw="Hoone on kasutamiskõlblik."),
            Finding(section_ref="14", observation_raw="Lõpphinnang: ohutu ja kasutamiskõlblik."),
        ],
    )


@pytest.fixture
def audit() -> Audit:
    return make_minimal_audit()
