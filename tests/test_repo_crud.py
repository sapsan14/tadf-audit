from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tadf.db.orm import AuditorRow, AuditRow, Base, BuildingRow
from tadf.db.repo import (
    delete_audit,
    list_audits,
    list_drafts,
    load_audit,
    save_audit,
    upsert_audit,
)
from tadf.models import Finding


def _engine(tmp_path):
    e = create_engine(f"sqlite:///{tmp_path / 'crud.db'}")
    Base.metadata.create_all(e)
    return e


def test_list_drafts_filters_by_status(audit, tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        a1 = save_audit(s, audit)
        s.commit()
        s.get(AuditRow, a1).status = "submitted"
        s.commit()

        # Second one stays default ("draft")
        a2 = save_audit(s, audit)
        s.commit()

    with Session(engine) as s:
        drafts = list_drafts(s)
        assert {d.id for d in drafts} == {a2}
        assert len(list_audits(s)) == 2


def test_upsert_inserts_when_id_none(audit, tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        aid = upsert_audit(s, audit)
        s.commit()
        assert aid is not None
        assert audit.id == aid

    with Session(engine) as s:
        assert len(list_audits(s)) == 1


def test_upsert_updates_in_place(audit, tmp_path):
    """Repeated upsert must not create duplicates and must mutate in place."""
    engine = _engine(tmp_path)
    with Session(engine) as s:
        aid = upsert_audit(s, audit)
        s.commit()
        composer_id_before = s.get(AuditRow, aid).composer_id
        building_id_before = s.get(AuditRow, aid).building_id

    audit.purpose = "Uus eesmärk pärast värskendust."
    audit.building.address = "New address"
    audit.findings.append(Finding(section_ref="6.2", observation_raw="Updated finding."))

    with Session(engine) as s:
        aid2 = upsert_audit(s, audit)
        s.commit()
        assert aid2 == aid
        # No duplicate Auditor/Building rows.
        assert s.query(AuditorRow).count() == 2  # composer + reviewer
        assert s.query(BuildingRow).count() == 1
        assert s.query(AuditRow).count() == 1
        # IDs preserved.
        row = s.get(AuditRow, aid)
        assert row.composer_id == composer_id_before
        assert row.building_id == building_id_before
        assert row.purpose == "Uus eesmärk pärast värskendust."
        assert row.building.address == "New address"
        # Findings replaced wholesale.
        assert len(row.findings) == len(audit.findings)


def test_upsert_with_stale_id_falls_back_to_insert(audit, tmp_path):
    engine = _engine(tmp_path)
    audit.id = 9999  # never persisted
    with Session(engine) as s:
        aid = upsert_audit(s, audit)
        s.commit()
        assert aid != 9999
        assert s.get(AuditRow, aid) is not None


def test_delete_audit_cascades_findings_and_photos(audit, tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        aid = save_audit(s, audit)
        s.commit()
        assert s.get(AuditRow, aid) is not None
        assert s.query(AuditRow).count() == 1

    with Session(engine) as s:
        delete_audit(s, aid)
        s.commit()
        assert s.get(AuditRow, aid) is None
        assert list_audits(s) == []
        # Auditor/Building rows are intentionally preserved across deletes.
        assert s.query(AuditorRow).count() == 2
        assert s.query(BuildingRow).count() == 1


def test_delete_missing_id_is_noop(audit, tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as s:
        delete_audit(s, 12345)
        s.commit()  # must not raise
