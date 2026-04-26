from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tadf.db.orm import Base
from tadf.db.repo import list_audits, load_audit, save_audit


def test_save_and_load(audit, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        aid = save_audit(s, audit)
        s.commit()
    with Session(engine) as s:
        loaded = load_audit(s, aid)
        assert loaded.composer.full_name == audit.composer.full_name
        assert loaded.reviewer.kutsetunnistus_no == audit.reviewer.kutsetunnistus_no
        assert loaded.building.ehr_code == audit.building.ehr_code
        assert len(loaded.findings) == len(audit.findings)
        section_refs = {f.section_ref for f in loaded.findings}
        assert "11" in section_refs
        assert "14" in section_refs

        all_audits = list_audits(s)
        assert len(all_audits) == 1
