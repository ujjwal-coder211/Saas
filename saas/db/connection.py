"""PostgreSQL connection pool — optional (falls back to env keys if unset)."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from neuralrouter.config import DATABASE_URL

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def saas_db_enabled() -> bool:
    return bool(DATABASE_URL)


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL not configured")
        _engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
        logger.info("SaaS database connected")
    return _engine


@contextmanager
def db_session() -> Generator[Session, None, None]:
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def run_schema_sql() -> None:
    from pathlib import Path

    schema_path = Path(__file__).parent / "schema.sql"
    sql = schema_path.read_text(encoding="utf-8")
    engine = get_engine()
    with engine.begin() as conn:
        for stmt in sql.split(";"):
            chunk = stmt.strip()
            if chunk:
                conn.execute(text(chunk))
