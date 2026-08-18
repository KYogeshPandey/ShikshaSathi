"""Tests for ``POST /api/v1/auth/login``.

Uses ``client_db`` (app/tests/conftest.py): an HTTP client wired to the
same real, per-test-isolated database session as ``db_session``, so a
test can seed a user directly via the repository and then exercise the
real endpoint against it.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.security import hash_password
from app.modules.users.models import UserRole
from app.modules.users.normalization import normalize_email
from app.modules.users.repository import UserRepository

_LOGIN_URL = "/api/v1/auth/login"
_PASSWORD = "a-strong-real-password-1"


async def _seed_user(
    db_session: AsyncSession, *, email: str, is_active: bool = True, password: str = _PASSWORD
) -> None:
    repo = UserRepository(db_session)
    await repo.create(
        email=normalize_email(email),
        password_hash=hash_password(password),
        full_name="Login Test User",
        role=UserRole.TEACHER,
        is_active=is_active,
    )
    await db_session.commit()


async def test_successful_login_returns_user_and_access_token(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_user(db_session, email="login-ok@example.com")

    response = await client_db.post(
        _LOGIN_URL, json={"email": "login-ok@example.com", "password": _PASSWORD}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "login-ok@example.com"
    assert "password_hash" not in body["user"]
    assert body["token"]["access_token"]
    assert body["token"]["token_type"] == "bearer"
    assert body["token"]["expires_in"] > 0

    set_cookie = response.headers.get("set-cookie", "")
    assert "refresh_token=" in set_cookie
    assert "HttpOnly" in set_cookie


async def test_login_with_wrong_password_returns_401(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_user(db_session, email="wrong-pw@example.com")

    response = await client_db.post(
        _LOGIN_URL, json={"email": "wrong-pw@example.com", "password": "totally-wrong-1"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_login_with_unknown_email_returns_401_same_as_wrong_password(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_user(db_session, email="known@example.com")

    unknown_response = await client_db.post(
        _LOGIN_URL, json={"email": "does-not-exist@example.com", "password": _PASSWORD}
    )
    wrong_password_response = await client_db.post(
        _LOGIN_URL, json={"email": "known@example.com", "password": "totally-wrong-1"}
    )

    # Same status, code, and message either way — no account-enumeration
    # signal (instruction B/K).
    assert unknown_response.status_code == wrong_password_response.status_code == 401
    assert (
        unknown_response.json()["error"]["code"]
        == wrong_password_response.json()["error"]["code"]
        == "INVALID_CREDENTIALS"
    )
    assert (
        unknown_response.json()["error"]["message"]
        == wrong_password_response.json()["error"]["message"]
    )


async def test_login_with_deactivated_account_returns_401(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_user(db_session, email="deactivated@example.com", is_active=False)

    response = await client_db.post(
        _LOGIN_URL, json={"email": "deactivated@example.com", "password": _PASSWORD}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_login_normalizes_email_case_before_lookup(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_user(db_session, email="case-test@example.com")

    response = await client_db.post(
        _LOGIN_URL, json={"email": "Case-Test@Example.com", "password": _PASSWORD}
    )
    assert response.status_code == 200


async def test_login_malformed_request_missing_password_returns_422(
    client_db: AsyncClient,
) -> None:
    response = await client_db.post(_LOGIN_URL, json={"email": "someone@example.com"})
    assert response.status_code == 422


async def test_login_malformed_request_invalid_email_returns_422(
    client_db: AsyncClient,
) -> None:
    response = await client_db.post(
        _LOGIN_URL, json={"email": "not-an-email", "password": _PASSWORD}
    )
    assert response.status_code == 422


async def test_login_response_carries_request_id_header(client_db: AsyncClient) -> None:
    # Preserves Phase 1's request-ID-on-every-response contract even for
    # a 422 validation failure from this new router (Phase 2 brief,
    # instruction 8: "Preserve the existing error envelope, request-ID
    # behavior...").
    response = await client_db.post(_LOGIN_URL, json={"email": "not-an-email", "password": "x"})
    assert response.headers.get("X-Request-ID")
    assert response.json()["request_id"]
