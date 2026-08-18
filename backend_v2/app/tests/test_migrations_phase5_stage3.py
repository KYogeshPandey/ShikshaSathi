"""Round-trip test for the Phase 5 Stage 3 migration (biometric embeddings
+ sample processing-bookkeeping columns).

Mirrors ``app.tests.test_migrations_phase5_stage2`` exactly (same
sync-test, self-restoring-``finally`` rationale, and same "always reach
this stage's own revision via an explicit move rather than assuming
'head' still equals it" reasoning — see that file's docstring, not
repeated here in full).

**Direction note (this test's own addition over the Stage 2 template):**
the move from wherever ``upgrade(cfg, "head")`` lands to
``PHASE5_STAGE3_HEAD_REVISION`` is performed via ``command.downgrade``,
never ``command.upgrade``, and deliberately not via a blind
``command.upgrade(cfg, PHASE5_STAGE3_HEAD_REVISION)`` call. ``d22bce264ecd``
is this repository's current true ``head`` as of Stage 3, so that move
is a no-op today — but the day a Stage 4 migration is added on top,
``head`` will sit *above* this revision, and only ``downgrade`` (not
``upgrade``) is the correct direction to reach it again. Alembic's
``downgrade`` command is itself a safe no-op when the requested target
already equals the current revision, so this one call is correct in
both cases without this test needing to detect which case it is in.
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

PHASE5_STAGE2_HEAD_REVISION = "ca8e748dc8f2"
PHASE5_STAGE3_HEAD_REVISION = "d22bce264ecd"

_PHASE5_STAGE3_NEW_TABLES = ("biometric_embeddings",)
_PHASE5_STAGE3_NEW_SAMPLE_COLUMNS = (
    "processing_started_at",
    "processing_completed_at",
    "processing_failure_reason_code",
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


def _sample_column_exists(column_name: str) -> bool:
    async def _check() -> bool:
        engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(
                    text(
                        """
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'biometric_samples' AND column_name = :column_name
                        """
                    ),
                    {"column_name": column_name},
                )
                return result.first() is not None
        finally:
            await engine.dispose()

    return asyncio.run(_check())


def test_phase5_stage3_migration_round_trip() -> None:
    """Round-trips ``d22bce264ecd`` (biometric_embeddings + processing
    columns) down to the Stage 2 head, ``ca8e748dc8f2``, and back up
    again, following the exact 8-step sequence:

    1. upgrade to the true latest head
    2. move explicitly to the Stage 3 revision (downgrade or no-op,
       never a blind upgrade — see this file's module docstring)
    3. assert Stage 3 schema present
    4. downgrade to Stage 2 head (``ca8e748dc8f2``)
    5. assert Stage 3 schema gone, Stage 2 schema intact
    6. upgrade specifically back to the Stage 3 revision
    7. reassert Stage 3 schema present
    8. restore latest head in ``finally``
    """
    cfg = _alembic_config()

    try:
        # Step 1: true latest head (the Docker test workflow already runs
        # this before pytest; repeated here so this test is self-contained
        # when run directly too).
        command.upgrade(cfg, "head")
    except (ModuleNotFoundError, SQLAlchemyError) as exc:
        pytest.skip(
            "Postgres/asyncpg unavailable in this sandbox (no network egress, no "
            f"installed dependencies) — see docs/PROGRESS.md. Original error: {exc}"
        )
        return

    try:
        # Step 2: move explicitly to the Stage 3 revision under test.
        command.downgrade(cfg, PHASE5_STAGE3_HEAD_REVISION)
        assert _current_revision(cfg) == PHASE5_STAGE3_HEAD_REVISION

        # Step 3: assert Stage 3 schema.
        for table_name in _PHASE5_STAGE3_NEW_TABLES:
            assert _table_exists(table_name) is True, f"{table_name} should exist at Stage 3 head"
        for column_name in _PHASE5_STAGE3_NEW_SAMPLE_COLUMNS:
            assert _sample_column_exists(column_name) is True, (
                f"biometric_samples.{column_name} should exist at Stage 3 head"
            )
        # Stage 2's own tables must still be present (Stage 3 is additive).
        assert _table_exists("biometric_enrollments") is True
        assert _table_exists("biometric_samples") is True

        # Step 4: downgrade to Stage 2 head.
        command.downgrade(cfg, PHASE5_STAGE2_HEAD_REVISION)
        assert _current_revision(cfg) == PHASE5_STAGE2_HEAD_REVISION

        # Step 5: Stage 3 schema gone, Stage 2 schema intact.
        for table_name in _PHASE5_STAGE3_NEW_TABLES:
            assert _table_exists(table_name) is False, (
                f"{table_name} should not exist after downgrade to Stage 2 head"
            )
        for column_name in _PHASE5_STAGE3_NEW_SAMPLE_COLUMNS:
            assert _sample_column_exists(column_name) is False, (
                f"biometric_samples.{column_name} should not exist after downgrade to Stage 2 head"
            )
        assert _table_exists("biometric_enrollments") is True
        assert _table_exists("biometric_samples") is True
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
                f"{preserved_table} should still exist after downgrading to Stage 2 head"
            )

        # Step 6: upgrade specifically back to the Stage 3 revision.
        command.upgrade(cfg, PHASE5_STAGE3_HEAD_REVISION)
        assert _current_revision(cfg) == PHASE5_STAGE3_HEAD_REVISION

        # Step 7: reassert Stage 3 schema.
        for table_name in _PHASE5_STAGE3_NEW_TABLES:
            assert _table_exists(table_name) is True, (
                f"{table_name} should exist again after re-upgrade to Stage 3 head"
            )
        for column_name in _PHASE5_STAGE3_NEW_SAMPLE_COLUMNS:
            assert _sample_column_exists(column_name) is True, (
                f"biometric_samples.{column_name} should exist again after re-upgrade to "
                "Stage 3 head"
            )
    finally:
        # Step 8: always leave the schema at the true latest head.
        command.upgrade(cfg, "head")
