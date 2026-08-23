"""Round-trip verification for the sole Phase 5 Stage 4 migration."""

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
STAGE3_HEAD = "d22bce264ecd"
STAGE4_HEAD = "4f8c1a6e92b7"
_TABLE = "recognition_attendance_attempts"
_ENUM = "recognition_attendance_decision"


def _config() -> Config:
    cfg = Config(str(_BACKEND_V2_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_V2_ROOT / "alembic"))
    return cfg


def _scalar(sql: str, params: dict[str, object] | None = None):
    async def _read():
        engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                return (await connection.execute(text(sql), params or {})).scalar()
        finally:
            await engine.dispose()

    return asyncio.run(_read())


def _revision() -> str | None:
    return _scalar("SELECT version_num FROM alembic_version")


def _table_exists() -> bool:
    return _scalar("SELECT to_regclass(:name)", {"name": _TABLE}) is not None


def _enum_exists() -> bool:
    return bool(
        _scalar(
            "SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = :name)",
            {"name": _ENUM},
        )
    )


def _identifiers_fit_postgresql_limit() -> bool:
    return bool(
        _scalar(
            """
            SELECT COALESCE(
                bool_and(length(identifier) <= current_setting('max_identifier_length')::int),
                false
            )
            FROM (
                SELECT conname AS identifier
                FROM pg_constraint
                WHERE conrelid = to_regclass(:table_name)
                UNION ALL
                SELECT indexname AS identifier
                FROM pg_indexes
                WHERE schemaname = current_schema() AND tablename = :table_name
            ) AS identifiers
            """,
            {"table_name": _TABLE},
        )
    )


def test_phase5_stage4_migration_round_trip() -> None:
    cfg = _config()
    try:
        command.upgrade(cfg, "head")
    except (ModuleNotFoundError, SQLAlchemyError, OSError) as exc:
        pytest.skip(f"PostgreSQL migration environment unavailable: {type(exc).__name__}")
        return

    try:
        command.downgrade(cfg, STAGE4_HEAD)
        assert _revision() == STAGE4_HEAD
        assert _table_exists() is True
        assert _enum_exists() is True
        assert _identifiers_fit_postgresql_limit() is True

        command.downgrade(cfg, STAGE3_HEAD)
        assert _revision() == STAGE3_HEAD
        assert _table_exists() is False
        assert _enum_exists() is False
        assert _scalar("SELECT to_regclass('biometric_embeddings')") is not None
        assert _scalar("SELECT to_regclass('attendance_records')") is not None

        command.upgrade(cfg, STAGE4_HEAD)
        assert _revision() == STAGE4_HEAD
        assert _table_exists() is True
        assert _enum_exists() is True
        assert _identifiers_fit_postgresql_limit() is True
    finally:
        command.upgrade(cfg, "head")
