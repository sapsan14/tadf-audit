"""Tests for tadf.corpus.store — metadata inference, normalisation, ingest."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import tadf.corpus.store as store
from tadf.corpus.store import _infer_meta, _normalise_section_ref
from tadf.db.orm import Base, CorpusAuditRow, CorpusSectionRow


@pytest.mark.parametrize(
    "stem, expected_seq, expected_year, expected_kind",
    [
        # Newer SSYYYY convention — 2-digit seq + 4-digit year.
        ("012026_EP_AA1-01_Energeetik_Audit_2026-01-20", 1, 2026, "EP"),
        ("352024_EA_AA-1-03_Savi10Narva_Audit_2024-08-14", 35, 2024, "EA"),
        ("322025_EA_AA-1-01_Pribrezno_Audit_25122025", 32, 2025, "EA"),
        # Older DDMMYY date convention — no seq, year from date.
        ("100825_TJ_AA-1-01_Auga_8_Narva-Joesuu_Audit_2025-08-10", None, 2025, "TJ"),
        ("180625_TJ_AA-1-01_Noo_43_Narva_Audit_2025-06-18", None, 2025, "TJ"),
    ],
)
def test_infer_meta_handles_both_filename_conventions(
    stem, expected_seq, expected_year, expected_kind
):
    seq, year, kind = _infer_meta(stem)
    assert seq == expected_seq
    assert year == expected_year
    assert kind == expected_kind


def test_infer_meta_unknown_filename():
    seq, year, kind = _infer_meta("random_garbage_filename_no_date")
    assert seq is None
    assert year is None
    assert kind is None


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("6.1", "6.1"),  # exact match
        ("8.7", "8.7"),  # exact match
        ("1", "1"),  # auto-section top-level (Üldosa)
        ("12", "12"),  # auto-section (Õiguslikud alused)
        ("6.1.1.3", "6.1"),  # over-numbered → strip trailing levels
        ("6.99", "6"),  # subsection unknown → fall back to top-level
        ("99.99", None),  # totally unknown
    ],
)
def test_normalise_section_ref(raw, expected):
    assert _normalise_section_ref(raw) == expected


def _patch_session(monkeypatch, tmp_path):
    """Point the corpus store's session_scope at an isolated SQLite file."""
    engine = create_engine(f"sqlite:///{tmp_path}/store_test.db")
    Base.metadata.create_all(engine)

    class _Scope:
        def __enter__(self_inner):
            self_inner.s = Session(engine)
            return self_inner.s

        def __exit__(self_inner, *exc):
            self_inner.s.commit()
            self_inner.s.close()

    monkeypatch.setattr(store, "session_scope", lambda: _Scope())
    return engine


def test_ingest_skips_unsupported_format(tmp_path, monkeypatch):
    _patch_session(monkeypatch, tmp_path)
    txt = tmp_path / "junk.txt"
    txt.write_text("not an audit")
    status, audit_id = store.ingest_file(txt)
    assert status == "skip-format"
    assert audit_id is None


def test_ingest_directory_handles_empty_dir(tmp_path, monkeypatch):
    _patch_session(monkeypatch, tmp_path)
    counts = store.ingest_directory(tmp_path / "empty")
    assert counts == {
        "imported": 0,
        "skip-duplicate": 0,
        "skip-format": 0,
        "skip-no-libreoffice": 0,
        "error": 0,
    }


def test_ingest_dedupes_by_sha256(tmp_path, monkeypatch):
    """Re-ingesting the same bytes must not create duplicate rows. We use a
    real corpus .docx if available, else skip."""
    from pathlib import Path

    corpus = Path(__file__).resolve().parents[1] / "audit"
    candidate = corpus / "012026_EP_AA1-01_Energeetik2AÜ74Narva-Jõesuu_Audit_2026-01-20.docx"
    if not candidate.exists():
        pytest.skip("Corpus .docx not present")

    engine = _patch_session(monkeypatch, tmp_path)

    s1, id1 = store.ingest_file(candidate)
    assert s1 == "imported"
    assert id1 is not None

    s2, id2 = store.ingest_file(candidate)
    assert s2 == "skip-duplicate"
    assert id2 == id1

    # Confirm DB really has only one row.
    with Session(engine) as s:
        n_audits = s.query(CorpusAuditRow).count()
        n_sections = s.query(CorpusSectionRow).count()
    assert n_audits == 1
    assert n_sections > 0
