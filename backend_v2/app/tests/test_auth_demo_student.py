"""Fail-closed public Student demo login using the normal auth session flow."""

from __future__ import annotations

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.modules.auth.models import RefreshSession
from app.modules.auth.security import hash_password
from app.modules.profiles.repository import StudentProfileRepository
from app.modules.users.models import User, UserRole
from app.modules.users.normalization import normalize_email
from app.modules.users.repository import UserRepository

_DEMO_URL = "/api/v1/auth/demo-student"
_LOGIN_URL = "/api/v1/auth/login"
_TEST_PASSWORD = "test-only-demo-auth-password-123"


def _configure_demo(app: FastAPI, *, enabled: bool, email: str | None) -> Settings:
    base = get_settings().model_dump()
    settings = Settings(
        **{
            **base,
            "DEMO_STUDENT_LOGIN_ENABLED": enabled,
            "DEMO_STUDENT_LOGIN_EMAIL": email,
        }
    )
    app.dependency_overrides[get_settings] = lambda: settings
    return settings


async def _create_user(
    session: AsyncSession,
    *,
    email: str,
    role: UserRole,
    active: bool = True,
    with_student_profile: bool = False,
    profile_active: bool = True,
) -> User:
    user = await UserRepository(session).create(
        email=normalize_email(email),
        password_hash=hash_password(_TEST_PASSWORD),
        full_name="Public Demo Auth Test",
        role=role,
        is_active=active,
    )
    await session.flush()
    if with_student_profile:
        profile = await StudentProfileRepository(session).create(user_id=user.id)
        profile.is_active = profile_active
    await session.commit()
    return user


def _assert_unavailable(response_status: int, body: dict) -> None:
    assert response_status == 503
    assert body["error"]["code"] == "DEMO_STUDENT_LOGIN_UNAVAILABLE"
    assert body["error"]["message"] == "Student demo is temporarily unavailable."


async def test_demo_student_login_is_disabled_by_default(
    app: FastAPI,
    client_db: AsyncClient,
) -> None:
    _configure_demo(app, enabled=False, email=None)
    response = await client_db.post(_DEMO_URL)
    _assert_unavailable(response.status_code, response.json())


async def test_demo_student_login_rejects_missing_configured_user(
    app: FastAPI,
    client_db: AsyncClient,
) -> None:
    _configure_demo(app, enabled=True, email="missing-demo-student@example.com")
    response = await client_db.post(_DEMO_URL)
    _assert_unavailable(response.status_code, response.json())


async def test_demo_student_login_rejects_inactive_user(
    app: FastAPI,
    client_db: AsyncClient,
    db_session: AsyncSession,
) -> None:
    email = "inactive-demo-student@example.com"
    await _create_user(
        db_session,
        email=email,
        role=UserRole.STUDENT,
        active=False,
        with_student_profile=True,
    )
    _configure_demo(app, enabled=True, email=email)
    response = await client_db.post(_DEMO_URL)
    _assert_unavailable(response.status_code, response.json())


async def test_demo_student_login_rejects_configured_admin(
    app: FastAPI,
    client_db: AsyncClient,
    db_session: AsyncSession,
) -> None:
    email = "configured-demo-admin@example.com"
    await _create_user(db_session, email=email, role=UserRole.ADMIN)
    _configure_demo(app, enabled=True, email=email)
    response = await client_db.post(_DEMO_URL)
    _assert_unavailable(response.status_code, response.json())


async def test_demo_student_login_rejects_configured_teacher(
    app: FastAPI,
    client_db: AsyncClient,
    db_session: AsyncSession,
) -> None:
    email = "configured-demo-teacher@example.com"
    await _create_user(db_session, email=email, role=UserRole.TEACHER)
    _configure_demo(app, enabled=True, email=email)
    response = await client_db.post(_DEMO_URL)
    _assert_unavailable(response.status_code, response.json())


