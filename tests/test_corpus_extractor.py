"""Tests for tadf.llm.corpus_extractor — distillation of corpus sections.

The LLM call is monkeypatched so the tests run offline. We exercise the
deterministic parts (normalisation, idempotency, locked-section guard,
counter aggregation) end-to-end against a real SQLite file.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import tadf.llm.corpus_extractor as ce
from tadf.db.orm import Base, CorpusAuditRow, CorpusClauseRow, CorpusSectionRow

# ---------------------------------------------------------------------------
# Pure-Python helpers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "ref, locked",
    [
        ("11", True),
        ("11.1", True),
        ("14", True),
        ("14.3", True),
        ("6.1", False),
        ("8.7", False),
        (None, False),
    ],
)
def test_is_locked(ref, locked):
    assert ce._is_locked(ref) is locked


def test_normalise_clause_rejects_invalid_kind():
    assert ce._normalise_clause({"kind": "nonsense", "text": "x" * 30}) is None


def test_normalise_clause_rejects_short_text():
    assert ce._normalise_clause({"kind": "boilerplate", "text": "tiny"}) is None


def test_normalise_clause_clamps_reusability():
    out = ce._normalise_clause(
        {"kind": "boilerplate", "text": "a" * 50, "reusability": 12.0}
    )
    assert out["reusability"] == 1.0
    out2 = ce._normalise_clause(
        {"kind": "boilerplate", "text": "a" * 50, "reusability": -1.0}
    )
    assert out2["reusability"] == 0.0


def test_normalise_clause_drops_recommendation_for_non_finding():
    out = ce._normalise_clause(
        {
            "kind": "boilerplate",
            "text": "a" * 50,
            "recommendation": "should be discarded",
            "reusability": 0.7,
        }
    )
    assert out["recommendation"] is None


def test_normalise_clause_keeps_recommendation_for_finding():
    out = ce._normalise_clause(
        {
            "kind": "finding",
            "text": "Vundamendi pragu nähtav.",
            "recommendation": "Tihendada ja jälgida.",
            "reusability": 0.4,
        }
    )
    assert out["recommendation"] == "Tihendada ja jälgida."


def test_normalise_clause_handles_garbage_reusability():
    out = ce._normalise_clause(
        {"kind": "summary", "text": "a" * 50, "reusability": "not a number"}
    )
    assert out["reusability"] == 0.5


# ---------------------------------------------------------------------------
# DB-backed end-to-end with a faked LLM call
# ---------------------------------------------------------------------------

@pytest.fixture
def db_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/extractor.db")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def patch_session(monkeypatch, db_engine):
    class _Scope:
        def __enter__(self_inner):
            self_inner.s = Session(db_engine)
            return self_inner.s

        def __exit__(self_inner, *exc):
            self_inner.s.commit()
            self_inner.s.close()

    monkeypatch.setattr(ce, "session_scope", lambda: _Scope())
    return _Scope


def _seed_section(engine, *, section_ref="6.1", body="x" * 200):
    with Session(engine) as s:
        a = CorpusAuditRow(
            source_path="/tmp/x.docx",
            source_sha256="d" * 64,
            source_format="docx",
            filename="x.docx",
            subtype="erakorraline",
        )
        s.add(a)
        s.flush()
        sec = CorpusSectionRow(
            audit_id=a.id,
            raw_number="6.1",
            section_ref=section_ref,
            title="Vundament",
            body_text=body,
        )
        s.add(sec)
        s.commit()
        return a.id, sec.id


def _fake_llm(clauses):
    """Build a stub `complete_json` returning the given clause list."""
    return lambda **_: {"clauses": clauses}


def test_extract_section_inserts_rows(monkeypatch, db_engine, patch_session):
    audit_id, sec_id = _seed_section(db_engine)
    monkeypatch.setattr(
        ce,
        "complete_json",
        _fake_llm([
            {
                "kind": "boilerplate",
                "text": "Vundament on heas seisus, vastab nõuetele.",
                "recommendation": None,
                "reusability": 0.85,
            },
            {
                "kind": "finding",
                "text": "Pragu vundamendi loode nurgas, ~3 mm laiune.",
                "recommendation": "Jälgida 6 kuud, vajadusel tihendada.",
                "reusability": 0.4,
            },
            {
                "kind": "garbage",  # invalid kind — must be dropped
                "text": "should not be saved" * 5,
                "recommendation": None,
                "reusability": 0.9,
            },
        ]),
    )

    n = ce.extract_clauses_for_section(sec_id)
    assert n == 2  # garbage row was filtered out

    with Session(db_engine) as s:
        rows = (
            s.query(CorpusClauseRow)
            .filter(CorpusClauseRow.section_id == sec_id)
            .all()
        )
        assert len(rows) == 2
        kinds = {r.kind for r in rows}
        assert kinds == {"boilerplate", "finding"}
        finding = next(r for r in rows if r.kind == "finding")
        assert finding.recommendation == "Jälgida 6 kuud, vajadusel tihendada."


def test_extract_section_idempotent(monkeypatch, db_engine, patch_session):
    audit_id, sec_id = _seed_section(db_engine)
    monkeypatch.setattr(
        ce,
        "complete_json",
        _fake_llm([
            {
                "kind": "boilerplate",
                "text": "x" * 80,
                "recommendation": None,
                "reusability": 0.7,
            }
        ]),
    )
    assert ce.extract_clauses_for_section(sec_id) == 1
    # Re-running is a no-op
    assert ce.extract_clauses_for_section(sec_id) == 0
    with Session(db_engine) as s:
        assert s.query(CorpusClauseRow).count() == 1


def test_extract_section_force_replaces(monkeypatch, db_engine, patch_session):
    audit_id, sec_id = _seed_section(db_engine)
    monkeypatch.setattr(
        ce,
        "complete_json",
        _fake_llm([
            {
                "kind": "boilerplate",
                "text": "x" * 80,
                "recommendation": None,
                "reusability": 0.7,
            }
        ]),
    )
    ce.extract_clauses_for_section(sec_id)
    monkeypatch.setattr(
        ce,
        "complete_json",
        _fake_llm([
            {
                "kind": "summary",
                "text": "y" * 80,
                "recommendation": None,
                "reusability": 0.2,
            },
            {
                "kind": "summary",
                "text": "z" * 80,
                "recommendation": None,
                "reusability": 0.2,
            },
        ]),
    )
    n = ce.extract_clauses_for_section(sec_id, force=True)
    assert n == 2
    with Session(db_engine) as s:
        rows = s.query(CorpusClauseRow).all()
        assert len(rows) == 2
        assert {r.kind for r in rows} == {"summary"}


def test_extract_section_skips_locked(monkeypatch, db_engine, patch_session):
    """Sections 11 and 14 must never reach the LLM; calling the function on
    them returns 0 without invoking complete_json."""
    audit_id, sec_id = _seed_section(db_engine, section_ref="11.1")
    called = []

    def _spy(**kwargs):
        called.append(kwargs)
        return {"clauses": []}

    monkeypatch.setattr(ce, "complete_json", _spy)
    assert ce.extract_clauses_for_section(sec_id) == 0
    assert called == []


def test_extract_section_skips_short_body(monkeypatch, db_engine, patch_session):
    audit_id, sec_id = _seed_section(db_engine, body="too short")
    called = []
    monkeypatch.setattr(ce, "complete_json", lambda **k: called.append(k))
    assert ce.extract_clauses_for_section(sec_id) == 0
    assert called == []


def test_extract_audit_aggregates_counters(monkeypatch, db_engine, patch_session):
    """A 3-section audit: one normal, one locked (11), one tiny — expect
    1 processed, 1 skipped_locked, 1 skipped_short."""
    with Session(db_engine) as s:
        a = CorpusAuditRow(
            source_path="/tmp/y.docx",
            source_sha256="e" * 64,
            source_format="docx",
            filename="y.docx",
            subtype="kasutuseelne",
        )
        s.add(a)
        s.flush()
        s.add_all([
            CorpusSectionRow(
                audit_id=a.id, raw_number="6.1", section_ref="6.1",
                title="Vundament", body_text="x" * 200,
            ),
            CorpusSectionRow(
                audit_id=a.id, raw_number="11", section_ref="11",
                title="Kokkuvõte", body_text="x" * 200,
            ),
            CorpusSectionRow(
                audit_id=a.id, raw_number="6.5", section_ref="6.5",
                title="Katus", body_text="too short",
            ),
        ])
        s.commit()
        audit_id = a.id

    monkeypatch.setattr(
        ce,
        "complete_json",
        _fake_llm([
            {
                "kind": "boilerplate",
                "text": "x" * 80,
                "recommendation": None,
                "reusability": 0.8,
            }
        ]),
    )
    counts = ce.extract_clauses_for_audit(audit_id)
    assert counts == {
        "sections_processed": 1,
        "clauses_inserted": 1,
        "skipped_locked": 1,
        "skipped_short": 1,
    }


def test_has_extracted_reflects_db_state(monkeypatch, db_engine, patch_session):
    audit_id, sec_id = _seed_section(db_engine)
    assert ce.has_extracted(audit_id) is False
    monkeypatch.setattr(
        ce,
        "complete_json",
        _fake_llm([
            {
                "kind": "boilerplate",
                "text": "x" * 80,
                "recommendation": None,
                "reusability": 0.7,
            }
        ]),
    )
    ce.extract_clauses_for_section(sec_id)
    assert ce.has_extracted(audit_id) is True
