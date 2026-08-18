"""Tests for the centralized exception handlers (app/core/exceptions.py).

Phase 1 ships no business endpoints with request bodies to naturally
trigger a validation error or an internal error, so this file builds a
small, throwaway FastAPI app wired with the *same* handlers and
middleware the real app uses, and adds two deliberately-broken routes
purely to exercise those handlers. This never touches app.main's app
instance and adds no debug route to the real app.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.exceptions import EXCEPTION_HANDLERS, AppError
from app.core.middleware import RequestIDMiddleware


def _build_probe_app() -> FastAPI:
    probe_app = FastAPI()
    probe_app.add_middleware(RequestIDMiddleware)
    for exc_class, handler in EXCEPTION_HANDLERS.items():
        probe_app.add_exception_handler(exc_class, handler)

    @probe_app.get("/boom")
    async def boom() -> None:
        raise ValueError("simulated unexpected failure")

    @probe_app.get("/needs-int")
    async def needs_int(value: int) -> dict[str, int]:
        return {"value": value}

    @probe_app.get("/app-error")
    async def app_error() -> None:
        raise AppError("A safe application error.")

    @probe_app.get("/http-error")
    async def http_error() -> None:
        raise HTTPException(status_code=403, detail="Forbidden")

    return probe_app


@pytest.fixture()
def probe_client() -> Iterator[TestClient]:
    # raise_server_exceptions=False: defensive. Our registered `Exception`
    # handler should convert /boom's ValueError into a normal 500
    # JSONResponse before it ever reaches Starlette's outer
    # ServerErrorMiddleware, but if that assumption were ever wrong, this
    # makes the test fail on a clear assertion instead of crashing the
    # test process with an unhandled exception.
    with TestClient(_build_probe_app(), raise_server_exceptions=False) as test_client:
        yield test_client


def test_validation_error_follows_standard_envelope(probe_client: TestClient) -> None:
    response = probe_client.get("/needs-int", params={"value": "not-a-number"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"]["errors"]
    assert "request_id" in body


def test_unhandled_error_uses_generic_public_message(probe_client: TestClient) -> None:
    response = probe_client.get("/boom")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert body["error"]["message"] == "An unexpected error occurred. Please try again later."
    assert "simulated unexpected failure" not in body["error"]["message"]
    assert "ValueError" not in body["error"]["message"]


def test_unhandled_error_details_are_empty_not_a_traceback(probe_client: TestClient) -> None:
    body = probe_client.get("/boom").json()
    assert body["error"]["details"] == {}


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/boom", None),
        ("/needs-int", {"value": "not-a-number"}),
        ("/app-error", None),
        ("/http-error", None),
    ],
)
def test_request_id_present_in_headers_and_body_on_every_error(
    probe_client: TestClient,
    path: str,
    params: dict[str, str] | None,
) -> None:
    response = probe_client.get(path, params=params)
    assert "X-Request-ID" in response.headers
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_request_id_present_on_success_too(probe_client: TestClient) -> None:
    response = probe_client.get("/needs-int", params={"value": "5"})
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
