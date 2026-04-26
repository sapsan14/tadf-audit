"""SQLAlchemy session helpers.

`session_scope` is the only entrypoint and self-initialises the schema on
first use. This avoids "no such table" crashes on Streamlit Cloud, where
multipage scripts may run before any explicit `init_db()` call.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from tadf.config import DB_URL
from tadf.db.orm import Base

_engine = create_engine(DB_URL, echo=False, future=True)
_SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
_initialised = False


def init_db() -> None:
    """Idempotent — safe to call multiple times."""
    global _initialised
    if _initialised:
        return
    Base.metadata.create_all(_engine)
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
