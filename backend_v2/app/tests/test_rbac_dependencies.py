"""Unit tests for app/modules/auth/dependencies.py's RBAC composition.

Follows the same "small throwaway probe app" pattern as
app/tests/test_middleware.py: a tiny FastAPI app, entirely separate
from the real ``fastapi_app``, with ``get_current_user`` overridden to
return a fixed fake ``User`` instance (or to raise, for the
unauthenticated case) — this exercises ``get_current_active_user`` and
``require_roles`` directly without needing a real JWT, HTTP
Authorization header, or a reachable database, so this file always
runs (instruction F: "Add small protected probe/test routes only when
needed for automated tests.").
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, status
from fastapi.testclient import TestClient

from app.modules.auth.dependencies import (
    AuthenticationError,
    get_current_user,
    require_roles,
)
from app.modules.users.models import User, UserRole


def _fake_user(*, role: UserRole, is_active: bool = True) -> User:
    return User(
        id=uuid.uuid4(),
        email="probe@example.com",
        password_hash="irrelevant-not-checked-in-these-tests",
        full_name="Probe User",
        role=role,
        is_active=is_active,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _build_probe_app(
    current_user_override: Callable[[], Awaitable[User]],
) -> FastAPI:
    probe_app = FastAPI()
    probe_app.dependency_overrides[get_current_user] = current_user_override

    @probe_app.get("/admin-only")
    async def admin_only(
        _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    ) -> dict[str, str]:
        return {"status": "ok"}

    @probe_app.get("/teacher-or-admin")
    async def teacher_or_admin(
        _: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.TEACHER))],
    ) -> dict[str, str]:
        return {"status": "ok"}

    return probe_app


def test_unauthenticated_request_returns_401() -> None:
    async def _raise_unauthenticated() -> User:
        raise AuthenticationError("Not authenticated.")

    with TestClient(_build_probe_app(_raise_unauthenticated)) as client:
        response = client.get("/admin-only")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_allowed_role_succeeds() -> None:
    async def _admin_user() -> User:
        return _fake_user(role=UserRole.ADMIN)

    with TestClient(_build_probe_app(_admin_user)) as client:
        response = client.get("/admin-only")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_disallowed_role_returns_403() -> None:
    async def _student_user() -> User:
        return _fake_user(role=UserRole.STUDENT)

    with TestClient(_build_probe_app(_student_user)) as client:
        response = client.get("/admin-only")
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_require_roles_accepts_any_of_multiple_allowed_roles() -> None:
    async def _teacher_user() -> User:
        return _fake_user(role=UserRole.TEACHER)

    with TestClient(_build_probe_app(_teacher_user)) as client:
        response = client.get("/teacher-or-admin")
    assert response.status_code == 200


def test_disabled_user_is_blocked_even_with_an_otherwise_valid_identity() -> None:
    """A deactivated user must be rejected by get_current_active_user.

    Simulated here by having the overridden ``get_current_user`` return
    a user with ``is_active=False`` — exactly what a real deactivated
    account looks like once loaded from the database (see
    app/modules/auth/dependencies.py's ``get_current_active_user``).
    """

    async def _inactive_user() -> User:
        return _fake_user(role=UserRole.ADMIN, is_active=False)

    with TestClient(_build_probe_app(_inactive_user)) as client:
        response = client.get("/admin-only")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_require_roles_raised_error_is_a_plain_http_exception() -> None:
    """Sanity check that a 403 from require_roles carries no sensitive detail."""

    async def _student_user() -> User:
        return _fake_user(role=UserRole.STUDENT)

    with TestClient(_build_probe_app(_student_user)) as client:
        response = client.get("/admin-only")
    body = response.json()
    assert "detail" in body
    assert "password_hash" not in str(body)
