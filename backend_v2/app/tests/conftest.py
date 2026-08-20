"""Shared pytest fixtures for backend_v2.

Test-only environment bootstrap: importing ``app.main`` triggers
``Settings()`` construction at module level (``app.main``: ``app =
create_app()``), and ``Settings`` deliberately has no fallback defaults
for secrets/DB config (see app/core/config.py) — that fail-fast behavior
is intentional for real deployments. For this test suite specifically, we
set safe, obviously-fake values via ``os.environ.setdefault`` *before*
importing ``app.main``, so the whole suite runs without a real ``.env``,
a real secret, or (for Phase 1's tests) a reachable PostgreSQL instance.
``setdefault`` is used deliberately (not a hard assignment) so a
developer who *does* have a real local Postgres configured via real
environment variables can still run this suite against it unmodified.
None of the values below are real credentials.

Phase 5 Stage 2 additionally sets ``BIOMETRIC_STORAGE_ROOT`` to a fresh
``tempfile.mkdtemp()`` directory for the same reason: storage/
reconciliation tests write real files, and this keeps them isolated to
one throwaway directory per test session instead of the default
``var/biometric_data``.

Phase 2 added ``db_session`` / ``client_db`` (below), which need an
actually-reachable PostgreSQL test database with migrations through the
current Phase 3 head applied. See "database-backed test fixtures" below for
exactly how that database is isolated and cleaned between tests, and
backend_v2/README.md's "Phase 2 database-backed tests" section for how
to run them (the authoritative path is
``docker compose --profile test run --build --rm backend_v2_test``, which wires
DATABASE_URL to an isolated, ephemeral ``postgres_test`` service and
runs ``alembic upgrade head`` before pytest — see docker-compose.yml).
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.exceptions import DatabaseUnavailableError
from app.db.session import get_db_session, require_database_ready

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("APP_NAME", "ShikshaSathi API (test)")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("SECRET_KEY", "test-only-secret-key-not-a-real-credential-000")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://test_user:test_password@localhost:5432/shikshasathi_test",
)
os.environ.setdefault("POSTGRES_DB", "shikshasathi_test")
os.environ.setdefault("POSTGRES_USER", "test_user")
os.environ.setdefault("POSTGRES_PASSWORD", "test_password")
os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
# The limiter itself has dedicated low-threshold tests. Keep the shared app's
# process-wide counter from coupling otherwise-independent authentication
# integration tests to execution order.
os.environ.setdefault("LOGIN_RATE_LIMIT_ATTEMPTS", "1000")
# Secure cookies require HTTPS; TestClient / httpx talk plain HTTP.
os.environ.setdefault("REFRESH_TOKEN_COOKIE_SECURE", "false")
# Phase 5 Stage 2: isolate biometric file storage to a throwaway temp
# directory for the whole test session, instead of the default
# `var/biometric_data` (relative to CWD) — keeps every storage/
# reconciliation test hermetic and leaves nothing behind in the repo.
os.environ.setdefault(
    "BIOMETRIC_STORAGE_ROOT", tempfile.mkdtemp(prefix="shikshasathi-test-biometric-")
)

from app.main import app as fastapi_app


@pytest.fixture()
def app() -> Iterator[FastAPI]:
    """The shared app instance; dependency overrides are reset after every test."""
    yield fastapi_app
    fastapi_app.dependency_overrides.clear()


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def database_ready(app: FastAPI) -> None:
    """Override the readiness check so it succeeds without a real database."""

    async def _ok() -> None:
        return None

    app.dependency_overrides[require_database_ready] = _ok


@pytest.fixture()
def database_unavailable(app: FastAPI) -> None:
    """Override the readiness check so it fails without a real database."""

    async def _fail() -> None:
        raise DatabaseUnavailableError()

    app.dependency_overrides[require_database_ready] = _fail


# ---------------------------------------------------------------------------
# Phase 2/3: database-backed test fixtures
# ---------------------------------------------------------------------------
#
# ``db_session`` intentionally builds its own engine with ``NullPool``
# (never reusing the module-level cached engine in app/db/session.py)
# and disposes it at the end of every single test. This sidesteps a
# well-known class of bug where an asyncpg connection pool created
# under one asyncio event loop is later reused from a different loop —
# pytest-asyncio's default event-loop scope is per-test-function, so a
# long-lived, cross-test engine is exactly the failure mode to avoid
# here. The small per-test connection overhead is an acceptable trade
# for tests that are simple to reason about and independently
# repeatable (instruction J/K).
#
# Cleanup: after each test's session is closed, every row is deleted
# from every Phase 2 + Phase 3 + Phase 4 + Phase 5 Stage 2 table via a
# fresh autocommitting connection, in strict child-before-parent order
# (respecting every foreign key below), so the next test always starts
# from an empty, migrated schema:
#
#   biometric_samples        -> biometric_enrollments, users (RESTRICT),
#                                biometric_samples (self, SET NULL via
#                                previous_sample_id)
#   biometric_enrollments    -> student_profiles (CASCADE), users (RESTRICT
#                                via created_by_user_id, SET NULL via
#                                deletion_requested_by_user_id)
#   audit_logs                -> users (RESTRICT), classrooms/subjects (SET NULL)
#   attendance_records         -> student_profiles, classrooms, subjects (CASCADE),
#                                 users (RESTRICT, via marked_by_user_id)
#   announcement_classrooms  -> announcements, classrooms
#   announcements            -> users
#   timetable_entries        -> classrooms, subjects, teacher_profiles
#   teacher_assignments      -> teacher_profiles, classrooms, subjects
#   student_profiles         -> users, classrooms (SET NULL, order-safe either way)
#   teacher_profiles         -> users
#   subjects                 -> (no FK dependents left to clear first)
#   classrooms                -> (no FK dependents left to clear first)
#   refresh_sessions          -> users
#   users                     -> (root of the FK graph, deleted last)
_PHASE2_AND_PHASE3_TABLES_CHILD_FIRST: tuple[str, ...] = (
    # Phase 5 Stage 4: attempts reference users, classroom/subject,
    # student profiles, and (after a mark) attendance_records.
    "recognition_attendance_attempts",
    # Phase 5 Stage 3: biometric_embeddings FKs to biometric_samples,
    # so it must be deleted first.
    "biometric_embeddings",
    "biometric_samples",
    "biometric_enrollments",
    "audit_logs",
    "attendance_records",
    "announcement_classrooms",
    "announcements",
    "timetable_entries",
    "teacher_assignments",
    "student_profiles",
    "teacher_profiles",
    "subjects",
    "classrooms",
    "refresh_sessions",
    "users",
)


@pytest_asyncio.fixture()
async def db_session() -> AsyncIterator[AsyncSession]:
    settings = get_settings()
    engine: AsyncEngine | None = None

    try:
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:
        if engine is not None:
            await engine.dispose()
        pytest.skip(
            "Skipping database-backed test: no reachable PostgreSQL "
            f"test database ({type(exc).__name__}). Run `docker compose "
            "--profile test run --rm backend_v2_test`, or start "
            "`postgres_test` and run `alembic upgrade head` before running "
            "pytest directly — see backend_v2/README.md."
        )

    assert engine is not None
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as connection:
        for table_name in _PHASE2_AND_PHASE3_TABLES_CHILD_FIRST:
            await connection.execute(text(f"DELETE FROM {table_name}"))
    await engine.dispose()


@pytest_asyncio.fixture()
async def client_db(app: FastAPI, db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """Async HTTP client sharing this test's session in one event loop.

    ``ASGITransport`` runs the FastAPI app in pytest-asyncio's current
    loop. That keeps HTTP handling and the asyncpg-backed ``db_session``
    on the same event loop and avoids cross-loop connection errors.
    """

    async def _override_get_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = _override_get_db_session
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db_session, None)
