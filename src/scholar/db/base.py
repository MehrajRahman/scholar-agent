"""Database foundation for the web app's system of record.

SQLAlchemy 2.0, synchronous engine (FastAPI runs sync DB dependencies in a
threadpool). Defaults to SQLite for zero-setup local dev; point ``DATABASE_URL``
at Postgres for the real deployment — the models are portable across both.

Schema changes are bootstrapped with ``init_db()`` (create-all) for now; Alembic
migrations come in with the auth increment once the schema stabilises.
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from ..config import get_settings
from ..observability import get_logger

log = get_logger("db")


class Base(DeclarativeBase):
    """Declarative base shared by every model."""


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _engine_kwargs(url: str) -> dict:
    # SQLite + threadpool needs check_same_thread off; Postgres wants pool ping.
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True}


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = get_settings().database_url
        _engine = create_engine(url, **_engine_kwargs(url))
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _SessionLocal


def _ensure_columns(engine: Engine) -> None:
    """Lightweight additive migration: ADD COLUMN for any model column missing
    from an existing table. Handles the common additive case (new fields) without
    the weight of Alembic and without dropping data. Not a substitute for real
    migrations once the schema needs renames/drops/backfills."""
    insp = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing:
                continue
            col_type = col.type.compile(dialect=engine.dialect)
            try:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {col.name} {col_type}"))
                log.info("db_column_added", table=table.name, column=col.name)
            except Exception as exc:  # noqa: BLE001
                log.warning("db_add_column_failed", table=table.name, column=col.name, error=str(exc))


def init_db() -> None:
    """Create missing tables, then add any missing columns (dev bootstrap)."""
    from . import models  # noqa: F401 - register models on the metadata

    engine = get_engine()
    Base.metadata.create_all(engine)
    _ensure_columns(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: yield a session, always close it after the request."""
    with get_sessionmaker()() as session:
        yield session
