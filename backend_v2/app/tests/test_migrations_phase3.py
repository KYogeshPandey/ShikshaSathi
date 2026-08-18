"""Round-trip test for the Phase 3 Stage 1 migration (academics/profiles/announcements).

Mirrors ``app.tests.test_migrations_phase2`` exactly (same sync-test,
self-restoring-``finally`` rationale — see that file's docstring, not
repeated here). Downgrades to Phase 2 head (``6eeb9420bf8b``), not all
the way to the Phase 1 baseline, since this migration's *parent* is
Phase 2 head, not the Phase 1 baseline.
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

PHASE2_HEAD_REVISION = "6eeb9420bf8b"
PHASE3_STAGE1_HEAD_REVISION = "32819e0a6027"

_PHASE3_TABLES = (
    "classrooms",
    "subjects",
    "teacher_profiles",
    "student_profiles",
    "teacher_assignments",
    "timetable_entries",
    "announcements",
    "announcement_classrooms",
)


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


def _enum_values(enum_name: str) -> list[str]:
    async def _check() -> list[str]:
        engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(
                    text(
                        """
                        SELECT enum_value.enumlabel
                        FROM pg_type AS enum_type
                        JOIN pg_enum AS enum_value
                          ON enum_type.oid = enum_value.enumtypid
                        WHERE enum_type.typname = :enum_name
                        ORDER BY enum_value.enumsortorder
                        """
                    ),
                    {"enum_name": enum_name},
                )
                return list(result.scalars().all())
        finally:
            await engine.dispose()

    return asyncio.run(_check())


def test_phase3_stage1_migration_round_trip() -> None:
    cfg = _alembic_config()

    try:
        # Ensure the database is fully current, then move to the Phase 3
        # revision under test. A later phase may legitimately be the global head.
        command.upgrade(cfg, "head")
        command.downgrade(cfg, PHASE3_STAGE1_HEAD_REVISION)
    except (ModuleNotFoundError, SQLAlchemyError) as exc:
        pytest.skip(
            "Skipping Phase 3 migration round-trip test: no reachable PostgreSQL "
            f"test database ({type(exc).__name__}). See backend_v2/README.md "
            "'Phase 2 database-backed tests'."
        )

    try:
        assert _current_revision(cfg) == PHASE3_STAGE1_HEAD_REVISION
        for table_name in _PHASE3_TABLES:
            assert _table_exists(table_name) is True, f"{table_name} should exist at head"
        assert _enum_values("announcement_audience") == [
            "all",
            "classroom",
            "teacher",
            "student",
        ]

        # Downgrade to Phase 2 head: every Phase 3 table must disappear
        # cleanly, with no leftover enum type blocking a future
        # re-creation, while Phase 2's own tables remain untouched.
        command.downgrade(cfg, PHASE2_HEAD_REVISION)
        assert _current_revision(cfg) == PHASE2_HEAD_REVISION
        for table_name in _PHASE3_TABLES:
            assert _table_exists(table_name) is False, f"{table_name} should be gone at Phase 2"
        assert _table_exists("users") is True
        assert _table_exists("refresh_sessions") is True
        assert _enum_values("announcement_audience") == []

        # Re-upgrade only to the Phase 3 revision under test.
        command.upgrade(cfg, PHASE3_STAGE1_HEAD_REVISION)
        assert _current_revision(cfg) == PHASE3_STAGE1_HEAD_REVISION
        for table_name in _PHASE3_TABLES:
            assert _table_exists(table_name) is True, f"{table_name} should exist after re-upgrade"
        assert _enum_values("announcement_audience") == [
            "all",
            "classroom",
            "teacher",
            "student",
        ]
    finally:
        # Always leave the schema at Phase 3 Stage 1 head, regardless
        # of whether the assertions above passed — every other
        # database-backed test in this session depends on these tables
        # existing.
        command.upgrade(cfg, "head")
