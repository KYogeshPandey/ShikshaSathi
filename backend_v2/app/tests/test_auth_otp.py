"""Focused Milestone 4C email-OTP authentication coverage."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
from app.modules.auth.email import get_otp_email_sender
from app.modules.auth.models import OtpChallenge, RefreshSession
from app.modules.auth.security import hash_password
from app.modules.users.models import UserRole
from app.modules.users.normalization import normalize_email
from app.modules.users.repository import UserRepository

_LOGIN_URL = "/api/v1/auth/login"
_VERIFY_URL = "/api/v1/auth/otp/verify"
_RESEND_URL = "/api/v1/auth/otp/resend"
_PASSWORD = "otp-test-password-123"


@dataclass(frozen=True)
class Delivery:
    recipient: str
    otp: str
    expires_in_minutes: int


class CapturingOtpEmailSender:
    def __init__(self) -> None:
        self.deliveries: list[Delivery] = []

    async def send_login_otp(
        self,
        *,
        recipient: str,
        otp: str,
        expires_in_minutes: int,
    ) -> None:
        self.deliveries.append(Delivery(recipient, otp, expires_in_minutes))


@pytest.fixture()
def otp_enabled(app: FastAPI) -> tuple[Settings, CapturingOtpEmailSender]:
    base = get_settings().model_dump()
    settings = Settings(
        **{
            **base,
            "LOGIN_OTP_ENABLED": True,
            "LOGIN_OTP_TTL_SECONDS": 300,
            "LOGIN_OTP_MAX_ATTEMPTS": 3,
            "LOGIN_OTP_RESEND_COOLDOWN_SECONDS": 30,
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
) -> None:
    await UserRepository(session).create(
        email=normalize_email(email),
        password_hash=hash_password(_PASSWORD),
        full_name="OTP Test User",
        role=UserRole.TEACHER,
        is_active=active,
    )
    await session.commit()


async def _begin(
    client: AsyncClient,
    sender: CapturingOtpEmailSender,
    *,
    email: str = "otp-user@registered-domain.dev",
) -> tuple[dict[str, Any], Delivery]:
    response = await client.post(
        _LOGIN_URL,
        json={"email": email, "password": _PASSWORD},
    )
    assert response.status_code == 202, response.text
    return response.json(), sender.deliveries[-1]


async def test_otp_disabled_preserves_existing_login_behavior(
    client_db: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _seed_user(db_session, email="otp-disabled@example.com")
    response = await client_db.post(
        _LOGIN_URL,
        json={"email": "otp-disabled@example.com", "password": _PASSWORD},
    )
    assert response.status_code == 200
    assert response.json()["token"]["access_token"]
    assert "refresh_token=" in response.headers["set-cookie"]


async def test_correct_credentials_create_only_a_hashed_challenge(
    client_db: AsyncClient,
    db_session: AsyncSession,
    otp_enabled: tuple[Settings, CapturingOtpEmailSender],
) -> None:
    _, sender = otp_enabled
    email = "generic-user@independent-domain.org"
    await _seed_user(db_session, email=email)
    body, delivery = await _begin(client_db, sender, email=email)

    assert body["otp_required"] is True
    assert body["expires_in"] <= 300
    assert set(body) == {
        "otp_required",
        "challenge_id",
        "expires_in",
        "resend_available_in",
    }
    assert delivery.recipient == email
    assert delivery.otp.isdigit() and len(delivery.otp) == 6
    assert delivery.otp not in str(body)
    assert client_db.cookies.get("refresh_token") is None

    challenge = await db_session.get(OtpChallenge, uuid.UUID(body["challenge_id"]))
    assert challenge is not None
    assert challenge.otp_hash != delivery.otp
    assert len(challenge.otp_hash) == 64
    assert delivery.otp not in repr(challenge)
    assert int((await db_session.scalar(select(func.count(RefreshSession.id)))) or 0) == 0


@pytest.mark.parametrize(
    ("email", "password", "active"),
    [
        ("otp-wrong@example.com", "wrong-password-456", True),
        ("otp-inactive@example.com", _PASSWORD, False),
    ],
)
async def test_wrong_password_and_inactive_user_do_not_create_challenges(
    client_db: AsyncClient,
    db_session: AsyncSession,
    otp_enabled: tuple[Settings, CapturingOtpEmailSender],
    email: str,
    password: str,
    active: bool,
) -> None:
    _, sender = otp_enabled
    await _seed_user(db_session, email=email, active=active)
    response = await client_db.post(_LOGIN_URL, json={"email": email, "password": password})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert sender.deliveries == []
    assert int((await db_session.scalar(select(func.count(OtpChallenge.id)))) or 0) == 0


async def test_valid_otp_creates_session_and_supports_me_refresh_and_logout(
    client_db: AsyncClient,
    db_session: AsyncSession,
    otp_enabled: tuple[Settings, CapturingOtpEmailSender],
) -> None:
    _, sender = otp_enabled
    await _seed_user(db_session, email="otp-user@registered-domain.dev")
    challenge, delivery = await _begin(client_db, sender)

    verified = await client_db.post(
        _VERIFY_URL,
        json={"challenge_id": challenge["challenge_id"], "otp": delivery.otp},
    )
    assert verified.status_code == 200, verified.text
    token = verified.json()["token"]["access_token"]
    assert "refresh_token=" in verified.headers["set-cookie"]
    assert int((await db_session.scalar(select(func.count(RefreshSession.id)))) or 0) == 1

    me = await client_db.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    refreshed = await client_db.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200, refreshed.text
    refreshed_token = refreshed.json()["token"]["access_token"]
    restored = await client_db.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {refreshed_token}"},
    )
    assert restored.status_code == 200
    assert (await client_db.post("/api/v1/auth/logout")).status_code == 200
    assert (await client_db.post("/api/v1/auth/refresh")).status_code == 401


async def test_invalid_then_valid_otp_and_consumed_otp_behavior(
    client_db: AsyncClient,
    db_session: AsyncSession,
    otp_enabled: tuple[Settings, CapturingOtpEmailSender],
) -> None:
    _, sender = otp_enabled
    await _seed_user(db_session, email="otp-user@registered-domain.dev")
    challenge, delivery = await _begin(client_db, sender)
    payload = {"challenge_id": challenge["challenge_id"], "otp": "000000"}
    if delivery.otp == "000000":
        payload["otp"] = "111111"
    invalid = await client_db.post(_VERIFY_URL, json=payload)
    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "INVALID_OTP"

    valid = await client_db.post(
        _VERIFY_URL,
        json={"challenge_id": challenge["challenge_id"], "otp": delivery.otp},
    )
    assert valid.status_code == 200
    consumed = await client_db.post(
        _VERIFY_URL,
        json={"challenge_id": challenge["challenge_id"], "otp": delivery.otp},
    )
    assert consumed.status_code == 401
    assert consumed.json()["error"]["code"] == "INVALID_OTP"


async def test_expired_otp_is_rejected_but_can_be_replaced_by_resend(
    client_db: AsyncClient,
    db_session: AsyncSession,
    otp_enabled: tuple[Settings, CapturingOtpEmailSender],
) -> None:
    _, sender = otp_enabled
    await _seed_user(db_session, email="otp-user@registered-domain.dev")
    body, delivery = await _begin(client_db, sender)
    challenge = await db_session.get(OtpChallenge, uuid.UUID(body["challenge_id"]))
    assert challenge is not None
    challenge.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    challenge.last_sent_at = datetime.now(UTC) - timedelta(seconds=60)
    await db_session.commit()

    response = await client_db.post(
        _VERIFY_URL,
        json={"challenge_id": body["challenge_id"], "otp": delivery.otp},
    )
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "OTP_EXPIRED"
    await db_session.refresh(challenge)
    assert challenge.invalidated_at is None

    resent = await client_db.post(
        _RESEND_URL,
        json={"challenge_id": body["challenge_id"]},
    )
    assert resent.status_code == 202
    await db_session.refresh(challenge)
    assert challenge.invalidated_at is not None


async def test_max_attempts_invalidates_challenge(
    client_db: AsyncClient,
    db_session: AsyncSession,
    otp_enabled: tuple[Settings, CapturingOtpEmailSender],
) -> None:
    settings, sender = otp_enabled
    await _seed_user(db_session, email="otp-user@registered-domain.dev")
    body, delivery = await _begin(client_db, sender)
    wrong = "000000" if delivery.otp != "000000" else "111111"
    responses = [
        await client_db.post(
            _VERIFY_URL,
            json={"challenge_id": body["challenge_id"], "otp": wrong},
        )
        for _ in range(settings.LOGIN_OTP_MAX_ATTEMPTS)
    ]
    assert [response.status_code for response in responses] == [401, 401, 429]
    assert responses[-1].json()["error"]["code"] == "OTP_ATTEMPTS_EXCEEDED"
    challenge = await db_session.get(OtpChallenge, uuid.UUID(body["challenge_id"]))
    assert challenge is not None and challenge.invalidated_at is not None


async def test_resend_cooldown_then_replacement_invalidates_old_code(
    client_db: AsyncClient,
    db_session: AsyncSession,
    otp_enabled: tuple[Settings, CapturingOtpEmailSender],
) -> None:
    settings, sender = otp_enabled
    await _seed_user(db_session, email="otp-user@registered-domain.dev")
    original, original_delivery = await _begin(client_db, sender)
    cooldown = await client_db.post(
        _RESEND_URL,
        json={"challenge_id": original["challenge_id"]},
    )
    assert cooldown.status_code == 429
    assert cooldown.json()["error"]["code"] == "OTP_RESEND_COOLDOWN"

    old_row = await db_session.get(OtpChallenge, uuid.UUID(original["challenge_id"]))
    assert old_row is not None
    old_row.last_sent_at = datetime.now(UTC) - timedelta(
        seconds=settings.LOGIN_OTP_RESEND_COOLDOWN_SECONDS + 1
    )
    await db_session.commit()
    resent = await client_db.post(
        _RESEND_URL,
        json={"challenge_id": original["challenge_id"]},
    )
    assert resent.status_code == 202, resent.text
    replacement = resent.json()
    assert replacement["challenge_id"] != original["challenge_id"]
    assert len(sender.deliveries) == 2
    await db_session.refresh(old_row)
    assert old_row.invalidated_at is not None

    old_code = await client_db.post(
        _VERIFY_URL,
        json={"challenge_id": original["challenge_id"], "otp": original_delivery.otp},
    )
    assert old_code.status_code == 401
    new_code = await client_db.post(
        _VERIFY_URL,
        json={
            "challenge_id": replacement["challenge_id"],
            "otp": sender.deliveries[-1].otp,
        },
    )
    assert new_code.status_code == 200


def test_production_cannot_select_otp_exposing_development_adapter() -> None:
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
                "LOGIN_OTP_ENABLED": True,
                "OTP_EMAIL_PROVIDER": "development_log",
            }
        )


def test_otp_verify_and_resend_routes_are_rate_limited() -> None:
    app = FastAPI()
    app.add_middleware(
        AuthRateLimitMiddleware,
        route_limits={
            _LOGIN_URL: (1, 60),
            _VERIFY_URL: (2, 60),
            _RESEND_URL: (1, 60),
        },
    )
    app.add_middleware(RequestIDMiddleware)

    @app.post(_VERIFY_URL)
    async def verify_probe() -> dict[str, bool]:
        return {"ok": True}

    @app.post(_RESEND_URL)
    async def resend_probe() -> dict[str, bool]:
        return {"ok": True}

    @app.post(_LOGIN_URL)
    async def login_probe() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(app) as client:
        assert client.post(_VERIFY_URL).status_code == 200
        assert client.post(_VERIFY_URL).status_code == 200
        assert client.post(_VERIFY_URL).status_code == 429
        assert client.post(_RESEND_URL).status_code == 200
        assert client.post(_RESEND_URL).status_code == 429
        assert client.post(_LOGIN_URL).status_code == 200
        blocked_login = client.post(_LOGIN_URL)
        assert blocked_login.status_code == 429
        assert blocked_login.json()["error"]["message"] == (
            "Too many login attempts. Please try again later."
        )
