"""Tests for `*_by_name` resolvers in `tadf.db.lookups`.

Used by the form pages to autofill companion fields when the auditor
picks a past name from the combobox dropdown.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import delete

from tadf.db.lookups import auditor_by_name, client_by_name
from tadf.db.orm import AuditorRow, AuditRow, BuildingRow, ClientRow
from tadf.db.repo import save_audit
from tadf.db.session import session_scope
from tadf.models import Audit, Auditor, Building, Client


def _make_audit(
    *,
    seq: int,
    client: Client,
    composer: Auditor,
    reviewer: Auditor | None = None,
) -> Audit:
    return Audit(
        seq_no=seq,
        year=2026,
        type="EA",
        subtype="kasutuseelne",
        visit_date=date.today(),
        composer=composer,
        reviewer=reviewer
        or Auditor(full_name="default-reviewer-by-name-test"),
        building=Building(address=f"addr-{seq}"),
        client=client,
    )


def _cleanup(audit_ids: list[int]) -> None:
    """Remove test rows so they don't pollute the dev DB across test runs."""
    with session_scope() as s:
        for aid in audit_ids:
            row = s.get(AuditRow, aid)
            if row is None:
                continue
            client_id = row.client_id
            building_id = row.building_id
            composer_id = row.composer_id
            reviewer_id = row.reviewer_id
            s.delete(row)
            s.flush()
            if client_id:
                s.execute(delete(ClientRow).where(ClientRow.id == client_id))
            s.execute(delete(BuildingRow).where(BuildingRow.id == building_id))
            s.execute(delete(AuditorRow).where(AuditorRow.id.in_({composer_id, reviewer_id})))


def test_client_by_name_returns_most_recent_record() -> None:
    name = "Test ByName Client OÜ"
    older = _make_audit(
        seq=901,
        client=Client(name=name, reg_code="11111111", address="Old Street 1"),
        composer=Auditor(full_name="older-composer"),
    )
    newer = _make_audit(
        seq=902,
        client=Client(
            name=name,
            reg_code="22222222",
            address="New Street 2",
            contact_email="new@example.com",
        ),
        composer=Auditor(full_name="newer-composer"),
    )
    aids: list[int] = []
    try:
        with session_scope() as s:
            aids.append(save_audit(s, older))
            aids.append(save_audit(s, newer))

        got = client_by_name(name)
        assert got is not None
        # Most recent wins → reg_code from `newer`, not `older`.
        assert got.reg_code == "22222222"
        assert got.address == "New Street 2"
        assert got.contact_email == "new@example.com"
        assert got.name == name
    finally:
        _cleanup(aids)


def test_client_by_name_case_insensitive_and_trimmed() -> None:
    name = "Mixed CASE Client"
    audit = _make_audit(
        seq=903,
        client=Client(name=name, reg_code="33333333"),
        composer=Auditor(full_name="case-composer"),
    )
    aids: list[int] = []
    try:
        with session_scope() as s:
            aids.append(save_audit(s, audit))

        # Different case + leading/trailing spaces still resolves.
        got = client_by_name("  mixed case CLIENT  ")
        assert got is not None
        assert got.reg_code == "33333333"
    finally:
        _cleanup(aids)


def test_client_by_name_unknown_returns_none() -> None:
    assert client_by_name("Definitely Not A Saved Client XYZ") is None
    assert client_by_name("") is None
    assert client_by_name("   ") is None


def test_auditor_by_name_finds_composer() -> None:
    name = "Test ByName Composer"
    audit = _make_audit(
        seq=904,
        client=Client(name="byname-client-901"),
        composer=Auditor(
            full_name=name,
            kutsetunnistus_no="999999",
            qualification="Test qual",
            company="Test Company OÜ",
            company_reg_nr="44444444",
        ),
    )
    aids: list[int] = []
    try:
        with session_scope() as s:
            aids.append(save_audit(s, audit))

        got = auditor_by_name(name)
        assert got is not None
        assert got.kutsetunnistus_no == "999999"
        assert got.qualification == "Test qual"
        assert got.company == "Test Company OÜ"
        assert got.company_reg_nr == "44444444"
    finally:
        _cleanup(aids)


def test_auditor_by_name_finds_reviewer_too() -> None:
    """`auditor_by_name` should match against composer OR reviewer slot."""
    name = "Test ByName Reviewer Only"
    audit = _make_audit(
        seq=905,
        client=Client(name="byname-client-905"),
        composer=Auditor(full_name="some-composer-905"),
        reviewer=Auditor(
            full_name=name,
            kutsetunnistus_no="148515",
            qualification="Reviewer qual",
        ),
    )
    aids: list[int] = []
    try:
        with session_scope() as s:
            aids.append(save_audit(s, audit))

        got = auditor_by_name(name)
        assert got is not None
        assert got.kutsetunnistus_no == "148515"
        assert got.qualification == "Reviewer qual"
    finally:
        _cleanup(aids)


def test_auditor_by_name_unknown_returns_none() -> None:
    assert auditor_by_name("Nonexistent Auditor XYZ") is None
    assert auditor_by_name("") is None
