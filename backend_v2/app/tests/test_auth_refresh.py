"""Tests for ``POST /api/v1/auth/refresh``.

Covers rotation, reuse detection, revocation, expiry, and the CSRF
Origin check — see app/modules/auth/service.py's ``refresh`` method and
app/modules/auth/dependencies.py's ``verify_same_origin``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.repository import RefreshSessionRepository
from app.modules.auth.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
)
from app.modules.users.models import UserRole
from app.modules.users.normalization import normalize_email
from app.modules.users.repository import UserRepository

_LOGIN_URL = "/api/v1/auth/login"
_REFRESH_URL = "/api/v1/auth/refresh"
_COOKIE_NAME = "refresh_token"
_PASSWORD = "a-strong-real-password-1"


async def _seed_user(db_session: AsyncSession, *, email: str, is_active: bool = True) -> uuid.UUID:
    repo = UserRepository(db_session)
    user = await repo.create(
        email=normalize_email(email),
        password_hash=hash_password(_PASSWORD),
        full_name="Refresh Test User",
        role=UserRole.TEACHER,
        is_active=is_active,
    )
    await db_session.commit()
    return user.id


async def _login(client_db: AsyncClient, email: str) -> str:
    response = await client_db.post(_LOGIN_URL, json={"email": email, "password": _PASSWORD})
    assert response.status_code == 200
    cookie = client_db.cookies.get(_COOKIE_NAME)
    assert cookie is not None
    return cookie


async def test_successful_refresh_returns_new_access_token(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_user(db_session, email="refresh-ok@example.com")
    login_response = await client_db.post(
        _LOGIN_URL, json={"email": "refresh-ok@example.com", "password": _PASSWORD}
    )
    original_access_token = login_response.json()["token"]["access_token"]

    response = await client_db.post(_REFRESH_URL)

    assert response.status_code == 200
    new_access_token = response.json()["token"]["access_token"]
    assert new_access_token != original_access_token


async def test_refresh_rotates_the_cookie_value(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_user(db_session, email="rotate@example.com")
    old_cookie = await _login(client_db, "rotate@example.com")

    response = await client_db.post(_REFRESH_URL)
    assert response.status_code == 200
    new_cookie = client_db.cookies.get(_COOKIE_NAME)

    assert new_cookie is not None
    assert new_cookie != old_cookie


async def test_old_refresh_token_rejected_after_rotation(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_user(db_session, email="old-rejected@example.com")
    old_cookie = await _login(client_db, "old-rejected@example.com")

    # Rotate once (this consumes/revokes `old_cookie`).
    assert (await client_db.post(_REFRESH_URL)).status_code == 200

    # Re-presenting the now-rotated-away cookie must fail.
    response = await client_db.post(_REFRESH_URL, cookies={_COOKIE_NAME: old_cookie})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"


async def test_reuse_of_rotated_token_revokes_the_whole_session_family(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    """Reuse detection: presenting an already-rotated token invalidates every session.

    Sequence: login (session A) -> refresh (rotates to session B,
    revokes A with replaced_by_id=B) -> replay A (reuse detected -> B
    is also revoked defensively) -> B must now be rejected too.
    """
    await _seed_user(db_session, email="reuse@example.com")
    session_a_cookie = await _login(client_db, "reuse@example.com")

    first_refresh = await client_db.post(_REFRESH_URL)
    assert first_refresh.status_code == 200
    session_b_cookie = client_db.cookies.get(_COOKIE_NAME)
    assert session_b_cookie is not None

    # Replay the original (now-rotated-away) session A token.
    reuse_response = await client_db.post(_REFRESH_URL, cookies={_COOKIE_NAME: session_a_cookie})
    assert reuse_response.status_code == 401

    # Session B, which was perfectly valid a moment ago, must now also
    # be rejected — the whole family was defensively revoked.
    session_b_response = await client_db.post(
        _REFRESH_URL, cookies={_COOKIE_NAME: session_b_cookie}
    )
    assert session_b_response.status_code == 401
    assert session_b_response.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"


async def test_revoked_token_rejected(client_db: AsyncClient, db_session: AsyncSession) -> None:
    await _seed_user(db_session, email="revoked@example.com")
    cookie = await _login(client_db, "revoked@example.com")

    assert (await client_db.post("/api/v1/auth/logout")).status_code == 200

    response = await client_db.post(_REFRESH_URL, cookies={_COOKIE_NAME: cookie})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"


async def test_expired_refresh_token_rejected(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    user_id = await _seed_user(db_session, email="expired-refresh@example.com")

    raw_token = generate_refresh_token()
    await RefreshSessionRepository(db_session).create(
        user_id=user_id,
        token_hash=hash_refresh_token(raw_token),
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    await db_session.commit()

    response = await client_db.post(_REFRESH_URL, cookies={_COOKIE_NAME: raw_token})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"


async def test_malformed_refresh_token_rejected(client_db: AsyncClient) -> None:
    response = await client_db.post(_REFRESH_URL, cookies={_COOKIE_NAME: "not-a-real-token"})
    assert response.status_code == 401


async def test_no_refresh_cookie_at_all_rejected(client_db: AsyncClient) -> None:
    response = await client_db.post(_REFRESH_URL)
    assert response.status_code == 401


async def test_access_token_used_as_refresh_cookie_is_rejected(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    """An access token is a JWT, not a stored opaque session — its hash matches nothing."""
    user_id = await _seed_user(db_session, email="wrong-kind-of-token@example.com")
    access_token = create_access_token(user_id=user_id, settings=get_settings())

    response = await client_db.post(_REFRESH_URL, cookies={_COOKIE_NAME: access_token})
    assert response.status_code == 401


async def test_refresh_rejected_for_deactivated_user(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    user_id = await _seed_user(db_session, email="deactivated-refresh@example.com")
    cookie = await _login(client_db, "deactivated-refresh@example.com")

    user = await UserRepository(db_session).get_by_id(user_id)
    assert user is not None
    user.is_active = False
    await db_session.commit()

    response = await client_db.post(_REFRESH_URL, cookies={_COOKIE_NAME: cookie})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"


async def test_refresh_cookie_security_attributes(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_user(db_session, email="cookie-attrs@example.com")
    response = await client_db.post(
        _LOGIN_URL, json={"email": "cookie-attrs@example.com", "password": _PASSWORD}
    )
    set_cookie = response.headers.get("set-cookie", "")

    assert "HttpOnly" in set_cookie
    assert "samesite=lax" in set_cookie.lower()
    assert "path=/api/v1/auth" in set_cookie.lower()


async def test_refresh_rejects_cross_origin_request(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    """Reject a disallowed Origin on a cookie-authenticated request."""
    await _seed_user(db_session, email="csrf@example.com")
    await _login(client_db, "csrf@example.com")

    response = await client_db.post(_REFRESH_URL, headers={"Origin": "https://evil.example.com"})
    assert response.status_code == 403


async def test_refresh_allows_matching_origin(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_user(db_session, email="csrf-ok@example.com")
    await _login(client_db, "csrf-ok@example.com")

    allowed_origin = get_settings().CORS_ALLOWED_ORIGINS[0]
    response = await client_db.post(_REFRESH_URL, headers={"Origin": allowed_origin})
    assert response.status_code == 200
