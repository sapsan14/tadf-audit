"""Tests for tadf.llm.fewshot — corpus-driven retrieval for in-context examples.

Uses an isolated temporary SQLite DB seeded with synthetic corpus rows so we
don't depend on the real corpus being parseable.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import tadf.llm.fewshot as fewshot
from tadf.db.orm import Base, CorpusAuditRow, CorpusClauseRow, CorpusSectionRow
from tadf.llm.fewshot import _is_locked, _trim, examples_for, format_for_prompt


def _seed(engine):
    """Three audits, two subtypes, five sections: 6.1 (×2 different subtypes),
    6.2, 8.7 (locked-adjacent neighbour), 14.1 (locked)."""
    with Session(engine) as s:
        a_era = CorpusAuditRow(
            source_path="/tmp/era.docx",
            source_sha256="a" * 64,
            source_format="docx",
            filename="era.docx",
            subtype="erakorraline",
        )
        a_kas = CorpusAuditRow(
            source_path="/tmp/kas.docx",
            source_sha256="b" * 64,
            source_format="docx",
            filename="kas.docx",
            subtype="kasutuseelne",
        )
        a_none = CorpusAuditRow(
            source_path="/tmp/none.docx",
            source_sha256="c" * 64,
            source_format="docx",
            filename="none.docx",
            subtype=None,
        )
        s.add_all([a_era, a_kas, a_none])
        s.flush()
        s.add_all([
            CorpusSectionRow(
                audit_id=a_era.id, raw_number="6.1", section_ref="6.1",
                title="Vundament", body_text="ERA — vundament on heas seisus.",
            ),
            CorpusSectionRow(
                audit_id=a_kas.id, raw_number="6.1", section_ref="6.1",
                title="Vundament", body_text="KAS — vundament on heas seisus.",
            ),
            CorpusSectionRow(
                audit_id=a_none.id, raw_number="6.2", section_ref="6.2",
                title="Välisseinad", body_text="Sienäed on kontrollitud.",
            ),
            CorpusSectionRow(
                audit_id=a_era.id, raw_number="8.7", section_ref="8.7",
                title="Suitsueemaldus", body_text="Suitsueemalduskontroll OK.",
            ),
            CorpusSectionRow(
                audit_id=a_era.id, raw_number="14.1", section_ref="14.1",
                title="Lõpphinnang", body_text="Auditor-only — must NEVER leak.",
            ),
        ])
        s.commit()


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/fewshot.db")
    Base.metadata.create_all(engine)
    _seed(engine)

    class _Scope:
        def __enter__(self_inner):
            self_inner.s = Session(engine)
            return self_inner.s

        def __exit__(self_inner, *exc):
            self_inner.s.close()

    monkeypatch.setattr(fewshot, "session_scope", lambda: _Scope())
    return engine


def test_is_locked_top_level():
    assert _is_locked("11")
    assert _is_locked("11.1")
    assert _is_locked("14")
    assert _is_locked("14.3")
    assert not _is_locked("6.1")
    assert not _is_locked("8.7")
    assert not _is_locked(None)


def test_trim_short_text_unchanged():
    assert _trim("short", 50) == "short"


def test_trim_long_text_cuts_at_sentence_boundary():
    text = "A. " * 200  # very repetitive sentences
    out = _trim(text, 100)
    assert len(out) <= 101
    assert out.endswith(".") or out.endswith("…")


def test_examples_for_locked_section_returns_empty(seeded):
    assert examples_for("11") == []
    assert examples_for("11.1") == []
    assert examples_for("14") == []
    assert examples_for("14.1") == []


def test_examples_for_exact_match_no_subtype(seeded):
    # With max=2, we should get exactly the two exact-match 6.1 rows
    # (one per subtype) without falling through to the 6.x top-level pool.
    out = examples_for("6.1", max_examples=2)
    assert len(out) == 2
    bodies = " | ".join(out)
    assert "ERA" in bodies
    assert "KAS" in bodies
    # 6.2 must not leak in when the exact-match pool already filled the cap.
    assert "Sienäed" not in bodies


def test_examples_for_prefers_subtype(seeded):
    out = examples_for("6.1", subtype="erakorraline", max_examples=1)
    assert len(out) == 1
    assert "ERA" in out[0]
    assert "KAS" not in out[0]


def test_examples_for_unknown_section_falls_back_to_top_level(seeded):
    # 6.99 has no exact match; fall-through goes to top-level "6" / "6.x".
    out = examples_for("6.99", max_examples=2)
    assert len(out) == 2  # 6.1 (era) + 6.1 (kas) and/or 6.2 (none)


def test_examples_for_locked_never_leaks_via_top_level(seeded):
    # Even if you ask for 14.99, the entire 14.x branch is locked.
    out = examples_for("14.99", max_examples=5)
    assert out == []


def test_format_for_prompt_empty_returns_empty_string():
    assert format_for_prompt([]) == ""


def test_format_for_prompt_renders_examples():
    out = format_for_prompt(["alpha body", "beta body"])
    assert "Sarnaste jaotiste näited" in out
    assert "alpha body" in out
    assert "beta body" in out
    assert "Näide 1" in out
    assert "Näide 2" in out


def test_max_examples_cap(seeded):
    out = examples_for("6.1", max_examples=1)
    assert len(out) == 1


# ---------------------------------------------------------------------------
# Distilled-clause tier (preferred when present)
# ---------------------------------------------------------------------------

def _seed_clauses(engine):
    """Add a handful of distilled clauses for section 6.1 in the
    `erakorraline` audit (which the existing fixture seeded as id=1)."""
    with Session(engine) as s:
        # The fixture's first audit (era) has its 6.1 section as the second
        # row inserted (id 1 should be the era 6.1 section, but rather than
        # rely on insertion order, look it up explicitly).
        sec = (
            s.query(CorpusSectionRow)
            .filter(CorpusSectionRow.section_ref == "6.1")
            .join(CorpusAuditRow, CorpusSectionRow.audit_id == CorpusAuditRow.id)
            .filter(CorpusAuditRow.subtype == "erakorraline")
            .one()
        )
        s.add_all([
            CorpusClauseRow(
                audit_id=sec.audit_id, section_id=sec.id, section_ref="6.1",
                kind="boilerplate",
                text="DISTILLED-BOILER: Vundament on heas seisus.",
                reusability=0.9, model="claude-haiku-4-5", schema_version=1,
            ),
            CorpusClauseRow(
                audit_id=sec.audit_id, section_id=sec.id, section_ref="6.1",
                kind="finding",
                text="DISTILLED-FIND: Pragu vundamendi loode nurgas.",
                recommendation="Tihendada 6 kuu jooksul.",
                reusability=0.65, model="claude-haiku-4-5", schema_version=1,
            ),
            # A summary with low reusability — must NOT be picked
            # (filter requires >= 0.5).
            CorpusClauseRow(
                audit_id=sec.audit_id, section_id=sec.id, section_ref="6.1",
                kind="summary",
                text="DISTILLED-SUM: Audit kohta üldine kommentaar.",
                reusability=0.2, model="claude-haiku-4-5", schema_version=1,
            ),
        ])
        s.commit()


def test_distilled_clauses_take_priority(seeded):
    """When clauses exist for a section, they should be returned in
    preference to the raw section bodies — and the recommendation appears
    inline for finding clauses."""
    _seed_clauses(seeded)
    out = examples_for("6.1", max_examples=2)
    assert len(out) == 2
    joined = "\n".join(out)
    assert "DISTILLED-BOILER" in joined
    assert "DISTILLED-FIND" in joined
    # Recommendation gets stitched onto finding entries.
    assert "Soovitus: Tihendada" in joined
    # Raw section bodies must NOT appear — distilled fully filled the cap.
    assert "ERA — vundament" not in joined
    assert "KAS — vundament" not in joined


def test_distilled_low_reusability_filtered(seeded):
    """The summary at reusability=0.2 is below the >=0.5 bar — never
    surfaces as a few-shot example even when other clauses would."""
    _seed_clauses(seeded)
    out = examples_for("6.1", max_examples=5)
    joined = "\n".join(out)
    assert "DISTILLED-SUM" not in joined


def test_distilled_partial_fill_falls_back_to_raw(seeded):
    """Only one high-reusability distilled clause exists for 6.2 (none in
    fixture). Asking for max=2 from 6.2 should return raw 6.2 + raw 6.1
    bodies via top-level fallback rather than just the one distilled.

    Here we add a single distilled clause for 6.2, ask for max=2, and
    expect 1 distilled + 1 raw fallback."""
    with Session(seeded) as s:
        sec_62 = (
            s.query(CorpusSectionRow)
            .filter(CorpusSectionRow.section_ref == "6.2")
            .one()
        )
        s.add(
            CorpusClauseRow(
                audit_id=sec_62.audit_id, section_id=sec_62.id, section_ref="6.2",
                kind="boilerplate",
                text="DISTILLED-62: Välisseinad puhtad ja terved.",
                reusability=0.9, model="claude-haiku-4-5", schema_version=1,
            )
        )
        s.commit()

    out = examples_for("6.2", max_examples=2)
    assert len(out) == 2
    joined = "\n".join(out)
    assert "DISTILLED-62" in joined
    # The remaining slot must come from the raw-body fallback over 6.x.
    assert "Sienäed" in joined or "vundament" in joined
