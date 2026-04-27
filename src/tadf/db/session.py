"""SQLAlchemy session helpers.

`session_scope` is the only entrypoint and self-initialises the schema on
first use. This avoids "no such table" crashes on Streamlit Cloud, where
multipage scripts may run before any explicit `init_db()` call.

`init_db()` is **thread-safe and idempotent** — Streamlit reruns each script
in its own thread, and concurrent reruns at app boot can race the
`_initialised` flag and hit `CREATE TABLE … already exists` on SQLite. The
lock + double-checked check pattern below prevents that, and the
`OperationalError` catch covers the worker-process case (e.g. Hetzner +
multiple gunicorn-style processes sharing a DB file).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from tadf.config import DB_URL
from tadf.db.orm import Base

# Lightweight forward-only schema migrations for SQLite.
# Each entry is (table, column, type-with-default). On startup we ALTER
# TABLE only if the column is missing, so it's idempotent and safe to run
# every boot. Keep this list append-only — never edit a past entry.
_PENDING_MIGRATIONS: list[tuple[str, str, str]] = [
    ("audit", "header_override", "TEXT"),
    ("audit", "footer_override", "TEXT"),
]


def _apply_pending_migrations(engine) -> None:
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, column, coltype in _PENDING_MIGRATIONS:
            if not insp.has_table(table):
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            if column in existing:
                continue
            conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {coltype}'))

_engine = create_engine(DB_URL, echo=False, future=True)
_SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
_initialised = False
_init_lock = threading.Lock()


def _backfill_directory_once(session_factory) -> None:
    """First time the directory tables exist on a deployment with prior
    AuditorRow / ClientRow / BuildingRow data, copy distinct names/values
    into the directory so the dropdowns surface accumulated history
    immediately. Safe to run on every boot (idempotent — skipped when
    the directory tables already have rows)."""
    # Local import to avoid a cycle (repo imports orm, session imports orm).
    from tadf.db.orm import (
        DirectoryAuditorRow,
        DirectoryBuilderRow,
        DirectoryClientRow,
        DirectoryDesignerRow,
        DirectoryUsePurposeRow,
    )
    from tadf.db.repo import backfill_directory

    s = session_factory()
    try:
        # Cheap shortcut: if any directory has at least one row already,
        # assume the backfill has run before. Users can re-trigger by
        # truncating the directory tables manually.
        for model in (
            DirectoryAuditorRow,
            DirectoryClientRow,
            DirectoryDesignerRow,
            DirectoryBuilderRow,
            DirectoryUsePurposeRow,
        ):
            if s.query(model).limit(1).count() > 0:
                return
        backfill_directory(s)
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def init_db() -> None:
    """Idempotent + thread-safe schema bootstrap. Safe to call from many
    threads / multiple Streamlit reruns concurrently."""
    global _initialised
    if _initialised:
        return
    with _init_lock:
        if _initialised:
            return
        try:
            Base.metadata.create_all(_engine)
        except OperationalError as e:
            # SQLite race between two concurrent CREATE TABLE statements is
            # benign — the second one sees the first's table and fails with
            # "already exists". Tolerate it; the schema is correct either way.
            if "already exists" not in str(e).lower():
                raise
        # Forward-only column adds for tables that already existed before
        # this commit (existing prod DB with the old `audit` schema).
        _apply_pending_migrations(_engine)
        # One-time directory population from existing audit history.
        _backfill_directory_once(_SessionLocal)
        _initialised = True


@contextmanager
def session_scope() -> Iterator[Session]:
    init_db()  # Ensure schema before opening any session.
    s = _SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
