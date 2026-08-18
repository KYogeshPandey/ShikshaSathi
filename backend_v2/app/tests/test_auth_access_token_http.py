"""Tests for access-token validation, exercised end-to-end through ``GET /me``.

Complements app/tests/test_auth_security.py's pure-unit JWT tests with
the cases that specifically need a real database: a token whose
subject has been deleted, and a token whose subject has since been
deactivated (instruction K: "missing/deleted user", "inactive user
after token issuance").
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.security import create_access_token, hash_password
from app.modules.users.models import UserRole
from app.modules.users.normalization import normalize_email
from app.modules.users.repository import UserRepository

_ME_URL = "/api/v1/auth/me"


async def _seed_user(db_session: AsyncSession, *, email: str, is_active: bool = True) -> uuid.UUID:
    repo = UserRepository(db_session)
    user = await repo.create(
        email=normalize_email(email),
        password_hash=hash_password("a-strong-real-password-1"),
        full_name="Token Test User",
        role=UserRole.TEACHER,
        is_active=is_active,
    )
    await db_session.commit()
    return user.id


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_me_with_valid_token_returns_safe_user(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    user_id = await _seed_user(db_session, email="valid-token@example.com")
    token = create_access_token(user_id=user_id, settings=get_settings())

    response = await client_db.get(_ME_URL, headers=_auth_header(token))

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "valid-token@example.com"
    assert "password_hash" not in body


async def test_me_without_token_returns_401(client_db: AsyncClient) -> None:
    response = await client_db.get(_ME_URL)
    assert response.status_code == 401


async def test_me_with_malformed_token_returns_401(client_db: AsyncClient) -> None:
    response = await client_db.get(_ME_URL, headers=_auth_header("this-is-not-a-jwt"))
    assert response.status_code == 401


async def test_me_with_expired_token_returns_401(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    user_id = await _seed_user(db_session, email="expired-token@example.com")
    expired_issued_at = datetime.now(UTC) - timedelta(hours=1)
    token = create_access_token(user_id=user_id, settings=get_settings(), now=expired_issued_at)

    response = await client_db.get(_ME_URL, headers=_auth_header(token))
    assert response.status_code == 401


async def test_me_with_wrong_signature_returns_401(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    user_id = await _seed_user(db_session, email="wrong-sig@example.com")
    settings = get_settings()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(user_id),
            "type": "access",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "jti": uuid.uuid4().hex,
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
        },
        "a-completely-different-secret-not-the-real-one",
        algorithm=settings.JWT_ALGORITHM,
    )
    response = await client_db.get(_ME_URL, headers=_auth_header(token))
    assert response.status_code == 401


async def test_me_with_wrong_token_type_returns_401(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    user_id = await _seed_user(db_session, email="wrong-type@example.com")
    settings = get_settings()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(user_id),
            "type": "refresh",  # not "access"
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "jti": uuid.uuid4().hex,
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
        },
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    response = await client_db.get(_ME_URL, headers=_auth_header(token))
    assert response.status_code == 401


async def test_me_with_missing_or_deleted_user_returns_401(client_db: AsyncClient) -> None:
    # A structurally valid, correctly-signed token for a subject that
    # was never created (indistinguishable, from the token's own
    # perspective, from one that was deleted after issuance).
    token = create_access_token(user_id=uuid.uuid4(), settings=get_settings())
    response = await client_db.get(_ME_URL, headers=_auth_header(token))
    assert response.status_code == 401


async def test_me_with_user_deactivated_after_token_issuance_returns_401(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    user_id = await _seed_user(db_session, email="deactivated-after@example.com")
    token = create_access_token(user_id=user_id, settings=get_settings())

    # Confirm the token is valid before deactivation.
    assert (await client_db.get(_ME_URL, headers=_auth_header(token))).status_code == 200

    user = await UserRepository(db_session).get_by_id(user_id)
    assert user is not None
    user.is_active = False
    await db_session.commit()

    # Same still-unexpired token, now rejected — role/active state is
    # always read fresh from the database (instruction F), never
    # cached from when the token was issued.
    response = await client_db.get(_ME_URL, headers=_auth_header(token))
    assert response.status_code == 401
