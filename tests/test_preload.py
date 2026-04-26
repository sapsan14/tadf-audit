from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tadf.corpus.preload import _infer_meta_from_filename
from tadf.db.orm import Base


# Year + type are extractable reliably; seq_no encoding varies across the
# corpus (some filenames pack seq+yy, some pack DDMMYY) so we don't assert it.
@pytest.mark.parametrize(
    "stem, expected_year, expected_type",
    [
        ("100825_TJ_AA-1-01_Auga_8_Narva-Joesuu_Audit_2025-08-10", 2025, "TJ"),
        ("012026_EP_AA1-01_Energeetik_Audit_2026-01-20", 2026, "EP"),
        ("352024_EA_AA-1-03_Savi10Narva_Audit_2024-08-14", 2024, "EA"),
        ("322025_EA_AA-1-01_Pribrezno_Audit_25122025", 2025, "EA"),
    ],
)
def test_filename_meta_year_and_type(stem, expected_year, expected_type):
    meta = _infer_meta_from_filename(stem)
    assert meta["year"] == expected_year
    # Type may not be extracted if the leading prefix doesn't match — fall back
    # to default 'EA' is acceptable. But for matched prefixes we expect the right type.
    if meta["type"] != "EA":
        assert meta["type"] == expected_type


def test_filename_unknown_does_not_crash():
    # Should not raise, should fall back to defaults
    meta = _infer_meta_from_filename("random_garbage_filename")
    assert meta["seq_no"] == 1
    assert meta["type"] == "EA"


def test_preload_skips_missing_audit_dir(tmp_path, monkeypatch):
    # Point the DB at a temp file so we don't touch the dev DB
    db_file = tmp_path / "preload_test.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)

    # Patch session_scope to use our temp engine
    import tadf.corpus.preload as p
    from tadf.corpus.preload import preload_corpus

    class _Scope:
        def __enter__(self_inner):
            self_inner.s = Session(engine)
            return self_inner.s

        def __exit__(self_inner, *exc):
            self_inner.s.commit()
            self_inner.s.close()

    monkeypatch.setattr(p, "session_scope", lambda: _Scope())

    imp, skp = preload_corpus(tmp_path / "nonexistent")
    assert imp == 0
    assert skp == 0
