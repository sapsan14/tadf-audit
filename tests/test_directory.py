"""Tests for the directory tables and the upsert / delete repo helpers.

Covers:
  - upsert is keyed by name and idempotent (typing the same name twice
    does NOT create two rows; second pass updates sibling fields)
  - delete returns False for missing entries and True for existing
  - save_audit / upsert_audit auto-mirror to the directory
  - lookups read from the directory (so a deleted entry no longer
    surfaces as a suggestion)
  - backfill is one-shot and idempotent
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import tadf.db.session as session_mod
from tadf.db import lookups as lookups_mod
from tadf.db.orm import (
    Base,
    DirectoryAuditorRow,
    DirectoryBuilderRow,
    DirectoryClientRow,
    DirectoryDesignerRow,
    DirectoryUsePurposeRow,
)
from tadf.db.repo import (
    backfill_directory,
    delete_directory_auditor,
    delete_directory_builder,
    delete_directory_client,
    delete_directory_designer,
    delete_directory_use_purpose,
    save_audit,
    upsert_audit,
    upsert_directory_auditor,
    upsert_directory_builder,
    upsert_directory_client,
    upsert_directory_designer,
    upsert_directory_use_purpose,
)
from tadf.models import Audit, Auditor, Building, Client, Finding


@pytest.fixture
def db_engine(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/dir.db")
    Base.metadata.create_all(engine)

    class _Scope:
        def __enter__(self_inner):
            self_inner.s = Session(engine)
            return self_inner.s

        def __exit__(self_inner, exc_type, *_):
            if exc_type is None:
                self_inner.s.commit()
            else:
                self_inner.s.rollback()
            self_inner.s.close()

    # `lookups` calls session_scope to open its own short-lived sessions.
    # `repo` operates on Sessions passed in by callers — no patching needed.
    monkeypatch.setattr(session_mod, "session_scope", lambda: _Scope())
    monkeypatch.setattr(lookups_mod, "session_scope", lambda: _Scope())
    return engine


def _build_minimal_audit(**overrides) -> Audit:
    return Audit(
        seq_no=1,
        year=2026,
        type="EA",
        subtype="erakorraline",
        visit_date=date(2026, 4, 27),
        purpose="Test",
        scope="Test",
        composer=Auditor(full_name="Aleksei Sholokhov", company="UNTWERP OÜ"),
        reviewer=Auditor(
            full_name="Fjodor Sokolov",
            kutsetunnistus_no="148515",
            qualification="Diplomeeritud insener tase 7",
        ),
        building=Building(
            address="Auga 8 Narva-Jõesuu",
            ehr_code="111111111",
            kataster_no="51001:001:0001",
            footprint_m2=80.0,
            volume_m3=240.0,
            storeys_above=2,
            storeys_below=0,
            fire_class="TP-3",
            use_purpose="aiamaja",
            designer="ABC Project OÜ",
            builder="ABC Build OÜ",
        ),
        client=Client(name="Acme OÜ", reg_code="12345678"),
        findings=[
            Finding(section_ref="6.1", observation_raw="OK"),
            Finding(section_ref="11", observation_raw="Cover-only required by §5"),
            Finding(section_ref="14", observation_raw="Final assessment"),
        ],
        **overrides,
    )


# ---------------------------------------------------------------------------
# upsert is keyed by name (idempotent)
# ---------------------------------------------------------------------------

def test_upsert_directory_auditor_idempotent(db_engine):
    with Session(db_engine) as s:
        upsert_directory_auditor(s, Auditor(full_name="Anton", kutsetunnistus_no="111"))
        upsert_directory_auditor(s, Auditor(full_name="Anton", kutsetunnistus_no="222"))
        s.commit()
    with Session(db_engine) as s:
        rows = s.query(DirectoryAuditorRow).all()
    assert len(rows) == 1
    # Latest write wins — sibling field updated in place.
    assert rows[0].kutsetunnistus_no == "222"


def test_upsert_skips_empty_name(db_engine):
    with Session(db_engine) as s:
        upsert_directory_auditor(s, Auditor(full_name="   "))
        upsert_directory_auditor(s, Auditor(full_name=""))
        s.commit()
    with Session(db_engine) as s:
        assert s.query(DirectoryAuditorRow).count() == 0


def test_upsert_directory_client_idempotent(db_engine):
    with Session(db_engine) as s:
        upsert_directory_client(s, Client(name="Acme", reg_code="111"))
        upsert_directory_client(s, Client(name="Acme", reg_code="222"))
        s.commit()
    with Session(db_engine) as s:
        rows = s.query(DirectoryClientRow).all()
    assert len(rows) == 1 and rows[0].reg_code == "222"


def test_upsert_does_not_blank_existing_fields_with_none(db_engine):
    """Directory accumulates data: subsequent upserts that omit a field
    must preserve the previously-populated value. Without this, opening
    an old audit (which has a partially-filled auditor) and re-saving
    would silently wipe whatever the user typed in the «🗂 Справочник»
    edit form (or in a different audit)."""
    with Session(db_engine) as s:
        upsert_directory_auditor(
            s,
            Auditor(
                full_name="Anton",
                kutsetunnistus_no="111",
                qualification="Diplomeeritud",
                company="Acme OÜ",
                company_reg_nr="12345678",
            ),
        )
        s.commit()
    # Re-upsert with only the name + a new company — other fields None.
    with Session(db_engine) as s:
        upsert_directory_auditor(s, Auditor(full_name="Anton", company="New Co"))
        s.commit()
    with Session(db_engine) as s:
        row = s.query(DirectoryAuditorRow).one()
        assert row.full_name == "Anton"
        assert row.company == "New Co"  # explicitly set → updated
        assert row.kutsetunnistus_no == "111"  # PRESERVED
        assert row.qualification == "Diplomeeritud"  # PRESERVED
        assert row.company_reg_nr == "12345678"  # PRESERVED


def test_upsert_client_does_not_blank_with_none(db_engine):
    with Session(db_engine) as s:
        upsert_directory_client(
            s,
            Client(
                name="Acme",
                reg_code="111",
                contact_email="a@example.com",
                address="Tartu mnt 84a",
            ),
        )
        s.commit()
    with Session(db_engine) as s:
        upsert_directory_client(s, Client(name="Acme", contact_phone="+372 555 0000"))
        s.commit()
    with Session(db_engine) as s:
        row = s.query(DirectoryClientRow).one()
        assert row.reg_code == "111"  # preserved
        assert row.contact_email == "a@example.com"  # preserved
        assert row.address == "Tartu mnt 84a"  # preserved
        assert row.contact_phone == "+372 555 0000"  # newly added


def test_upsert_simple_designer_idempotent(db_engine):
    with Session(db_engine) as s:
        upsert_directory_designer(s, "Bureau OÜ")
        upsert_directory_designer(s, "Bureau OÜ")
        upsert_directory_designer(s, "Bureau OÜ ")  # whitespace stripped
        s.commit()
    with Session(db_engine) as s:
        assert s.query(DirectoryDesignerRow).count() == 1


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

def test_delete_returns_true_when_present_false_when_missing(db_engine):
    with Session(db_engine) as s:
        upsert_directory_auditor(s, Auditor(full_name="Anton"))
        s.commit()
    with Session(db_engine) as s:
        assert delete_directory_auditor(s, "Anton") is True
        s.commit()
    with Session(db_engine) as s:
        assert delete_directory_auditor(s, "Anton") is False


@pytest.mark.parametrize(
    "name, model, delete_fn, upsert_fn, upsert_arg",
    [
        ("Anton", DirectoryAuditorRow, delete_directory_auditor,
         upsert_directory_auditor, lambda: Auditor(full_name="Anton")),
        ("Acme", DirectoryClientRow, delete_directory_client,
         upsert_directory_client, lambda: Client(name="Acme")),
        ("Bureau OÜ", DirectoryDesignerRow, delete_directory_designer,
         upsert_directory_designer, lambda: "Bureau OÜ"),
        ("Build OÜ", DirectoryBuilderRow, delete_directory_builder,
         upsert_directory_builder, lambda: "Build OÜ"),
        ("aiamaja", DirectoryUsePurposeRow, delete_directory_use_purpose,
         upsert_directory_use_purpose, lambda: "aiamaja"),
    ],
)
def test_delete_round_trips_for_every_directory(
    db_engine, name, model, delete_fn, upsert_fn, upsert_arg
):
    with Session(db_engine) as s:
        upsert_fn(s, upsert_arg())
        s.commit()
    with Session(db_engine) as s:
        assert s.query(model).count() == 1
        assert delete_fn(s, name) is True
        s.commit()
    with Session(db_engine) as s:
        assert s.query(model).count() == 0


# ---------------------------------------------------------------------------
# save_audit / upsert_audit auto-mirror
# ---------------------------------------------------------------------------

def test_mirror_picks_more_complete_record_when_composer_reviewer_share_name(db_engine):
    """Real-world bug: the user typed «Anton Sokolov» in BOTH composer
    (with kutsetunnistus 000000 + company Anthemion) and reviewer (with
    kutsetunnistus 148515 + company TADF Ehitus OÜ). The directory ended
    up with reviewer's data because both upserts ran and the second
    silently overwrote the first.

    Fix: detect the same-name collision in `_mirror_to_directory` and
    keep only the side with more populated sibling fields.
    """
    audit = _build_minimal_audit()
    # Composer: 5 filled fields (kutsetunnistus, qual, company, reg_nr, id_code).
    audit.composer = Auditor(
        full_name="Anton Sokolov",
        kutsetunnistus_no="000000",
        qualification="Diplomeeritud insener tase 7",
        company="Anthemion",
        company_reg_nr="00000000",
        id_code="38001011234",
    )
    # Reviewer: 3 filled fields.
    audit.reviewer = Auditor(
        full_name="Anton Sokolov",
        kutsetunnistus_no="148515",
        qualification="Diplomeeritud insener tase 7",
        company="TADF Ehitus OÜ",
    )
    with Session(db_engine) as s:
        save_audit(s, audit)
        s.commit()
    with Session(db_engine) as s:
        rows = s.query(DirectoryAuditorRow).all()
        assert len(rows) == 1, "exactly one Anton Sokolov record (no collision)"
        anton = rows[0]
        # Composer has more filled fields → composer's data wins.
        assert anton.kutsetunnistus_no == "000000"
        assert anton.company == "Anthemion"
        assert anton.company_reg_nr == "00000000"
        assert anton.id_code == "38001011234"


def test_mirror_picks_reviewer_when_collision_and_reviewer_more_complete(db_engine):
    audit = _build_minimal_audit()
    audit.composer = Auditor(full_name="Boris", company="Just Co")  # 1 sibling field
    audit.reviewer = Auditor(
        full_name="Boris",
        kutsetunnistus_no="999",
        qualification="Diplomeeritud",
        company="Real OÜ",
        company_reg_nr="11111111",
    )  # 4 sibling fields
    with Session(db_engine) as s:
        save_audit(s, audit)
        s.commit()
    with Session(db_engine) as s:
        rows = s.query(DirectoryAuditorRow).all()
        assert len(rows) == 1
        boris = rows[0]
        assert boris.kutsetunnistus_no == "999"
        assert boris.company == "Real OÜ"
        assert boris.company_reg_nr == "11111111"


def test_mirror_keeps_distinct_records_when_names_differ(db_engine):
    """Different names → both entries kept (the original behaviour)."""
    audit = _build_minimal_audit()
    audit.composer = Auditor(full_name="Anna", kutsetunnistus_no="111")
    audit.reviewer = Auditor(full_name="Boris", kutsetunnistus_no="222")
    with Session(db_engine) as s:
        save_audit(s, audit)
        s.commit()
    with Session(db_engine) as s:
        rows = {r.full_name: r for r in s.query(DirectoryAuditorRow).all()}
        assert set(rows) == {"Anna", "Boris"}
        assert rows["Anna"].kutsetunnistus_no == "111"
        assert rows["Boris"].kutsetunnistus_no == "222"


def test_save_audit_mirrors_to_all_directories(db_engine):
    audit = _build_minimal_audit()
    with Session(db_engine) as s:
        save_audit(s, audit)
        s.commit()
    with Session(db_engine) as s:
        # composer + reviewer
        names = {r.full_name for r in s.query(DirectoryAuditorRow).all()}
        assert names == {"Aleksei Sholokhov", "Fjodor Sokolov"}
        # client
        assert {r.name for r in s.query(DirectoryClientRow).all()} == {"Acme OÜ"}
        # designer + builder + use_purpose
        assert {r.name for r in s.query(DirectoryDesignerRow).all()} == {"ABC Project OÜ"}
        assert {r.name for r in s.query(DirectoryBuilderRow).all()} == {"ABC Build OÜ"}
        assert {r.value for r in s.query(DirectoryUsePurposeRow).all()} == {"aiamaja"}


def test_upsert_audit_updates_directory(db_engine):
    """If the auditor edits the kutsetunnistus on an existing draft, the
    directory entry for that name gets the new value — same name, latest
    wins."""
    audit = _build_minimal_audit()
    with Session(db_engine) as s:
        save_audit(s, audit)
        s.commit()
    audit.reviewer.kutsetunnistus_no = "999999"
    with Session(db_engine) as s:
        upsert_audit(s, audit)
        s.commit()
    with Session(db_engine) as s:
        row = s.query(DirectoryAuditorRow).filter_by(full_name="Fjodor Sokolov").one()
        assert row.kutsetunnistus_no == "999999"


# ---------------------------------------------------------------------------
# Lookups read from the directory
# ---------------------------------------------------------------------------

def test_composer_names_reads_from_directory(db_engine):
    with Session(db_engine) as s:
        upsert_directory_auditor(s, Auditor(full_name="Boris"))
        upsert_directory_auditor(s, Auditor(full_name="Anton"))
        s.commit()
    assert lookups_mod.composer_names() == ["Anton", "Boris"]


def test_deleted_entry_disappears_from_suggestions(db_engine):
    with Session(db_engine) as s:
        upsert_directory_auditor(s, Auditor(full_name="Boris"))
        s.commit()
    assert lookups_mod.composer_names() == ["Boris"]
    with Session(db_engine) as s:
        delete_directory_auditor(s, "Boris")
        s.commit()
    assert lookups_mod.composer_names() == []


def test_latest_auditor_by_name_pulls_directory(db_engine):
    with Session(db_engine) as s:
        upsert_directory_auditor(
            s,
            Auditor(
                full_name="Fjodor Sokolov",
                kutsetunnistus_no="148515",
                qualification="Diplomeeritud insener tase 7",
            ),
        )
        s.commit()
    out = lookups_mod.latest_auditor_by_name("Fjodor Sokolov")
    assert out["kutsetunnistus_no"] == "148515"
    assert out["qualification"] == "Diplomeeritud insener tase 7"


def test_latest_auditor_returns_none_after_delete(db_engine):
    with Session(db_engine) as s:
        upsert_directory_auditor(s, Auditor(full_name="Boris"))
        s.commit()
    with Session(db_engine) as s:
        delete_directory_auditor(s, "Boris")
        s.commit()
    assert lookups_mod.latest_auditor_by_name("Boris") is None


# ---------------------------------------------------------------------------
# Backfill is idempotent
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# update_directory_*
# ---------------------------------------------------------------------------

from tadf.db.repo import (  # noqa: E402
    update_directory_auditor,
    update_directory_builder,
    update_directory_client,
    update_directory_designer,
    update_directory_use_purpose,
)


def test_update_directory_auditor_changes_fields_in_place(db_engine):
    with Session(db_engine) as s:
        upsert_directory_auditor(
            s,
            Auditor(
                full_name="Anton",
                kutsetunnistus_no="111",
                qualification="Old",
                company="Old Co",
            ),
        )
        s.commit()
    with Session(db_engine) as s:
        row = s.query(DirectoryAuditorRow).one()
        update_directory_auditor(
            s,
            row_id=row.id,
            full_name="Anton Sokolov",
            kutsetunnistus_no="222",
            qualification="New",
            company="New Co",
            company_reg_nr="12345678",
        )
        s.commit()
    with Session(db_engine) as s:
        row = s.query(DirectoryAuditorRow).one()
        assert row.full_name == "Anton Sokolov"
        assert row.kutsetunnistus_no == "222"
        assert row.qualification == "New"
        assert row.company == "New Co"
        assert row.company_reg_nr == "12345678"


def test_update_returns_false_when_row_missing(db_engine):
    with Session(db_engine) as s:
        assert update_directory_auditor(s, row_id=9999, full_name="Whatever") is False


def test_update_rejects_empty_name(db_engine):
    with Session(db_engine) as s:
        upsert_directory_auditor(s, Auditor(full_name="Anton"))
        s.commit()
    with Session(db_engine) as s:
        row = s.query(DirectoryAuditorRow).one()
        with pytest.raises(ValueError, match="не может быть пустым"):
            update_directory_auditor(s, row_id=row.id, full_name="")


def test_update_rejects_name_clash(db_engine):
    with Session(db_engine) as s:
        upsert_directory_auditor(s, Auditor(full_name="Anton"))
        upsert_directory_auditor(s, Auditor(full_name="Boris"))
        s.commit()
    with Session(db_engine) as s:
        boris = (
            s.query(DirectoryAuditorRow)
            .filter_by(full_name="Boris")
            .one()
        )
        with pytest.raises(ValueError, match="уже занято"):
            update_directory_auditor(s, row_id=boris.id, full_name="Anton")


def test_update_directory_client_full_round_trip(db_engine):
    with Session(db_engine) as s:
        upsert_directory_client(s, Client(name="Acme", reg_code="111"))
        s.commit()
    with Session(db_engine) as s:
        row = s.query(DirectoryClientRow).one()
        update_directory_client(
            s,
            row_id=row.id,
            name="Acme Updated",
            reg_code="222",
            contact_email="hello@example.com",
            contact_phone="+372 555 0000",
            address="Tartu mnt 84a, Tallinn",
        )
        s.commit()
    with Session(db_engine) as s:
        row = s.query(DirectoryClientRow).one()
        assert row.name == "Acme Updated"
        assert row.reg_code == "222"
        assert row.contact_email == "hello@example.com"
        assert row.address == "Tartu mnt 84a, Tallinn"


def test_update_designer_and_builder(db_engine):
    with Session(db_engine) as s:
        upsert_directory_designer(s, "Bureau OÜ")
        upsert_directory_builder(s, "Build OÜ")
        s.commit()
    with Session(db_engine) as s:
        d = s.query(DirectoryDesignerRow).one()
        b = s.query(DirectoryBuilderRow).one()
        update_directory_designer(
            s, row_id=d.id, name="Bureau Updated OÜ", reg_code="11111111"
        )
        update_directory_builder(
            s, row_id=b.id, name="Build Updated OÜ", reg_code="22222222"
        )
        s.commit()
    with Session(db_engine) as s:
        assert s.query(DirectoryDesignerRow).one().name == "Bureau Updated OÜ"
        assert s.query(DirectoryDesignerRow).one().reg_code == "11111111"
        assert s.query(DirectoryBuilderRow).one().name == "Build Updated OÜ"


def test_update_use_purpose(db_engine):
    with Session(db_engine) as s:
        upsert_directory_use_purpose(s, "aiamaja")
        s.commit()
    with Session(db_engine) as s:
        row = s.query(DirectoryUsePurposeRow).one()
        update_directory_use_purpose(s, row_id=row.id, value="elumaja")
        s.commit()
    with Session(db_engine) as s:
        assert s.query(DirectoryUsePurposeRow).one().value == "elumaja"


# ---------------------------------------------------------------------------
# Backfill is idempotent
# ---------------------------------------------------------------------------


def test_backfill_is_idempotent(db_engine):
    audit = _build_minimal_audit()
    with Session(db_engine) as s:
        save_audit(s, audit)
        s.commit()
    # First call adds nothing new (entries are already there from save_audit).
    with Session(db_engine) as s:
        before = s.query(DirectoryAuditorRow).count()
        counts = backfill_directory(s)
        s.commit()
        after = s.query(DirectoryAuditorRow).count()
    assert after == before
    assert counts["auditor"] == 0  # all already mirrored

    # Even calling backfill twice is a no-op.
    with Session(db_engine) as s:
        counts2 = backfill_directory(s)
        s.commit()
    assert counts2["auditor"] == 0
