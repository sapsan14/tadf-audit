"""Cache warm-up walks the audit DB and refreshes external caches."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tadf.db.orm import AuditorRow, Base, BuildingRow, ClientRow


@pytest.fixture
def fake_db(tmp_path, monkeypatch):
    """Wire `tadf.db.session.session_scope` to an in-memory test database
    so prewarm walks our fixtures, not the real audit DB.
    """
    engine = create_engine(f"sqlite:///{tmp_path / 'prewarm.db'}", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    @contextmanager
    def fake_scope():
        s = SessionLocal()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    monkeypatch.setattr("tadf.db.session.session_scope", fake_scope)
    return engine, SessionLocal


@pytest.fixture(autouse=True)
def _isolate_external_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("tadf.external.cache.CACHE_DIR", tmp_path / "cache")


def _seed(SessionLocal, **kwargs) -> None:
    with SessionLocal() as s:
        for c in kwargs.get("clients", []):
            s.add(c)
        for a in kwargs.get("auditors", []):
            s.add(a)
        for b in kwargs.get("buildings", []):
            s.add(b)
        s.commit()


def test_collect_reg_codes_uses_both_clients_and_auditors(fake_db) -> None:
    _, SL = fake_db
    _seed(
        SL,
        clients=[
            ClientRow(name="X", reg_code="12503172"),
            ClientRow(name="Y", reg_code="10137319"),
            ClientRow(name="Z", reg_code=None),  # filtered
        ],
        auditors=[
            AuditorRow(full_name="A", company_reg_nr="12345678"),
            AuditorRow(full_name="B", company_reg_nr="abc"),  # filtered
        ],
    )
    from tadf.external.prewarm import collect_reg_codes
    assert collect_reg_codes() == {"12503172", "10137319", "12345678"}


def test_collect_reg_codes_strips_short_or_nondigit(fake_db) -> None:
    _, SL = fake_db
    _seed(
        SL,
        clients=[
            ClientRow(name="A", reg_code=" 12503172 "),
            ClientRow(name="B", reg_code="123"),
            ClientRow(name="C", reg_code="ABCDEFGH"),
        ],
    )
    from tadf.external.prewarm import collect_reg_codes
    assert collect_reg_codes() == {"12503172"}


def test_collect_addresses_uses_both_buildings_and_clients(fake_db) -> None:
    _, SL = fake_db
    _seed(
        SL,
        buildings=[
            BuildingRow(address="Auga 8 Narva-Jõesuu"),
            BuildingRow(address="Tartu mnt 84"),
            BuildingRow(address=""),  # filtered
        ],
        clients=[
            ClientRow(name="X", address="Sadama tn 25 Tallinn"),
            ClientRow(name="Y", address=None),  # filtered
        ],
    )
    from tadf.external.prewarm import collect_addresses
    assert collect_addresses() == {
        "Auga 8 Narva-Jõesuu",
        "Tartu mnt 84",
        "Sadama tn 25 Tallinn",
    }


def test_warm_companies_invokes_lookup_for_each_code(fake_db) -> None:
    _, SL = fake_db
    _seed(
        SL,
        clients=[
            ClientRow(name="X", reg_code="12503172"),
            ClientRow(name="Y", reg_code="10137319"),
        ],
    )
    calls: list[str] = []

    def fake_lookup(code, **kwargs):
        calls.append(code)
        return {"name": "Mock", "reg_code": code}

    with patch("tadf.external.ariregister_client.lookup_company", new=fake_lookup):
        from tadf.external.prewarm import warm_companies
        seen, warmed = warm_companies()

    assert seen == 2
    assert warmed == 2
    assert sorted(calls) == ["10137319", "12503172"]


def test_warm_companies_counts_misses(fake_db) -> None:
    _, SL = fake_db
    _seed(SL, clients=[ClientRow(name="X", reg_code="12503172")])

    def fake_lookup(code, **kwargs):
        return None

    with patch("tadf.external.ariregister_client.lookup_company", new=fake_lookup):
        from tadf.external.prewarm import warm_companies
        seen, warmed = warm_companies()

    assert seen == 1
    assert warmed == 0


def test_warm_addresses_invokes_search_for_each_address(fake_db) -> None:
    _, SL = fake_db
    _seed(SL, buildings=[BuildingRow(address="Auga 8 Narva-Jõesuu")])

    calls: list[str] = []

    def fake_search(q, **kwargs):
        calls.append(q)
        from tadf.external.inaadress_client import AddressHit
        return [AddressHit(address=q, short=None, ads_id="X", kataster=None,
                           coords=None, raw={})]

    with patch("tadf.external.inaadress_client.search_address", new=fake_search):
        from tadf.external.prewarm import warm_addresses
        seen, warmed = warm_addresses()

    assert seen == 1
    assert warmed == 1
    assert calls == ["Auga 8 Narva-Jõesuu"]


def test_warm_companies_swallows_exceptions(fake_db) -> None:
    _, SL = fake_db
    _seed(SL, clients=[ClientRow(name="X", reg_code="12503172")])

    def boom(code, **kwargs):
        raise RuntimeError("API down")

    with patch("tadf.external.ariregister_client.lookup_company", new=boom):
        from tadf.external.prewarm import warm_companies
        seen, warmed = warm_companies()

    # Errors are logged and counted as misses, never re-raised.
    assert seen == 1
    assert warmed == 0


def test_warm_all_returns_combined_stats(fake_db) -> None:
    _, SL = fake_db
    _seed(
        SL,
        clients=[ClientRow(name="X", reg_code="12503172", address="Sadama 25")],
        buildings=[BuildingRow(address="Auga 8 Narva-Jõesuu")],
    )

    def co_lookup(code, **kwargs):
        return {"name": "X", "reg_code": code}

    def addr_search(q, **kwargs):
        from tadf.external.inaadress_client import AddressHit
        return [AddressHit(address=q, short=None, ads_id="X", kataster=None,
                           coords=None, raw={})]

    with patch("tadf.external.ariregister_client.lookup_company", new=co_lookup), \
         patch("tadf.external.inaadress_client.search_address", new=addr_search):
        from tadf.external.prewarm import warm_all
        stats = warm_all()

    assert stats.companies_seen == 1
    assert stats.companies_warmed == 1
    assert stats.addresses_seen == 2  # client.address + building.address
    assert stats.addresses_warmed == 2
