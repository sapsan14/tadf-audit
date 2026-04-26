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

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from tadf.config import DB_URL
from tadf.db.orm import Base

_engine = create_engine(DB_URL, echo=False, future=True)
_SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
_initialised = False
_init_lock = threading.Lock()


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
