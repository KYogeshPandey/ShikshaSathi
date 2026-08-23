"""Round-trip the additive Milestone 4 review and OTP migrations."""

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

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_ATTEMPT_REVISION = "4f8c1a6e92b7"
_REVIEW_REVISION = "b41f6d91a2c3"
_OTP_REVISION = "c52d7a40e8f1"


def _config() -> Config:
    config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    return config


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


def _table_exists(name: str) -> bool:
    return _scalar("SELECT to_regclass(:name)", {"name": name}) is not None


def _column_exists(table: str, column: str) -> bool:
    return bool(
        _scalar(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = :table_name
                  AND column_name = :column_name
            )
            """,
            {"table_name": table, "column_name": column},
        )
    )


def _enum_exists(name: str) -> bool:
    return bool(
        _scalar(
            "SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = :name)",
            {"name": name},
        )
    )


def test_milestone4_migrations_upgrade_downgrade_and_restore_head() -> None:
    config = _config()
    try:
        command.upgrade(config, "head")
    except (ModuleNotFoundError, SQLAlchemyError, OSError) as exc:
        pytest.skip(f"PostgreSQL migration environment unavailable: {type(exc).__name__}")
        return

    try:
        assert _revision() == _OTP_REVISION
        assert _table_exists("recognition_attendance_reviews")
        assert _column_exists("recognition_attendance_attempts", "review_id")
        assert _table_exists("otp_challenges")
        assert _enum_exists("otp_purpose")

        command.downgrade(config, _REVIEW_REVISION)
        assert _revision() == _REVIEW_REVISION
        assert _table_exists("recognition_attendance_reviews")
        assert not _table_exists("otp_challenges")
        assert not _enum_exists("otp_purpose")

        command.downgrade(config, _ATTEMPT_REVISION)
        assert _revision() == _ATTEMPT_REVISION
        assert not _table_exists("recognition_attendance_reviews")
        assert not _column_exists("recognition_attendance_attempts", "review_id")
        assert _table_exists("recognition_attendance_attempts")

        command.upgrade(config, "head")
        assert _revision() == _OTP_REVISION
        assert _table_exists("recognition_attendance_reviews")
        assert _table_exists("otp_challenges")
    finally:
        command.upgrade(config, "head")
