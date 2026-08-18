"""Tests for ``POST /api/v1/auth/logout``."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.repository import RefreshSessionRepository
from app.modules.auth.security import hash_password, hash_refresh_token
from app.modules.users.models import UserRole
from app.modules.users.normalization import normalize_email
from app.modules.users.repository import UserRepository

_LOGIN_URL = "/api/v1/auth/login"
_LOGOUT_URL = "/api/v1/auth/logout"
_REFRESH_URL = "/api/v1/auth/refresh"
_COOKIE_NAME = "refresh_token"
_PASSWORD = "a-strong-real-password-1"


async def _seed_user(db_session: AsyncSession, *, email: str) -> uuid.UUID:
    repo = UserRepository(db_session)
    user = await repo.create(
        email=normalize_email(email),
        password_hash=hash_password(_PASSWORD),
        full_name="Logout Test User",
        role=UserRole.TEACHER,
        is_active=True,
    )
    await db_session.commit()
    return user.id


async def test_logout_revokes_the_refresh_session(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_user(db_session, email="logout-revoke@example.com")
    login_response = await client_db.post(
        _LOGIN_URL, json={"email": "logout-revoke@example.com", "password": _PASSWORD}
    )
    assert login_response.status_code == 200
    cookie = client_db.cookies.get(_COOKIE_NAME)
    assert cookie is not None

    logout_response = await client_db.post(_LOGOUT_URL)
    assert logout_response.status_code == 200

    session_row = await RefreshSessionRepository(db_session).get_by_token_hash(
        hash_refresh_token(cookie)
    )
    assert session_row is not None
    assert session_row.revoked_at is not None

    # And the now-revoked session can no longer be used to refresh.
    refresh_response = await client_db.post(_REFRESH_URL, cookies={_COOKIE_NAME: cookie})
    assert refresh_response.status_code == 401


async def test_logout_clears_the_cookie(client_db: AsyncClient, db_session: AsyncSession) -> None:
    await _seed_user(db_session, email="logout-clear@example.com")
    await client_db.post(
        _LOGIN_URL,
        json={"email": "logout-clear@example.com", "password": _PASSWORD},
    )

    response = await client_db.post(_LOGOUT_URL)
    set_cookie = response.headers.get("set-cookie", "")

    # A cleared cookie is expressed as an immediately-expired Set-Cookie
    # for the same name/path (Starlette's delete_cookie behavior).
    assert f"{_COOKIE_NAME}=" in set_cookie
    assert "path=/api/v1/auth" in set_cookie.lower()


async def test_repeated_logout_is_handled_safely(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_user(db_session, email="logout-repeat@example.com")
    await client_db.post(
        _LOGIN_URL,
        json={"email": "logout-repeat@example.com", "password": _PASSWORD},
    )

    first = await client_db.post(_LOGOUT_URL)
    second = await client_db.post(_LOGOUT_URL)

    assert first.status_code == 200
    assert second.status_code == 200


async def test_logout_with_no_cookie_at_all_is_a_safe_no_op(client_db: AsyncClient) -> None:
    response = await client_db.post(_LOGOUT_URL)
    assert response.status_code == 200
