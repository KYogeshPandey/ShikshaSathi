"""Async SQLAlchemy engine, session factory, and FastAPI database dependencies.

Two dependencies are exported for use in routes:

- ``get_db_session`` — yields a request-scoped ``AsyncSession`` with a
  correct commit/rollback/close lifecycle. No repository/service code
  exists yet in Phase 1, but this is the seam Phase 3+ builds on.
- ``require_database_ready`` — used only by GET /health/ready; runs a
  real ``SELECT 1`` and raises the sanitized ``DatabaseUnavailableError``
  on failure, so the route itself stays a one-line dependency call and is
  trivially overridable in tests without a real Postgres instance (see
  app/tests/conftest.py's ``database_ready`` / ``database_unavailable``
  fixtures, and app/tests/test_health_ready.py).

Engines/sessionmakers are cached per (url, echo) pair rather than as a
single process-wide singleton bound to whichever settings happened to be
active first — this matters because ``get_settings()`` can be overridden
per-app in tests via ``app.dependency_overrides``, and a naive singleton
would silently ignore that override.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

import structlog
from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings
from app.core.exceptions import DatabaseUnavailableError

logger = structlog.get_logger(__name__)

_engine_cache: dict[tuple[str, bool], AsyncEngine] = {}
_sessionmaker_cache: dict[tuple[str, bool], async_sessionmaker[AsyncSession]] = {}


def get_engine(settings: Settings) -> AsyncEngine:
    """Return the (cached) async engine for these settings."""
    key = (settings.DATABASE_URL, settings.DATABASE_ECHO)
    if key not in _engine_cache:
        _engine_cache[key] = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.DATABASE_ECHO,
            pool_pre_ping=True,
            future=True,
        )
    return _engine_cache[key]


def _get_sessionmaker(settings: Settings) -> async_sessionmaker[AsyncSession]:
    key = (settings.DATABASE_URL, settings.DATABASE_ECHO)
    if key not in _sessionmaker_cache:
        _sessionmaker_cache[key] = async_sessionmaker(
            bind=get_engine(settings), expire_on_commit=False, autoflush=False
        )
    return _sessionmaker_cache[key]


async def get_db_session(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncGenerator[AsyncSession, None]:
    """Yield a request-scoped session; roll back on error, always close.

    Commits are deliberately the caller's responsibility (no domain
    service layer exists yet to own transaction boundaries) — this
    dependency only guarantees cleanup and never hides or swallows the
    application's original exception.
    """
    session_factory = _get_sessionmaker(settings)
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def ping_database(settings: Settings) -> None:
    """Run a real, minimal query against PostgreSQL.

    Raises whatever the underlying driver raises on failure —
    deliberately untranslated here, so this stays a pure, easily-mocked
    infrastructure check (see app/tests/test_health_ready.py).
    """
    engine = get_engine(settings)
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def require_database_ready(
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """FastAPI dependency for GET /health/ready.

    Translates any failure from ``ping_database`` into the sanitized
    ``DatabaseUnavailableError`` — never the raw driver/SQLAlchemy
    exception, its message, or any connection detail. This is the direct
    fix for docs/AUDIT.md §2.2's shallow-health-check finding (the legacy
    ``/health`` endpoint reported ``{"status": "ok"}`` even when MongoDB
    was unreachable).
    """
    try:
        await ping_database(settings)
    except Exception as exc:
        logger.warning("readiness_check_failed", exc_type=type(exc).__name__)
        raise DatabaseUnavailableError() from exc


async def dispose_all_engines() -> None:
    """Dispose every cached engine's connection pool (app shutdown or test teardown)."""
    for engine in list(_engine_cache.values()):
        await engine.dispose()
    _engine_cache.clear()
    _sessionmaker_cache.clear()
