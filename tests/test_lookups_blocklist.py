"""Tests for the autocomplete-suggestion blocklist.

The auditor can hide stale / typo / test values from the combobox
dropdown without deleting the underlying audit data; this validates
the round-trip + that hidden values are filtered out of the public
`*_names` / `*_addresses` / `*_companies` helpers.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import delete

from tadf.db.lookups import (
    KIND_BUILDING_ADDRESS,
    KIND_CLIENT_NAME,
    KIND_COMPOSER_NAME,
    building_addresses,
    client_names,
    composer_names,
    hidden_lookups,
    hide_lookup,
    unhide_lookup,
)
from tadf.db.orm import AuditorRow, AuditRow, BuildingRow, ClientRow, LookupHiddenRow
from tadf.db.repo import save_audit
from tadf.db.session import session_scope
from tadf.models import Audit, Auditor, Building, Client


def _make_audit(seq: int, *, client_name: str, composer: str, address: str) -> Audit:
    return Audit(
        seq_no=seq,
        year=2026,
        type="EA",
        subtype="kasutuseelne",
        visit_date=date.today(),
        composer=Auditor(full_name=composer),
        reviewer=Auditor(full_name=f"reviewer-blocklist-{seq}"),
        building=Building(address=address),
        client=Client(name=client_name),
    )


def _cleanup(audit_ids: list[int], hidden_kinds: list[str]) -> None:
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
        for kind in hidden_kinds:
            s.execute(delete(LookupHiddenRow).where(LookupHiddenRow.kind == kind))


def test_hide_lookup_removes_from_suggestions() -> None:
    name = "Blocklist Test Client OÜ"
    aids: list[int] = []
    try:
        with session_scope() as s:
            aids.append(
                save_audit(
                    s,
                    _make_audit(
                        seq=701,
                        client_name=name,
                        composer="blocklist-c-701",
                        address="addr-701",
                    ),
                )
            )

        assert name in client_names()
        hide_lookup(KIND_CLIENT_NAME, name)
        assert name not in client_names()
        # And it's reported in `hidden_lookups`.
        assert name in hidden_lookups(KIND_CLIENT_NAME)
    finally:
        _cleanup(aids, [KIND_CLIENT_NAME])


def test_unhide_lookup_restores() -> None:
    name = "Restore Test Client OÜ"
    aids: list[int] = []
    try:
        with session_scope() as s:
            aids.append(
                save_audit(
                    s,
                    _make_audit(
                        seq=702,
                        client_name=name,
                        composer="blocklist-c-702",
                        address="addr-702",
                    ),
                )
            )

        hide_lookup(KIND_CLIENT_NAME, name)
        assert name not in client_names()
        unhide_lookup(KIND_CLIENT_NAME, name)
        assert name in client_names()
        assert name not in hidden_lookups(KIND_CLIENT_NAME)
    finally:
        _cleanup(aids, [KIND_CLIENT_NAME])


def test_hide_lookup_is_case_insensitive() -> None:
    """If the auditor hides `Foo OÜ`, `foo oü` should also be filtered out
    when it eventually lands in the DB via a different audit."""
    aids: list[int] = []
    try:
        with session_scope() as s:
            aids.append(
                save_audit(
                    s,
                    _make_audit(
                        seq=703,
                        client_name="Mixed CASE OÜ",
                        composer="blocklist-c-703",
                        address="addr-703",
                    ),
                )
            )

        # Hide using a different case variant.
        hide_lookup(KIND_CLIENT_NAME, "mixed case oü")
        assert "Mixed CASE OÜ" not in client_names()
        unhide_lookup(KIND_CLIENT_NAME, "MIXED case OÜ")
        assert "Mixed CASE OÜ" in client_names()
    finally:
        _cleanup(aids, [KIND_CLIENT_NAME])


def test_hide_lookup_idempotent() -> None:
    name = "Idempotent Test Client OÜ"
    aids: list[int] = []
    try:
        with session_scope() as s:
            aids.append(
                save_audit(
                    s,
                    _make_audit(
                        seq=704,
                        client_name=name,
                        composer="blocklist-c-704",
                        address="addr-704",
                    ),
                )
            )

        hide_lookup(KIND_CLIENT_NAME, name)
        hide_lookup(KIND_CLIENT_NAME, name)  # should be no-op
        hide_lookup(KIND_CLIENT_NAME, name.lower())  # case variant
        assert hidden_lookups(KIND_CLIENT_NAME).count(name) == 1
        # No additional rows for case variants either:
        assert len(hidden_lookups(KIND_CLIENT_NAME)) == 1
    finally:
        _cleanup(aids, [KIND_CLIENT_NAME])


def test_hide_lookup_per_kind_isolation() -> None:
    """Hiding `Foo` under `client_name` shouldn't hide it under
    `composer_name`."""
    aids: list[int] = []
    try:
        with session_scope() as s:
            aids.append(
                save_audit(
                    s,
                    _make_audit(
                        seq=705,
                        client_name="Cross Kind",
                        composer="Cross Kind",
                        address="addr-705",
                    ),
                )
            )

        hide_lookup(KIND_CLIENT_NAME, "Cross Kind")
        assert "Cross Kind" not in client_names()
        # composer dropdown still shows it
        assert "Cross Kind" in composer_names()
    finally:
        _cleanup(aids, [KIND_CLIENT_NAME, KIND_COMPOSER_NAME])


def test_hide_lookup_empty_value_is_noop() -> None:
    hide_lookup(KIND_CLIENT_NAME, "")
    hide_lookup(KIND_CLIENT_NAME, "   ")
    unhide_lookup(KIND_CLIENT_NAME, "")
    # No row should have been written.
    with session_scope() as s:
        n = s.query(LookupHiddenRow).filter(LookupHiddenRow.kind == KIND_CLIENT_NAME).count()
    assert n == 0


def test_building_addresses_filtered_too() -> None:
    """Same blocklist mechanism applies to building addresses."""
    addr = "Hidden Address 99, City"
    aids: list[int] = []
    try:
        with session_scope() as s:
            aids.append(
                save_audit(
                    s,
                    _make_audit(
                        seq=706,
                        client_name="addr-test-706",
                        composer="addr-test-706",
                        address=addr,
                    ),
                )
            )
        assert addr in building_addresses()
        hide_lookup(KIND_BUILDING_ADDRESS, addr)
        assert addr not in building_addresses()
    finally:
        _cleanup(aids, [KIND_BUILDING_ADDRESS])
