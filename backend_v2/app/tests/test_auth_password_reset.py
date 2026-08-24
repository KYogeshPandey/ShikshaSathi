"""Focused Milestone 4D secure password-reset coverage."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Environment, Settings, get_settings
from app.core.middleware import AuthRateLimitMiddleware, RequestIDMiddleware
from app.modules.auth.email import SmtpOtpEmailSender, get_otp_email_sender
from app.modules.auth.models import OtpChallenge, OtpPurpose, RefreshSession
from app.modules.auth.security import hash_password, verify_password
from app.modules.users.models import User, UserRole
from app.modules.users.normalization import normalize_email
from app.modules.users.repository import UserRepository

_REQUEST_URL = "/api/v1/auth/password-reset/request"
_VERIFY_URL = "/api/v1/auth/password-reset/verify"
_RESEND_URL = "/api/v1/auth/password-reset/resend"
_CONFIRM_URL = "/api/v1/auth/password-reset/confirm"
_LOGIN_URL = "/api/v1/auth/login"
_LOGIN_OTP_VERIFY_URL = "/api/v1/auth/otp/verify"
_OLD_PASSWORD = "old-password-secure-123"
_NEW_PASSWORD = "new-password-secure-456"
_GENERIC_DETAIL = "If an active account exists for that email, a verification code has been sent."


@dataclass(frozen=True)
class Delivery:
    recipient: str
    otp: str
    expires_in_minutes: int


class CapturingOtpEmailSender:
    def __init__(self) -> None:
        self.login_deliveries: list[Delivery] = []
        self.reset_deliveries: list[Delivery] = []

    async def send_login_otp(
        self,
        *,
        recipient: str,
        otp: str,
        expires_in_minutes: int,
    ) -> None:
        self.login_deliveries.append(Delivery(recipient, otp, expires_in_minutes))

    async def send_password_reset_otp(
        self,
        *,
        recipient: str,
        otp: str,
        expires_in_minutes: int,
    ) -> None:
        self.reset_deliveries.append(Delivery(recipient, otp, expires_in_minutes))


@pytest.fixture()
def reset_enabled(app: FastAPI) -> tuple[Settings, CapturingOtpEmailSender]:
    base = get_settings().model_dump()
    settings = Settings(
        **{
            **base,
            "LOGIN_OTP_ENABLED": True,
            "LOGIN_OTP_TTL_SECONDS": 300,
            "LOGIN_OTP_MAX_ATTEMPTS": 3,
            "LOGIN_OTP_RESEND_COOLDOWN_SECONDS": 30,
            "PASSWORD_RESET_GRANT_TTL_SECONDS": 120,
            "OTP_EMAIL_PROVIDER": "development_log",
        }
    )
    sender = CapturingOtpEmailSender()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_otp_email_sender] = lambda: sender
    return settings, sender


async def _seed_user(
    session: AsyncSession,
    *,
    email: str,
    active: bool = True,
) -> User:
    user = await UserRepository(session).create(
        email=normalize_email(email),
        password_hash=hash_password(_OLD_PASSWORD),
        full_name="Password Reset Test User",
        role=UserRole.TEACHER,
        is_active=active,
    )
    await session.commit()
    return user


async def _request_reset(
    client: AsyncClient,
    sender: CapturingOtpEmailSender,
    *,
    email: str,
) -> tuple[dict[str, Any], Delivery]:
    response = await client.post(_REQUEST_URL, json={"email": email})
    assert response.status_code == 202, response.text
    return response.json(), sender.reset_deliveries[-1]


async def _reset_challenge(session: AsyncSession, user_id: uuid.UUID) -> OtpChallenge:
    challenge = await session.scalar(
        select(OtpChallenge)
        .where(
            OtpChallenge.user_id == user_id,
            OtpChallenge.purpose == OtpPurpose.PASSWORD_RESET,
        )
        .order_by(OtpChallenge.created_at.desc())
    )
    assert challenge is not None
    return challenge


async def _verify_reset(
    client: AsyncClient,
    *,
    email: str,
    otp: str,
) -> dict[str, Any]:
    response = await client.post(_VERIFY_URL, json={"email": email, "otp": otp})
    assert response.status_code == 200, response.text
    return response.json()


async def test_registered_request_is_generic_hashed_and_issues_no_session(
    client_db: AsyncClient,
    db_session: AsyncSession,
    reset_enabled: tuple[Settings, CapturingOtpEmailSender],
) -> None:
    _, sender = reset_enabled
    email = "reset-user@ordinary-domain.dev"
    user = await _seed_user(db_session, email=email)

    body, delivery = await _request_reset(client_db, sender, email=email)

    assert body == {"detail": _GENERIC_DETAIL, "expires_in": 300, "resend_available_in": 30}
    assert delivery.recipient == email
    assert delivery.otp.isdigit() and len(delivery.otp) == 6
    challenge = await _reset_challenge(db_session, user.id)
    assert challenge.purpose is OtpPurpose.PASSWORD_RESET
    assert challenge.otp_hash != delivery.otp
    assert len(challenge.otp_hash) == 64
    assert delivery.otp not in repr(challenge)
    assert client_db.cookies.get("refresh_token") is None
    user_sessions = await db_session.scalar(
        select(func.count(RefreshSession.id)).where(RefreshSession.user_id == user.id)
    )
    assert int(user_sessions or 0) == 0


async def test_nonexistent_and_inactive_requests_are_indistinguishable(
    client_db: AsyncClient,
    db_session: AsyncSession,
    reset_enabled: tuple[Settings, CapturingOtpEmailSender],
) -> None:
    _, sender = reset_enabled
    await _seed_user(db_session, email="inactive-reset@example.com", active=False)

    missing = await client_db.post(_REQUEST_URL, json={"email": "missing@example.com"})
    inactive = await client_db.post(_REQUEST_URL, json={"email": "inactive-reset@example.com"})

    assert missing.status_code == inactive.status_code == 202
    assert (
        missing.json()
        == inactive.json()
        == {
            "detail": _GENERIC_DETAIL,
            "expires_in": 300,
            "resend_available_in": 30,
        }
    )
    assert sender.reset_deliveries == []
    assert int((await db_session.scalar(select(func.count(OtpChallenge.id)))) or 0) == 0


async def test_valid_reset_otp_returns_only_a_hashed_short_lived_grant(
    client_db: AsyncClient,
    db_session: AsyncSession,
    reset_enabled: tuple[Settings, CapturingOtpEmailSender],
) -> None:
    settings, sender = reset_enabled
    email = "valid-reset@example.com"
    user = await _seed_user(db_session, email=email)
    _, delivery = await _request_reset(client_db, sender, email=email)

    grant = await _verify_reset(client_db, email=email, otp=delivery.otp)

    assert set(grant) == {"reset_id", "reset_token", "expires_in"}
    assert grant["expires_in"] == settings.PASSWORD_RESET_GRANT_TTL_SECONDS
    assert "access_token" not in str(grant)
    assert client_db.cookies.get("refresh_token") is None
    challenge = await _reset_challenge(db_session, user.id)
    await db_session.refresh(challenge)
    assert challenge.consumed_at is not None
    assert challenge.otp_hash not in {delivery.otp, grant["reset_token"]}
    assert len(challenge.otp_hash) == 64
    user_sessions = await db_session.scalar(
        select(func.count(RefreshSession.id)).where(RefreshSession.user_id == user.id)
    )
    assert int(user_sessions or 0) == 0
    unauthorized = await client_db.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {grant['reset_token']}"},
    )
    assert unauthorized.status_code == 401


async def test_invalid_expired_consumed_and_max_attempt_reset_otps_are_rejected(
    client_db: AsyncClient,
    db_session: AsyncSession,
    reset_enabled: tuple[Settings, CapturingOtpEmailSender],
) -> None:
    settings, sender = reset_enabled
    email = "reset-lifecycle@example.com"
    user = await _seed_user(db_session, email=email)
    _, delivery = await _request_reset(client_db, sender, email=email)
    wrong = "000000" if delivery.otp != "000000" else "111111"

    invalid = await client_db.post(_VERIFY_URL, json={"email": email, "otp": wrong})
    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "INVALID_OTP"

    challenge = await _reset_challenge(db_session, user.id)
    challenge.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    expired = await client_db.post(_VERIFY_URL, json={"email": email, "otp": delivery.otp})
    assert expired.status_code == 410
    assert expired.json()["error"]["code"] == "OTP_EXPIRED"

    challenge.expires_at = datetime.now(UTC) + timedelta(seconds=60)
    challenge.attempt_count = 0
    await db_session.commit()
    attempts = [
        await client_db.post(_VERIFY_URL, json={"email": email, "otp": wrong})
        for _ in range(settings.LOGIN_OTP_MAX_ATTEMPTS)
    ]
    assert [response.status_code for response in attempts] == [401, 401, 429]
    assert attempts[-1].json()["error"]["code"] == "OTP_ATTEMPTS_EXCEEDED"

    challenge.last_sent_at = datetime.now(UTC) - timedelta(seconds=60)
    await db_session.commit()
    await client_db.post(_RESEND_URL, json={"email": email})
    replacement_delivery = sender.reset_deliveries[-1]
    await _verify_reset(client_db, email=email, otp=replacement_delivery.otp)
    consumed = await client_db.post(
        _VERIFY_URL,
        json={"email": email, "otp": replacement_delivery.otp},
    )
    assert consumed.status_code == 401
    assert consumed.json()["error"]["code"] == "INVALID_OTP"


async def test_resend_cooldown_is_enforced_and_replacement_invalidates_old_code(
    client_db: AsyncClient,
    db_session: AsyncSession,
    reset_enabled: tuple[Settings, CapturingOtpEmailSender],
) -> None:
    settings, sender = reset_enabled
    email = "reset-resend@example.com"
    user = await _seed_user(db_session, email=email)
    original_body, original = await _request_reset(client_db, sender, email=email)
    original_row = await _reset_challenge(db_session, user.id)

    cooldown = await client_db.post(_RESEND_URL, json={"email": email})
    assert cooldown.status_code == 202
    assert cooldown.json() == original_body
    assert len(sender.reset_deliveries) == 1
    assert original_row.invalidated_at is None

    original_row.last_sent_at = datetime.now(UTC) - timedelta(
        seconds=settings.LOGIN_OTP_RESEND_COOLDOWN_SECONDS + 1
    )
    await db_session.commit()
    resent = await client_db.post(_RESEND_URL, json={"email": email})
    assert resent.status_code == 202
    assert resent.json() == original_body
    assert len(sender.reset_deliveries) == 2
    await db_session.refresh(original_row)
    assert original_row.invalidated_at is not None

    old_code = await client_db.post(_VERIFY_URL, json={"email": email, "otp": original.otp})
    assert old_code.status_code == 401
    await _verify_reset(client_db, email=email, otp=sender.reset_deliveries[-1].otp)


async def test_login_and_password_reset_otp_purposes_cannot_cross_authorize(
    client_db: AsyncClient,
    db_session: AsyncSession,
    reset_enabled: tuple[Settings, CapturingOtpEmailSender],
) -> None:
    _, sender = reset_enabled
    email = "purpose-separated@example.com"
    user = await _seed_user(db_session, email=email)

    login = await client_db.post(_LOGIN_URL, json={"email": email, "password": _OLD_PASSWORD})
    assert login.status_code == 202
    login_challenge_id = login.json()["challenge_id"]
    login_code = sender.login_deliveries[-1].otp
    reset_with_login_code = await client_db.post(
        _VERIFY_URL,
        json={"email": email, "otp": login_code},
    )
    assert reset_with_login_code.status_code == 401

    _, reset_delivery = await _request_reset(client_db, sender, email=email)
    reset_challenge = await _reset_challenge(db_session, user.id)
    login_with_reset_code = await client_db.post(
        _LOGIN_OTP_VERIFY_URL,
        json={"challenge_id": str(reset_challenge.id), "otp": reset_delivery.otp},
    )
    assert login_with_reset_code.status_code == 401

    valid_login = await client_db.post(
        _LOGIN_OTP_VERIFY_URL,
        json={"challenge_id": login_challenge_id, "otp": login_code},
    )
    assert valid_login.status_code == 200


async def test_weak_password_and_confirmation_mismatch_do_not_consume_grant(
    client_db: AsyncClient,
    db_session: AsyncSession,
    reset_enabled: tuple[Settings, CapturingOtpEmailSender],
) -> None:
    _, sender = reset_enabled
    email = "reset-policy@example.com"
    await _seed_user(db_session, email=email)
    _, delivery = await _request_reset(client_db, sender, email=email)
    grant = await _verify_reset(client_db, email=email, otp=delivery.otp)

    mismatch = await client_db.post(
        _CONFIRM_URL,
        json={
            "reset_id": grant["reset_id"],
            "reset_token": grant["reset_token"],
            "new_password": _NEW_PASSWORD,
            "confirm_password": "different-password-789",
        },
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "VALIDATION_ERROR"

    weak = await client_db.post(
        _CONFIRM_URL,
        json={
            "reset_id": grant["reset_id"],
            "reset_token": grant["reset_token"],
            "new_password": "short",
            "confirm_password": "short",
        },
    )
    assert weak.status_code == 422
    assert weak.json()["error"]["code"] == "INVALID_NEW_PASSWORD"

    valid = await client_db.post(
        _CONFIRM_URL,
        json={
            "reset_id": grant["reset_id"],
            "reset_token": grant["reset_token"],
            "new_password": _NEW_PASSWORD,
            "confirm_password": _NEW_PASSWORD,
        },
    )
    assert valid.status_code == 200


async def test_password_reset_changes_credentials_revokes_sessions_and_is_single_use(
    client_db: AsyncClient,
    db_session: AsyncSession,
    reset_enabled: tuple[Settings, CapturingOtpEmailSender],
) -> None:
    _, sender = reset_enabled
    email = "reset-complete@example.com"
    user = await _seed_user(db_session, email=email)

    login = await client_db.post(_LOGIN_URL, json={"email": email, "password": _OLD_PASSWORD})
    login_verified = await client_db.post(
        _LOGIN_OTP_VERIFY_URL,
        json={
            "challenge_id": login.json()["challenge_id"],
            "otp": sender.login_deliveries[-1].otp,
        },
    )
    assert login_verified.status_code == 200
    assert client_db.cookies.get("refresh_token") is not None

    _, delivery = await _request_reset(client_db, sender, email=email)
    grant = await _verify_reset(client_db, email=email, otp=delivery.otp)
    payload = {
        "reset_id": grant["reset_id"],
        "reset_token": grant["reset_token"],
        "new_password": _NEW_PASSWORD,
        "confirm_password": _NEW_PASSWORD,
    }
    completed = await client_db.post(_CONFIRM_URL, json=payload)
    assert completed.status_code == 200
    assert set(completed.json()) == {"detail"}

    await db_session.refresh(user)
    assert verify_password(_OLD_PASSWORD, user.password_hash) is False
    assert verify_password(_NEW_PASSWORD, user.password_hash) is True
    active_sessions = await db_session.scalar(
        select(func.count(RefreshSession.id)).where(RefreshSession.revoked_at.is_(None))
    )
    assert int(active_sessions or 0) == 0
    assert (await client_db.post("/api/v1/auth/refresh")).status_code == 401

    reused = await client_db.post(_CONFIRM_URL, json=payload)
    assert reused.status_code == 401
    assert reused.json()["error"]["code"] == "INVALID_PASSWORD_RESET_GRANT"
    old_login = await client_db.post(
        _LOGIN_URL,
        json={"email": email, "password": _OLD_PASSWORD},
    )
    assert old_login.status_code == 401
    new_login = await client_db.post(
        _LOGIN_URL,
        json={"email": email, "password": _NEW_PASSWORD},
    )
    assert new_login.status_code == 202


async def test_expired_or_wrong_reset_grant_is_rejected(
    client_db: AsyncClient,
    db_session: AsyncSession,
    reset_enabled: tuple[Settings, CapturingOtpEmailSender],
) -> None:
    _, sender = reset_enabled
    email = "reset-grant-expiry@example.com"
    user = await _seed_user(db_session, email=email)
    _, delivery = await _request_reset(client_db, sender, email=email)
    grant = await _verify_reset(client_db, email=email, otp=delivery.otp)

    wrong = await client_db.post(
        _CONFIRM_URL,
        json={
            "reset_id": grant["reset_id"],
            "reset_token": "x" * 64,
            "new_password": _NEW_PASSWORD,
            "confirm_password": _NEW_PASSWORD,
        },
    )
    assert wrong.status_code == 401

    challenge = await _reset_challenge(db_session, user.id)
    challenge.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    expired = await client_db.post(
        _CONFIRM_URL,
        json={
            "reset_id": grant["reset_id"],
            "reset_token": grant["reset_token"],
            "new_password": _NEW_PASSWORD,
            "confirm_password": _NEW_PASSWORD,
        },
    )
    assert expired.status_code == 401
    assert expired.json()["error"]["code"] == "INVALID_PASSWORD_RESET_GRANT"


def test_production_cannot_expose_password_reset_otp_with_development_adapter() -> None:
    base = get_settings().model_dump()
    with pytest.raises(ValidationError):
        Settings(
            **{
                **base,
                "APP_ENV": Environment.PRODUCTION,
                "DEBUG": False,
                "CORS_ALLOWED_ORIGINS": ["https://shikshasathi.vercel.app"],
                "TRUSTED_HOSTS": ["shikshasathi-api.onrender.com"],
                "REFRESH_TOKEN_COOKIE_SECURE": True,
                "LOGIN_OTP_ENABLED": False,
                "OTP_EMAIL_PROVIDER": "development_log",
            }
        )


async def test_smtp_adapter_uses_password_reset_specific_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = get_settings().model_dump()
    settings = Settings(
        **{
            **base,
            "LOGIN_OTP_ENABLED": False,
            "OTP_EMAIL_PROVIDER": "smtp",
            "SMTP_HOST": "smtp.example.com",
            "SMTP_FROM_EMAIL": "no-reply@example.com",
        }
    )
    sender = SmtpOtpEmailSender(settings)
    messages: list[EmailMessage] = []
    monkeypatch.setattr(sender, "_send_sync", messages.append)

    await sender.send_password_reset_otp(
        recipient="reset-recipient@example.com",
        otp="123456",
        expires_in_minutes=10,
    )

    assert len(messages) == 1
    message = messages[0]
    assert message["Subject"] == "ShikshaSathi password reset"
    content = message.get_content()
    assert "Password Reset" in content
    assert "123456" in content
    assert "10 minutes" in content
    assert "password" not in content.lower().replace("password reset", "")


def test_all_password_reset_routes_are_independently_rate_limited() -> None:
    app = FastAPI()
    app.add_middleware(
        AuthRateLimitMiddleware,
        route_limits={
            _REQUEST_URL: (1, 60),
            _VERIFY_URL: (1, 60),
            _RESEND_URL: (1, 60),
            _CONFIRM_URL: (1, 60),
        },
    )
    app.add_middleware(RequestIDMiddleware)

    for path in (_REQUEST_URL, _VERIFY_URL, _RESEND_URL, _CONFIRM_URL):
        app.add_api_route(path, lambda: {"ok": True}, methods=["POST"])

    with TestClient(app) as client:
        for path in (_REQUEST_URL, _VERIFY_URL, _RESEND_URL, _CONFIRM_URL):
            assert client.post(path).status_code == 200
            blocked = client.post(path)
            assert blocked.status_code == 429
            assert blocked.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
