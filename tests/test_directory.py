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
