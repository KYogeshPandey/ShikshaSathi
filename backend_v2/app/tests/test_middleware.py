"""Tests for app.core.middleware.RequestIDMiddleware.

Exercises the pure ID-selection logic directly (fast, no app required)
and the full HTTP behavior through a small throwaway probe app: a
supplied valid ID is propagated, a missing ID is generated, and an
unsafe or oversized ID is replaced.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.middleware import RequestIDMiddleware, _extract_safe_request_id


@pytest.mark.parametrize("raw", ["a-valid-request-id-123", "ABC_123", "x" * 128])
def test_extract_safe_request_id_accepts_valid_values(raw: str) -> None:
    assert _extract_safe_request_id(raw) == raw


@pytest.mark.parametrize(
    "raw",
    [None, "", "x" * 129, "has spaces", "has/slash", "has\nnewline", "semi;colon"],
)
def test_extract_safe_request_id_replaces_invalid_values(raw: str | None) -> None:
    generated = _extract_safe_request_id(raw)
    assert generated != raw
    assert generated  # never empty


def _build_probe_app() -> FastAPI:
    probe_app = FastAPI()
    probe_app.add_middleware(RequestIDMiddleware, header_name="X-Request-ID")

    @probe_app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"status": "ok"}

    return probe_app


@pytest.fixture()
def probe_client() -> Iterator[TestClient]:
    with TestClient(_build_probe_app()) as test_client:
        yield test_client


def test_supplied_valid_request_id_is_propagated(probe_client: TestClient) -> None:
    response = probe_client.get("/ping", headers={"X-Request-ID": "caller-supplied-id"})
    assert response.headers["X-Request-ID"] == "caller-supplied-id"


def test_missing_request_id_is_generated(probe_client: TestClient) -> None:
    response = probe_client.get("/ping")
    assert response.headers["X-Request-ID"]


def test_each_request_without_an_id_gets_a_different_generated_id(
    probe_client: TestClient,
) -> None:
    first = probe_client.get("/ping").headers["X-Request-ID"]
    second = probe_client.get("/ping").headers["X-Request-ID"]
    assert first != second


def test_unsafe_request_id_is_replaced(probe_client: TestClient) -> None:
    unsafe = "not safe; drop table users"
    response = probe_client.get("/ping", headers={"X-Request-ID": unsafe})
    assert response.headers["X-Request-ID"] != unsafe


def test_oversized_request_id_is_replaced(probe_client: TestClient) -> None:
    oversized = "x" * 5000
    response = probe_client.get("/ping", headers={"X-Request-ID": oversized})
    returned = response.headers["X-Request-ID"]
    assert returned != oversized
    assert len(returned) < 200
