"""Phase 9 production-boundary regression tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from app.core.middleware import (
    LoginAttemptLimiter,
    LoginRateLimitMiddleware,
    RequestIDMiddleware,
)


def _build_rate_limited_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        LoginRateLimitMiddleware,
        login_path="/api/v1/auth/login",
        max_attempts=2,
        window_seconds=60,
    )
    app.add_middleware(RequestIDMiddleware)

    @app.post("/api/v1/auth/login")
    async def login() -> dict[str, str]:
        return {"status": "attempted"}

    @app.post("/api/v1/other")
    async def other() -> dict[str, str]:
        return {"status": "ok"}

    return app


@pytest.fixture()
def rate_limited_client() -> Iterator[TestClient]:
    with TestClient(_build_rate_limited_app()) as client:
        yield client


def test_login_rate_limit_returns_standard_429_envelope(
    rate_limited_client: TestClient,
) -> None:
    assert rate_limited_client.post("/api/v1/auth/login").status_code == status.HTTP_200_OK
    assert rate_limited_client.post("/api/v1/auth/login").status_code == status.HTTP_200_OK

    response = rate_limited_client.post("/api/v1/auth/login")

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.json()["error"] == {
        "code": "RATE_LIMIT_EXCEEDED",
        "message": "Too many login attempts. Please try again later.",
        "details": {},
    }
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    assert int(response.headers["Retry-After"]) >= 1


def test_login_rate_limit_does_not_count_other_routes(
    rate_limited_client: TestClient,
) -> None:
    for _ in range(5):
        assert rate_limited_client.post("/api/v1/other").status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_login_rate_limit_window_expires() -> None:
    current_time = [100.0]
    limiter = LoginAttemptLimiter(
        max_attempts=2,
        window_seconds=60,
        clock=lambda: current_time[0],
    )

    assert await limiter.check("client") is None
    assert await limiter.check("client") is None
    assert await limiter.check("client") == 60

    current_time[0] = 161.0
    assert await limiter.check("client") is None
