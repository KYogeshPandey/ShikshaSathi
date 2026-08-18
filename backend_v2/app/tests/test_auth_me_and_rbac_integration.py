"""Integration tests for ``GET /me`` and role-based access, against the real app.

Unlike app/tests/test_rbac_dependencies.py (which uses a throwaway app
and fake ``User`` instances to unit-test the dependency composition in
isolation), this file exercises the *real* ``fastapi_app``, a real JWT,
and a real database — in particular to prove that a role change made
directly in the database takes effect on a user's very next request,
without needing a new access token (instruction F/K).

A tiny probe router is added to the real app only for the duration of
each test in this file (see ``_probe_router_installed``) and removed
immediately afterward — this is the "small protected probe/test route"
instruction F allows, kept out of the permanent router
(app/api/router.py) and out of every other test.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Annotated

import pytest
from fastapi import APIRouter, Depends, FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.dependencies import require_roles
from app.modules.auth.security import create_access_token, hash_password
from app.modules.users.models import User, UserRole
from app.modules.users.normalization import normalize_email
from app.modules.users.repository import UserRepository

_ME_URL = "/api/v1/auth/me"
_ADMIN_PROBE_URL = "/api/v1/_test-probe/admin-only"
_PASSWORD = "a-strong-real-password-1"


def _build_probe_router() -> APIRouter:
    probe_router = APIRouter(prefix="/api/v1/_test-probe")

    @probe_router.get("/admin-only")
    async def admin_only(
        _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    ) -> dict[str, str]:
        return {"status": "ok"}

    return probe_router


@pytest.fixture()
def _probe_router_installed(app: FastAPI) -> Iterator[None]:
    router = _build_probe_router()
    app.include_router(router)
    installed_routes = list(router.routes)
    try:
        yield
    finally:
        for route in installed_routes:
            if route in app.router.routes:
                app.router.routes.remove(route)


async def _seed_user(
    db_session: AsyncSession, *, email: str, role: UserRole = UserRole.TEACHER
) -> uuid.UUID:
    repo = UserRepository(db_session)
    user = await repo.create(
        email=normalize_email(email),
        password_hash=hash_password(_PASSWORD),
        full_name="RBAC Integration Test User",
        role=role,
        is_active=True,
    )
    await db_session.commit()
    return user.id


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_me_returns_the_safe_user_representation(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    user_id = await _seed_user(db_session, email="me-shape@example.com", role=UserRole.STUDENT)
    token = create_access_token(user_id=user_id, settings=get_settings())

    response = await client_db.get(_ME_URL, headers=_auth_header(token))

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "me-shape@example.com"
    assert body["role"] == "student"
    assert "password_hash" not in body


async def test_me_unauthenticated_returns_401(client_db: AsyncClient) -> None:
    response = await client_db.get(_ME_URL)
    assert response.status_code == 401


@pytest.mark.usefixtures("_probe_router_installed")
async def test_allowed_role_succeeds_against_real_app(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    user_id = await _seed_user(db_session, email="real-admin@example.com", role=UserRole.ADMIN)
    token = create_access_token(user_id=user_id, settings=get_settings())

    response = await client_db.get(_ADMIN_PROBE_URL, headers=_auth_header(token))
    assert response.status_code == 200


@pytest.mark.usefixtures("_probe_router_installed")
async def test_disallowed_role_returns_403_against_real_app(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    user_id = await _seed_user(db_session, email="real-teacher@example.com", role=UserRole.TEACHER)
    token = create_access_token(user_id=user_id, settings=get_settings())

    response = await client_db.get(_ADMIN_PROBE_URL, headers=_auth_header(token))
    assert response.status_code == 403


@pytest.mark.usefixtures("_probe_router_installed")
async def test_database_role_change_takes_effect_without_a_new_token(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    """The concrete regression test for instruction F's "no stale-role trust" rule.

    The same access token, never reissued, goes from 403 to 200 the
    moment the user's row is promoted to admin in the database — proof
    that authorization reads the role fresh on every request rather
    than trusting anything carried in the token.
    """
    user_id = await _seed_user(db_session, email="promoted@example.com", role=UserRole.TEACHER)
    token = create_access_token(user_id=user_id, settings=get_settings())

    before = await client_db.get(_ADMIN_PROBE_URL, headers=_auth_header(token))
    assert before.status_code == 403

    user = await UserRepository(db_session).get_by_id(user_id)
    assert user is not None
    user.role = UserRole.ADMIN
    await db_session.commit()

    after = await client_db.get(_ADMIN_PROBE_URL, headers=_auth_header(token))
    assert after.status_code == 200