async def test_demo_student_login_requires_an_active_student_profile(
    app: FastAPI,
    client_db: AsyncClient,
    db_session: AsyncSession,
) -> None:
    email = "inactive-demo-profile@example.com"
    await _create_user(
        db_session,
        email=email,
        role=UserRole.STUDENT,
        with_student_profile=True,
        profile_active=False,
    )
    _configure_demo(app, enabled=True, email=email)
    response = await client_db.post(_DEMO_URL)
    _assert_unavailable(response.status_code, response.json())


async def test_demo_student_login_rejects_student_without_profile(
    app: FastAPI,
    client_db: AsyncClient,
    db_session: AsyncSession,
) -> None:
    email = "profileless-demo-student@example.com"
    await _create_user(db_session, email=email, role=UserRole.STUDENT)
    _configure_demo(app, enabled=True, email=email)
    response = await client_db.post(_DEMO_URL)
    _assert_unavailable(response.status_code, response.json())


async def test_configured_student_receives_the_normal_session_pair(
    app: FastAPI,
    client_db: AsyncClient,
    db_session: AsyncSession,
) -> None:
    email = "configured-demo-student@example.com"
    user = await _create_user(
        db_session,
        email=email,
        role=UserRole.STUDENT,
        with_student_profile=True,
    )
    settings = _configure_demo(app, enabled=True, email=email)

    response = await client_db.post(_DEMO_URL)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["id"] == str(user.id)
    assert body["user"]["role"] == "student"
    assert body["token"]["access_token"]
    assert body["token"]["token_type"] == "bearer"
    assert settings.REFRESH_TOKEN_COOKIE_NAME in response.headers["set-cookie"]
    session_count = await db_session.scalar(
        select(func.count()).select_from(RefreshSession).where(RefreshSession.user_id == user.id)
    )
    assert session_count == 1

    current_user = await client_db.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {body['token']['access_token']}"},
    )
    assert current_user.status_code == 200
    assert current_user.json()["id"] == str(user.id)


async def test_demo_client_cannot_submit_identity_or_credentials(
    app: FastAPI,
    client_db: AsyncClient,
    db_session: AsyncSession,
) -> None:
    configured_email = "fixed-demo-student@example.com"
    await _create_user(
        db_session,
        email=configured_email,
        role=UserRole.STUDENT,
        with_student_profile=True,
    )
    other = await _create_user(
        db_session,
        email="other-demo-student@example.com",
        role=UserRole.STUDENT,
        with_student_profile=True,
    )
    _configure_demo(app, enabled=True, email=configured_email)

    forbidden_fields = {
        "email": other.email,
        "password": _TEST_PASSWORD,
        "user_id": str(other.id),
        "student_profile_id": "2f87849f-52a6-4aac-b417-167e9f2c88ba",
    }
    response = await client_db.post(_DEMO_URL, json=forbidden_fields)

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    rejected_fields = {detail["field"] for detail in body["error"]["details"]["errors"]}
    assert rejected_fields == set(forbidden_fields)
    session_count = await db_session.scalar(select(func.count()).select_from(RefreshSession))
    assert session_count == 0


async def test_normal_password_login_is_unchanged_when_demo_login_is_enabled(
    app: FastAPI,
    client_db: AsyncClient,
    db_session: AsyncSession,
) -> None:
    demo_email = "normal-login-demo-student@example.com"
    await _create_user(
        db_session,
        email=demo_email,
        role=UserRole.STUDENT,
        with_student_profile=True,
    )
    normal_user = await _create_user(
        db_session,
        email="normal-password-login@example.com",
        role=UserRole.TEACHER,
    )
    _configure_demo(app, enabled=True, email=demo_email)

    response = await client_db.post(
        _LOGIN_URL,
        json={"email": normal_user.email, "password": _TEST_PASSWORD},
    )

    assert response.status_code == 200, response.text
    assert response.json()["user"]["id"] == str(normal_user.id)
    assert response.json()["user"]["role"] == "teacher"
