"""Round-trip test for the Phase 2 migration (users + refresh_sessions).

Deliberately a **synchronous** test function, not ``async def``:
alembic/env.py's online-migration path calls ``asyncio.run(...)``
internally, which raises ``RuntimeError`` if invoked from inside an
already-running event loop — exactly the situation a pytest-asyncio
``async def`` test would create for it. A plain sync test has no event
loop of its own when it starts, so alembic's internal ``asyncio.run()``
call (and this test's own, for its lightweight table-existence checks)
are each the only one running at any given time.

This test is intentionally self-restoring: the ``finally`` block always
leaves the schema back at the repository's current Alembic head, even if an
assertion fails partway through, so later Phase 3 tests still see their tables.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

_BACKEND_V2_ROOT = Path(__file__).resolve().parents[2]

PHASE1_BASELINE_REVISION = "98161483914f"
PHASE2_HEAD_REVISION = "6eeb9420bf8b"


def _alembic_config() -> Config:
    cfg = Config(str(_BACKEND_V2_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_V2_ROOT / "alembic"))
    return cfg


def _table_exists(table_name: str) -> bool:
    async def _check() -> bool:
        engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(
                    text("SELECT to_regclass(:name)"), {"name": table_name}
                )
                return result.scalar() is not None
        finally:
            await engine.dispose()

    return asyncio.run(_check())


def _current_revision(cfg: Config) -> str | None:
    async def _check() -> str | None:
        engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(text("SELECT version_num FROM alembic_version"))
                row = result.first()
                return row[0] if row else None
        finally:
            await engine.dispose()

    return asyncio.run(_check())


def test_phase2_migration_round_trip() -> None:
    cfg = _alembic_config()

    try:
        # The Docker workflow migrates to the repository's current head
        # before pytest. Explicitly step back to Phase 2 so this historical
        # round-trip test remains valid after later migrations are added.
        command.upgrade(cfg, "head")
        command.downgrade(cfg, PHASE2_HEAD_REVISION)
    except (ModuleNotFoundError, SQLAlchemyError) as exc:
        pytest.skip(
            "Skipping migration round-trip test: no reachable PostgreSQL "
            f"test database ({type(exc).__name__}). See backend_v2/README.md "
            "'Phase 2 database-backed tests'."
        )

    try:
        assert _current_revision(cfg) == PHASE2_HEAD_REVISION
        assert _table_exists("users") is True
        assert _table_exists("refresh_sessions") is True

        # Downgrade to the Phase 1 baseline: both Phase 2 tables must
        # disappear cleanly, with no leftover enum type blocking a
        # future re-creation.
        command.downgrade(cfg, PHASE1_BASELINE_REVISION)
        assert _current_revision(cfg) == PHASE1_BASELINE_REVISION
        assert _table_exists("users") is False
        assert _table_exists("refresh_sessions") is False

        # Re-upgrade specifically to Phase 2; the finally block restores
        # the repository's latest head for the rest of the suite.
        command.upgrade(cfg, PHASE2_HEAD_REVISION)
        assert _current_revision(cfg) == PHASE2_HEAD_REVISION
        assert _table_exists("users") is True
        assert _table_exists("refresh_sessions") is True
    finally:
        # Always restore the repository's latest head, regardless of
        # whether the Phase 2 assertions above passed.
        command.upgrade(cfg, "head")
