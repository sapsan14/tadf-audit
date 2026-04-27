"""Audit history (snapshots) — save / list / restore + 30-version cap."""

from __future__ import annotations

from datetime import date

from tadf.db.repo import (
    SNAPSHOT_LIMIT,
    list_snapshots,
    load_snapshot,
    save_audit,
    save_snapshot,
)
from tadf.db.session import session_scope
from tadf.models import Audit, Auditor, Building, Client


def _make_audit(seq: int) -> Audit:
    return Audit(
        seq_no=seq,
        year=2026,
        type="EA",
        subtype="kasutuseelne",
        visit_date=date.today(),
        composer=Auditor(full_name=f"composer-{seq}"),
        reviewer=Auditor(full_name=f"reviewer-{seq}"),
        building=Building(address=f"addr-{seq}"),
        client=Client(name=f"client-{seq}"),
    )


def _cleanup(audit_id: int) -> None:
    from sqlalchemy import delete

    from tadf.db.orm import AuditRow, AuditSnapshotRow

    with session_scope() as s:
        s.execute(delete(AuditSnapshotRow).where(AuditSnapshotRow.audit_id == audit_id))
        row = s.get(AuditRow, audit_id)
        if row is not None:
            s.delete(row)


def test_save_snapshot_assigns_monotonic_versions() -> None:
    with session_scope() as s:
        aid = save_audit(s, _make_audit(101))
    try:
        with session_scope() as s:
            v1 = save_snapshot(s, aid, '{"step": 1}')
            v2 = save_snapshot(s, aid, '{"step": 2}')
            v3 = save_snapshot(s, aid, '{"step": 3}')
        assert (v1, v2, v3) == (1, 2, 3)
    finally:
        _cleanup(aid)


def test_list_snapshots_newest_first() -> None:
    with session_scope() as s:
        aid = save_audit(s, _make_audit(102))
    try:
        with session_scope() as s:
            for i in range(5):
                save_snapshot(s, aid, f'{{"step": {i}}}')
            rows = list_snapshots(s, aid)
        # newest first → version_no descending
        versions = [r.version_no for r in rows]
        assert versions == [5, 4, 3, 2, 1]
    finally:
        _cleanup(aid)


def test_load_snapshot_round_trip() -> None:
    with session_scope() as s:
        original = _make_audit(103)
        aid = save_audit(s, original)
    try:
        # Snapshot the audit's serialised state
        with session_scope() as s:
            snap_json = original.model_dump_json()
            save_snapshot(s, aid, snap_json)
            rows = list_snapshots(s, aid)
            snap_row = rows[0]
        # Restore via load_snapshot
        with session_scope() as s:
            restored = load_snapshot(s, snap_row.id)
        assert restored is not None
        assert restored.building.address == "addr-103"
        assert restored.client.name == "client-103"
    finally:
        _cleanup(aid)


def test_load_snapshot_missing_returns_none() -> None:
    with session_scope() as s:
        assert load_snapshot(s, 999_999) is None


def test_load_snapshot_corrupt_returns_none() -> None:
    with session_scope() as s:
        aid = save_audit(s, _make_audit(104))
    try:
        with session_scope() as s:
            save_snapshot(s, aid, "{not valid json")
            rows = list_snapshots(s, aid)
            snap_id = rows[0].id
        with session_scope() as s:
            assert load_snapshot(s, snap_id) is None
    finally:
        _cleanup(aid)


def test_snapshot_cap_drops_oldest() -> None:
    """Once we cross SNAPSHOT_LIMIT, the oldest version is dropped."""
    with session_scope() as s:
        aid = save_audit(s, _make_audit(105))
    try:
        # Write SNAPSHOT_LIMIT + 5 snapshots
        with session_scope() as s:
            for i in range(SNAPSHOT_LIMIT + 5):
                save_snapshot(s, aid, f'{{"step": {i}}}')
            rows = list_snapshots(s, aid)
        # We should retain exactly SNAPSHOT_LIMIT, with the newest range
        assert len(rows) == SNAPSHOT_LIMIT
        versions = sorted(r.version_no for r in rows)
        # The 5 oldest (1..5) should have been dropped
        assert versions[0] == 6
        assert versions[-1] == SNAPSHOT_LIMIT + 5
    finally:
        _cleanup(aid)
