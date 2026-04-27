"""Lookup helpers backing the «Новый аудит» autofill feature."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import tadf.db.session as session_module
from tadf.db.lookups import (
    latest_auditor_by_name,
    latest_client_by_name,
    latest_footer_override,
    latest_header_override,
)
from tadf.db.orm import Base
from tadf.db.repo import save_audit, upsert_audit


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Replace the module-level engine + session_scope's binding with a
    per-test SQLite so the lookup helpers (which use the live module
    state) operate on a clean DB."""
    engine = create_engine(f"sqlite:///{tmp_path / 'lookup.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(session_module, "_engine", engine)
    monkeypatch.setattr(
        session_module,
        "_SessionLocal",
        session_module.sessionmaker(bind=engine, autoflush=False, expire_on_commit=False),
    )
    monkeypatch.setattr(session_module, "_initialised", True)
    return engine


def test_latest_auditor_by_name_returns_none_for_empty(isolated_db, audit) -> None:
    assert latest_auditor_by_name("") is None
    assert latest_auditor_by_name(None) is None
    assert latest_auditor_by_name("   ") is None


def test_latest_auditor_by_name_returns_full_record(isolated_db, audit) -> None:
    with Session(isolated_db) as s:
        save_audit(s, audit)
        s.commit()
    rec = latest_auditor_by_name(audit.reviewer.full_name)
    assert rec is not None
    assert rec["full_name"] == audit.reviewer.full_name
    assert rec["kutsetunnistus_no"] == audit.reviewer.kutsetunnistus_no
    assert rec["qualification"] == audit.reviewer.qualification


def test_latest_auditor_picks_most_recent_row(isolated_db, audit) -> None:
    """Two saves with the same name → newest record wins (id desc)."""
    name = audit.reviewer.full_name
    with Session(isolated_db) as s:
        # First save: qualification A
        audit.id = None
        audit.reviewer.qualification = "Qual A"
        save_audit(s, audit)
        s.commit()
        # Second save: qualification B
        audit.id = None
        audit.reviewer.qualification = "Qual B"
        save_audit(s, audit)
        s.commit()
    rec = latest_auditor_by_name(name)
    assert rec is not None
    assert rec["qualification"] == "Qual B"


def test_latest_client_by_name_round_trip(isolated_db, audit) -> None:
    with Session(isolated_db) as s:
        save_audit(s, audit)
        s.commit()
    rec = latest_client_by_name(audit.client.name)
    assert rec is not None
    assert rec["name"] == audit.client.name


def test_latest_header_override_skips_excluded_audit(isolated_db, audit) -> None:
    audit.header_override = "Custom HEADER text"
    audit.footer_override = "Custom FOOTER text"
    with Session(isolated_db) as s:
        aid = upsert_audit(s, audit)
        s.commit()
    # No exclude → should see this draft's override
    assert latest_header_override() == "Custom HEADER text"
    assert latest_footer_override() == "Custom FOOTER text"
    # Excluding the only draft → no override available, returns None
    assert latest_header_override(exclude_audit_id=aid) is None
    assert latest_footer_override(exclude_audit_id=aid) is None


def test_latest_header_override_ignores_null_values(isolated_db, audit) -> None:
    """Drafts without a header override should not surface as the «latest»."""
    audit.header_override = None
    audit.footer_override = None
    with Session(isolated_db) as s:
        save_audit(s, audit)
        s.commit()
    assert latest_header_override() is None
    assert latest_footer_override() is None
