"""Shared seed helpers for Phase 3 HTTP integration tests."""

from __future__ import annotations

import uuid
from typing import cast

from httpx import AsyncClient
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.security import create_access_token, hash_password
from app.modules.users.models import User, UserRole
from app.modules.users.normalization import normalize_email
from app.modules.users.repository import UserRepository

TEST_PASSWORD = "a-strong-real-password-1"


async def seed_user(
    session: AsyncSession,
    *,
    email: str,
    role: UserRole,
    is_active: bool = True,
) -> User:
    user = await UserRepository(session).create(
        email=normalize_email(email),
        password_hash=hash_password(TEST_PASSWORD),
        full_name=f"{role.value.title()} HTTP Test",
        role=role,
        is_active=is_active,
    )
    await session.commit()
    return user


def auth_headers(user: User, *, request_id: str | None = None) -> dict[str, str]:
    identity = inspect(user).identity
    if identity is None:
        raise RuntimeError("Cannot create auth headers for a transient User instance")
    user_id = cast(uuid.UUID, identity[0])
    headers = {
        "Authorization": (f"Bearer {create_access_token(user_id=user_id, settings=get_settings())}")
    }
    if request_id is not None:
        headers["X-Request-ID"] = request_id
    return headers


async def create_resource(
    client: AsyncClient,
    *,
    path: str,
    payload: dict[str, object],
    user: User,
) -> dict[str, object]:
    response = await client.post(path, json=payload, headers=auth_headers(user))
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body
