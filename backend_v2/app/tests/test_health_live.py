"""Tests for GET /health/live.

Liveness must succeed regardless of database state — it never depends on
the database at all (see app/api/routes/health.py).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_liveness_returns_200(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200


def test_liveness_returns_expected_body(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.json() == {"status": "alive"}


def test_liveness_does_not_require_a_database_override(client: TestClient) -> None:
    # Deliberately requests neither the `database_ready` nor the
    # `database_unavailable` fixture. The dummy DATABASE_URL from
    # conftest.py points at nothing reachable — if liveness touched the
    # database in any way this would fail or hang instead of returning
    # 200 immediately.
    response = client.get("/health/live")
    assert response.status_code == 200
