"""Round-trip test for the Phase 5 Stage 2 migration (biometric enrollment).

Mirrors ``app.tests.test_migrations_phase4`` exactly (same sync-test,
self-restoring-``finally`` rationale — see that file's docstring, not
repeated here). Downgrades to Phase 4 head (``e1208296dad5``), not all
the way to the Phase 3 baseline, since this migration's *parent* is
Phase 4 head, not the Phase 3 baseline.
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

PHASE4_HEAD_REVISION = "e1208296dad5"
PHASE5_STAGE2_HEAD_REVISION = "ca8e748dc8f2"

_PHASE5_STAGE2_TABLES = (
    "biometric_enrollments",
    "biometric_samples",
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


def test_phase5_stage2_migration_round_trip() -> None:
    """Round-trips ``ca8e748dc8f2`` (create biometric enrollment tables)
    down to the Phase 4 head, ``e1208296dad5``, and back up again.

    Deliberately does **not** assume ``"head"`` equals this stage's own
    revision anywhere it matters for the assertions below — a later
    stage's migration(s) may already have been added on top by the time
    this test runs, and this test must keep passing unmodified when that
    happens. Every assertion moves to ``PHASE5_STAGE2_HEAD_REVISION``
    explicitly instead of relying on "head" — the first such move starts
    from true head and is a *downgrade* whenever a later stage's
    migration already sits on top of Stage 2's, and a plain no-op/upgrade
    only for as long as Stage 2 happens to still be the true head — and
    the schema is always left at the true latest "head" afterward (not
    this stage's own revision) in the ``finally`` block, since every
    other database-backed test in this session depends on tables from
    every migration — including any added after this one — existing.
    """
    cfg = _alembic_config()

    try:
        # The Docker test workflow already runs `alembic upgrade head`
        # before pytest; running it again here makes this test
        # self-contained for anyone running pytest directly too.
        command.upgrade(cfg, "head")
    except (ModuleNotFoundError, SQLAlchemyError) as exc:
        pytest.skip(
            "Postgres/asyncpg unavailable in this sandbox (no network egress, no "
            f"installed dependencies) — see docs/PROGRESS.md. Original error: {exc}"
        )
        return

    try:
        # Move explicitly to this stage's own revision for the Stage 2
        # assertions below, regardless of where "head" now sits. Once a
        # later stage adds a migration on top, Stage 2 is an ancestor of
        # true head, so getting there from head is a downgrade, not an
        # upgrade.
        command.downgrade(cfg, PHASE5_STAGE2_HEAD_REVISION)
        assert _current_revision(cfg) == PHASE5_STAGE2_HEAD_REVISION
        for table_name in _PHASE5_STAGE2_TABLES:
            assert _table_exists(table_name) is True, f"{table_name} should exist at Stage 2 head"
        assert _enum_values("biometric_enrollment_status") == [
            "pending",
            "active",
            "deletion_pending",
            "deleted",
        ]
        assert _enum_values("biometric_sample_status") == [
            "pending",
            "active",
            "replacement_pending",
            "deletion_pending",
            "quarantined",
            "deleted",
        ]
        assert _enum_values("biometric_recognition_processing_state") == [
            "pending_processing",
            "processed",
            "processing_failed",
        ]

        # Downgrade to Phase 4 head: both Stage 2 tables must disappear
        # cleanly, with no leftover enum type blocking a future
        # re-creation, while every Phase 1-4 table remains untouched.
        command.downgrade(cfg, PHASE4_HEAD_REVISION)
        assert _current_revision(cfg) == PHASE4_HEAD_REVISION
        for table_name in _PHASE5_STAGE2_TABLES:
            assert _table_exists(table_name) is False, (
                f"{table_name} should not exist after downgrade to Phase 4 head"
            )
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
            "attendance_records",
            "audit_logs",
        ):
            assert _table_exists(preserved_table) is True, (
                f"{preserved_table} should still exist after downgrading to Phase 4 head"
            )
        assert _enum_values("biometric_enrollment_status") == []
        assert _enum_values("biometric_sample_status") == []
        assert _enum_values("biometric_recognition_processing_state") == []
        # Phase 4's own enums must be untouched by this migration's downgrade.
        assert _enum_values("attendance_status") == ["present", "absent"]
        assert _enum_values("audit_outcome") == ["success", "blocked"]

        # Re-upgrade specifically to this stage's own revision — not
        # "head" — so this assertion remains meaningful even after a
        # later stage adds a migration on top of Stage 2's.
        command.upgrade(cfg, PHASE5_STAGE2_HEAD_REVISION)
        assert _current_revision(cfg) == PHASE5_STAGE2_HEAD_REVISION
        for table_name in _PHASE5_STAGE2_TABLES:
            assert _table_exists(table_name) is True, (
                f"{table_name} should exist again after re-upgrade to Stage 2 head"
            )
        assert _enum_values("biometric_enrollment_status") == [
            "pending",
            "active",
            "deletion_pending",
            "deleted",
        ]
        assert _enum_values("biometric_sample_status") == [
            "pending",
            "active",
            "replacement_pending",
            "deletion_pending",
            "quarantined",
            "deleted",
        ]
        assert _enum_values("biometric_recognition_processing_state") == [
            "pending_processing",
            "processed",
            "processing_failed",
        ]
    finally:
        # Always leave the schema at the true latest head, regardless of
        # whether the assertions above passed or this stage is the
        # newest migration that exists yet.
        command.upgrade(cfg, "head")
