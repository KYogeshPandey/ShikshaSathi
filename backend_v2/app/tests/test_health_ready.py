"""Tests for GET /health/ready.

Covers the HTTP-level contract (via TestClient + dependency overrides, no
real Postgres needed) and the underlying ``require_database_ready``
dependency directly as a coroutine (exercising pytest-asyncio, via
monkeypatching ``ping_database`` rather than the HTTP layer).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.exceptions import DatabaseUnavailableError
from app.db.session import require_database_ready

_TEST_SETTINGS_KWARGS: dict[str, Any] = {
    "_env_file": None,
    "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
    "POSTGRES_DB": "db",
    "POSTGRES_USER": "user",
    "POSTGRES_PASSWORD": "pass",
    "SECRET_KEY": "a" * 40,
}


def test_readiness_returns_ready_when_database_check_succeeds(
    client: TestClient, database_ready: None
) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ready"}}


def test_readiness_returns_503_when_database_check_fails(
    client: TestClient, database_unavailable: None
) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 503


def test_readiness_failure_body_is_sanitized(
    client: TestClient, database_unavailable: None
) -> None:
    body = client.get("/health/ready").json()
    assert body["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert body["error"]["details"] == {}
    assert "traceback" not in body["error"]["message"].lower()


def test_readiness_failure_contains_request_id(
    client: TestClient, database_unavailable: None
) -> None:
    response = client.get("/health/ready")
    body = response.json()
    assert body["request_id"]
    assert response.headers["X-Request-ID"]
    assert body["request_id"] == response.headers["X-Request-ID"]


def test_readiness_failure_does_not_leak_database_url(
    client: TestClient, database_unavailable: None
) -> None:
    body_text = client.get("/health/ready").text
    # The dummy DATABASE_URL set in conftest.py; if any part of it (host,
    # user, password) ever leaked into the response, this would catch it.
    assert "test_password" not in body_text
    assert "test_user" not in body_text
    assert "localhost:5432" not in body_text


async def test_require_database_ready_raises_on_ping_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _boom(_settings: Settings) -> None:
        raise ConnectionError("simulated driver failure")

    monkeypatch.setattr("app.db.session.ping_database", _boom)

    settings = Settings(**_TEST_SETTINGS_KWARGS)

    with pytest.raises(DatabaseUnavailableError):
        await require_database_ready(settings)


async def test_require_database_ready_succeeds_when_ping_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _ok(_settings: Settings) -> None:
        return None

    monkeypatch.setattr("app.db.session.ping_database", _ok)

    settings = Settings(**_TEST_SETTINGS_KWARGS)

    await require_database_ready(settings)  # must not raise
