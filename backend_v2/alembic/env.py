"""Alembic environment configuration for backend_v2 (async SQLAlchemy).

The database URL is never hardcoded here or in alembic.ini — it is loaded
from the same validated application Settings the FastAPI app itself uses
(``app.core.config.get_settings()``), so there is exactly one source of
truth for ``DATABASE_URL`` and no credential is ever duplicated into
version-controlled Alembic configuration. Nothing in this file prints or
logs the resolved URL.
"""

from __future__ import annotations

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Ensure `backend_v2/` (the parent of this `alembic/` directory) is
# importable regardless of how the `alembic` command was invoked. Belt
# and suspenders alongside alembic.ini's `prepend_sys_path = .`.
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import (
    Announcement,
    AnnouncementClassroom,
    AttendanceRecord,
    AuditLog,
    BiometricEnrollment,
    BiometricSample,
    Classroom,
    RefreshSession,
    StudentProfile,
    Subject,
    TeacherAssignment,
    TeacherProfile,
    TimetableEntry,
    User,
)

# This is the Alembic Config object, providing access to values within
# the .ini file in use.
config = context.config

# Interpret the config file for Python logging; sets up loggers.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import the Phase 2 + Phase 3 + Phase 4 + Phase 5 Stage 2 models above
# before exposing Base.metadata so Alembic autogenerate sees the
# complete users/auth/academics/profiles/announcements/attendance/
# biometric-enrollment schema.
_registered_models = (
    User,
    RefreshSession,
    Classroom,
    Subject,
    TeacherProfile,
    StudentProfile,
    TeacherAssignment,
    TimetableEntry,
    Announcement,
    AnnouncementClassroom,
    AttendanceRecord,
    AuditLog,
    BiometricEnrollment,
    BiometricSample,
)
target_metadata = Base.metadata

# Inject the real database URL from validated application settings.
config.set_main_option("sqlalchemy.url", get_settings().DATABASE_URL)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emits SQL; no live DB connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations against a live connection."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a real, live database."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
