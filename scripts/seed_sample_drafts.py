"""Seed plausible sample drafts so the «📋 Сохранённые черновики» list
isn't empty on a fresh machine.

Each sample is derived from the filename + filename-encoded date of a
real historical audit in `audit/` — same address shape, same audit type,
same visit-date — but the body fields are intentionally minimal /
work-in-progress so the entries look like genuine **drafts** (a couple
of findings, no signed status, no client filled).

Usage:
    uv run python scripts/seed_sample_drafts.py            # idempotent
    uv run python scripts/seed_sample_drafts.py --force    # re-create

Idempotent: a sample with the same (seq_no, year, type) is left as-is
on subsequent runs unless `--force` is passed (in which case the prior
sample is wiped and re-seeded).

Lives in `scripts/` (not `src/tadf/`) so production code never imports
sample data by accident.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from datetime import date

# Make the local checkout importable when run as a plain script.
_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src"))

from tadf.db.orm import AuditRow  # noqa: E402
from tadf.db.repo import delete_audit, save_audit  # noqa: E402
from tadf.db.session import session_scope  # noqa: E402
from tadf.models import Audit, Auditor, Building, Client, Finding  # noqa: E402


def _reviewer() -> Auditor:
    """Default reviewer (vastutav pädev isik) used across the project."""
    return Auditor(
        full_name="Fjodor Sokolov",
        kutsetunnistus_no="148515",
        qualification="AA-1-01",
        company="TADF Ehitus OÜ",
    )


def _composer() -> Auditor:
    """Composer matches reviewer in the typical small-shop case where the
    same engineer signs and writes the report. Realistic for these samples."""
    return _reviewer()


# Each tuple: (
#   seq_no, year, type, subtype, visit_date,
#   address, kataster_no, ehr_code, use_purpose, year_built,
#   list of (section_ref, severity, observation_raw),
# )
# Addresses + types pulled from the audit/ folder filenames; building
# specs are plausible defaults (not the real values from the report —
# we don't ship those).
SAMPLES: list[dict] = [
    {
        "seq_no": 35,
        "year": 2024,
        "type": "EA",
        "subtype": "korraline",
        "visit_date": date(2024, 8, 14),
        "address": "Savi 10, Narva linn, Ida-Viru maakond",
        "kataster_no": "51101:001:0035",
        "ehr_code": "104015350",
        "use_purpose": "üksikelamu",
        "year_built": 1962,
        "findings": [
            ("6.1", "info",
             "- Vundament — välispind nähtav osaliselt; pinnasniiskuse jäljed sokli alaosas."),
            ("8.7", "nonconf_minor",
             "- Akende tihendid — vananenud, jahedaste ilmadega tunda tõmbe."),
        ],
    },
    {
        "seq_no": 32,
        "year": 2025,
        "type": "EA",
        "subtype": "erakorraline",
        "visit_date": date(2025, 12, 25),
        "address": "Pribrežnõi tee veetorustik, Narva-Jõesuu linn, Ida-Viru maakond",
        "kataster_no": "85101:003:0210",
        "ehr_code": None,
        "use_purpose": "veerajatis",
        "year_built": 1985,
        "findings": [
            ("11.2", "nonconf_major",
             "- Veetorustiku läbiviigu lekkekohad — pinnaseelt nähtav niiskuse koondumine."),
        ],
    },
    {
        "seq_no": 19,
        "year": 2025,
        "type": "TJ",
        "subtype": "kasutuseelne",
        "visit_date": date(2025, 2, 19),
        "address": "Oru 24, Narva linn, Ida-Viru maakond",
        "kataster_no": "51101:020:0024",
        "ehr_code": "104215080",
        "use_purpose": "kahe korteriga elamu",
        "year_built": 1958,
        "findings": [
            ("6.4", "info",
             "- Katus — eterniitkate, üksikud praod nähtavad räästa lähedal."),
            ("12.1", "nonconf_minor",
             "- Korstna pealmine osa — nõrgalt vuugitud, vajab tihendamist enne uut kütteperioodi."),
        ],
    },
    {
        "seq_no": 18,
        "year": 2025,
        "type": "TJ",
        "subtype": "kasutuseelne",
        "visit_date": date(2025, 6, 18),
        "address": "Noo 43, Narva linn, Ida-Viru maakond",
        "kataster_no": "51101:022:0043",
        "ehr_code": "104221140",
        "use_purpose": "üksikelamu",
        "year_built": 1971,
        "findings": [
            ("8.7", "info",
             "- Aknad — uued PVC, paigaldus kvaliteetne, tihendid puhtad."),
            ("9.3", "nonconf_minor",
             "- Vannitoa põranda kalle — minimaalne, vee äravool ahtaks läinud."),
        ],
    },
    {
        "seq_no": 1,
        "year": 2026,
        "type": "EP",
        "subtype": "korraline",
        "visit_date": date(2026, 1, 20),
        "address": "Energeetik 2 AÜ 74, Narva-Jõesuu linn, Ida-Viru maakond",
        "kataster_no": "85101:004:0074",
        "ehr_code": "104310120",
        "use_purpose": "suvila",
        "year_built": 1989,
        "findings": [
            ("6.1", "info",
             "- Aiakrundi piires üldine seisukord rahuldav; eraldi kõrvalhoone vajab eraldi auditit."),
        ],
    },
    {
        "seq_no": 15,
        "year": 2025,
        "type": "TP",
        "subtype": "kasutuseelne",
        "visit_date": date(2025, 5, 20),
        "address": "Kajaka 8, Sillamäe linn, Ida-Viru maakond",
        "kataster_no": "73501:008:0008",
        "ehr_code": "104511220",
        "use_purpose": "kaubandus-teenindushoone",
        "year_built": 2007,
        "findings": [
            ("7.2", "info",
             "- Fassaad — kompositmaterial, mehaanilisi vigastusi ei tuvastatud."),
            ("10.4", "nonconf_minor",
             "- Tuletõkkesektsioon serveriruumi uksel — uksesulgur defektne, ei sulgu täielikult."),
        ],
    },
    {
        "seq_no": 10,
        "year": 2025,
        "type": "TJ",
        "subtype": "kasutuseelne",
        "visit_date": date(2025, 8, 10),
        "address": "Auga 8, Narva-Jõesuu linn, Ida-Viru maakond",
        "kataster_no": "85101:004:0020",
        "ehr_code": "104612330",
        "use_purpose": "üksikelamu",
        "year_built": 1996,
        "findings": [
            ("6.1", "info",
             "- Vundament — visuaalne kontroll; pragu sokli edelaservas, laius ~0.5 mm."),
            ("8.5", "nonconf_minor",
             "- Räästa- ja vihmaveesüsteem — paigaldatud, kuid sademevee suunamine eemale puudub."),
        ],
    },
]


def _make_audit(s: dict) -> Audit:
    return Audit(
        seq_no=s["seq_no"],
        year=s["year"],
        type=s["type"],
        subtype=s["subtype"],
        visit_date=s["visit_date"],
        purpose=(
            "Auditeerimise eesmärk — hinnata ehitise tehnilist seisukorda "
            "ja nõuetekohasust kasutuselevõtuks / korralise ülevaatuse jaoks. "
            "(Sample draft, körpus filename: see `audit/`.)"
        ),
        scope=(
            "Auditeerimisel vaadatakse üle olemasolevad ehituspaberid, "
            "tehakse visuaalne ülevaatus väljast ja seest, "
            "fikseeritakse rikked ja kõrvalekalded standarditest."
        ),
        composer=_composer(),
        reviewer=_reviewer(),
        building=Building(
            address=s["address"],
            kataster_no=s.get("kataster_no"),
            ehr_code=s.get("ehr_code"),
            use_purpose=s.get("use_purpose"),
            construction_year=s.get("year_built"),
        ),
        client=Client(name=""),
        findings=[
            Finding(section_ref=section_ref, severity=severity, observation_raw=text)
            for section_ref, severity, text in s["findings"]
        ],
        status="draft",
    )


def _existing_audit_id(seq_no: int, year: int, type_: str) -> int | None:
    with session_scope() as s:
        row = (
            s.query(AuditRow)
            .filter(
                AuditRow.seq_no == seq_no,
                AuditRow.year == year,
                AuditRow.type == type_,
            )
            .first()
        )
        return row.id if row else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-seed even when a sample with the same seq/year/type exists.",
    )
    args = parser.parse_args()

    created = 0
    skipped = 0
    replaced = 0
    for s in SAMPLES:
        existing = _existing_audit_id(s["seq_no"], s["year"], s["type"])
        if existing is not None:
            if not args.force:
                print(
                    f"  · skip  {s['type']} {s['seq_no']:03d}/{s['year']}  "
                    f"— audit_id={existing} already exists"
                )
                skipped += 1
                continue
            with session_scope() as sess:
                delete_audit(sess, existing)
            replaced += 1

        audit = _make_audit(s)
        with session_scope() as sess:
            new_id = save_audit(sess, audit)
        verb = "REPLACE" if existing is not None else "create"
        print(
            f"  ✓ {verb}  {s['type']} {s['seq_no']:03d}/{s['year']}  "
            f"— audit_id={new_id}  ({s['address']})"
        )
        created += 1

    print()
    print(f"Готово: создано {created}, заменено {replaced}, пропущено {skipped}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
