"""Round-trip test for the Phase 4 Stage 1 migration (attendance + audit log).

The true Alembic head may be later than Phase 4. Move explicitly to the
revision under test, round-trip its direct parent, then restore the true
latest head so later migration tests and DB-backed tests remain usable.
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

PHASE3_HEAD_REVISION = "32819e0a6027"
PHASE4_STAGE1_HEAD_REVISION = "e1208296dad5"

_PHASE4_TABLES = (
    "attendance_records",
    "audit_logs",
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


def test_phase4_stage1_migration_round_trip() -> None:
    cfg = _alembic_config()

    try:
        # The Docker test workflow already runs `alembic upgrade head`
        # before pytest; running it again here makes this test
        # self-contained for anyone running pytest directly too.
        command.upgrade(cfg, "head")
    except (ModuleNotFoundError, SQLAlchemyError) as exc:
        pytest.skip(
            "Skipping Phase 4 migration round-trip test: no reachable PostgreSQL "
            f"test database ({type(exc).__name__}). See backend_v2/README.md "
            "'Phase 2 database-backed tests'."
        )

    try:
        # A later Phase 5 migration may be the true head. Reach the Phase 4
        # revision explicitly instead of assuming ``head`` still means it.
        command.downgrade(cfg, PHASE4_STAGE1_HEAD_REVISION)
        assert _current_revision(cfg) == PHASE4_STAGE1_HEAD_REVISION
        for table_name in _PHASE4_TABLES:
            assert _table_exists(table_name) is True, f"{table_name} should exist at head"
        assert _enum_values("attendance_status") == ["present", "absent"]
        assert _enum_values("audit_outcome") == ["success", "blocked"]

        # Downgrade to Phase 3 head: both Phase 4 tables must disappear
        # cleanly, with no leftover enum type blocking a future
        # re-creation, while every Phase 1-3 table remains untouched.
        command.downgrade(cfg, PHASE3_HEAD_REVISION)
        assert _current_revision(cfg) == PHASE3_HEAD_REVISION
        for table_name in _PHASE4_TABLES:
            assert _table_exists(table_name) is False, f"{table_name} should be gone at Phase 3"
        for preserved_table in (
            "users",
            "refresh_sessions",
            "classrooms",
            "subjects",
            "teacher_profiles",
            "student_profiles",
            "teacher_assignments",
            "timetable_entries",
            "announcements",
            "announcement_classrooms",
        ):
            assert _table_exists(preserved_table) is True, (
                f"{preserved_table} should still exist after downgrading to Phase 3 head"
            )
        assert _enum_values("attendance_status") == []
        assert _enum_values("audit_outcome") == []
        # Phase 3's own enums must be untouched by this migration's downgrade.
        assert _enum_values("announcement_audience") == [
            "all",
            "classroom",
            "teacher",
            "student",
        ]

        # Re-upgrade specifically to the Phase 4 revision under test.
        command.upgrade(cfg, PHASE4_STAGE1_HEAD_REVISION)
        assert _current_revision(cfg) == PHASE4_STAGE1_HEAD_REVISION
        for table_name in _PHASE4_TABLES:
            assert _table_exists(table_name) is True, f"{table_name} should exist after re-upgrade"
        assert _enum_values("attendance_status") == ["present", "absent"]
        assert _enum_values("audit_outcome") == ["success", "blocked"]
    finally:
        # Always restore the true latest schema; later Phase 5 tests depend
        # on migrations added after this Phase 4 checkpoint.
        command.upgrade(cfg, "head")
