"""Focused tests for the Brevo HTTPS OTP email adapter."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.modules.auth import email as email_module
from app.modules.auth.email import (
    BrevoApiOtpEmailSender,
    OtpEmailDeliveryError,
    SmtpOtpEmailSender,
    get_otp_email_sender,
)
from app.modules.auth.security import hash_password
from app.modules.users.models import UserRole
from app.modules.users.normalization import normalize_email
from app.modules.users.repository import UserRepository

_BREVO_URL = "https://api.brevo.com/v3/smtp/email"
_API_KEY = "brevo-test-key-not-a-real-secret"
_SENDER = "verified-sender@example.com"
_PASSWORD = "brevo-test-password-123"


def _brevo_settings(*, login_otp_enabled: bool = True) -> Settings:
    base = get_settings().model_dump()
    return Settings(
        **{
            **base,
            "LOGIN_OTP_ENABLED": login_otp_enabled,
            "OTP_EMAIL_PROVIDER": "brevo_api",
            "BREVO_API_KEY": _API_KEY,
            "BREVO_API_TIMEOUT_SECONDS": 20,
            "SMTP_FROM_EMAIL": _SENDER,
        }
    )


async def _seed_user(session: AsyncSession, *, email: str) -> None:
    await UserRepository(session).create(
        email=normalize_email(email),
        password_hash=hash_password(_PASSWORD),
        full_name="Brevo Email Test User",
        role=UserRole.TEACHER,
        is_active=True,
    )
    await session.commit()


def _response(
    status_code: int,
    *,
    json: Any | None = None,
    content: bytes | None = None,
) -> httpx.Response:
    request = httpx.Request("POST", _BREVO_URL)
    if content is not None:
        return httpx.Response(status_code, content=content, request=request)
    return httpx.Response(status_code, json=json, request=request)


def _install_mock_client(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[..., Awaitable[httpx.Response]],
) -> list[dict[str, Any]]:
    configurations: list[dict[str, Any]] = []

    class MockAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            configurations.append(kwargs)

        async def __aenter__(self) -> MockAsyncClient:
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

        async def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, Any],
        ) -> httpx.Response:
            return await handler(url, headers=headers, json=json)

    monkeypatch.setattr(email_module, "AsyncClient", MockAsyncClient)
    return configurations


async def test_brevo_success_posts_expected_https_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
    ) -> httpx.Response:
        captured.update(url=url, headers=headers, json=json)
        return _response(201, json={"messageId": "brevo-message-id"})

    configurations = _install_mock_client(monkeypatch, fake_post)
    sender = BrevoApiOtpEmailSender(_brevo_settings())

    await sender.send_login_otp(
        recipient="registered-user@example.net",
        otp="123456",
        expires_in_minutes=10,
    )

    assert captured["url"] == _BREVO_URL
    assert captured["url"].startswith("https://")
    assert captured["headers"]["api-key"] == _API_KEY
    assert captured["json"]["sender"] == {"name": "ShikshaSathi", "email": _SENDER}
    assert captured["json"]["to"] == [{"email": "registered-user@example.net"}]
    assert captured["json"]["subject"] == "Your ShikshaSathi sign-in code"
    assert "123456" in captured["json"]["textContent"]
    assert configurations == [{"timeout": 20, "follow_redirects": False}]


@pytest.mark.parametrize("status_code", [400, 401, 429, 500, 503])
async def test_brevo_http_failures_raise_only_provider_neutral_error(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
) -> None:
    async def fake_post(*_args: Any, **_kwargs: Any) -> httpx.Response:
        return _response(
            status_code,
            json={"message": f"provider detail {_API_KEY} 654321"},
        )

    _install_mock_client(monkeypatch, fake_post)
    sender = BrevoApiOtpEmailSender(_brevo_settings())

    with pytest.raises(OtpEmailDeliveryError) as raised:
        await sender.send_login_otp(
            recipient="registered-user@example.net",
            otp="654321",
            expires_in_minutes=10,
        )

    assert str(raised.value) == "OTP email delivery failed."
    assert _API_KEY not in str(raised.value)
    assert "654321" not in str(raised.value)


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ReadTimeout("test timeout", request=httpx.Request("POST", _BREVO_URL)),
        httpx.ConnectError("test network error", request=httpx.Request("POST", _BREVO_URL)),
    ],
    ids=["timeout", "network"],
)
async def test_brevo_transport_failures_are_handled_safely(
    monkeypatch: pytest.MonkeyPatch,
    failure: httpx.RequestError,
) -> None:
    async def fake_post(*_args: Any, **_kwargs: Any) -> httpx.Response:
        raise failure

    _install_mock_client(monkeypatch, fake_post)
    sender = BrevoApiOtpEmailSender(_brevo_settings())

    with pytest.raises(OtpEmailDeliveryError, match=r"^OTP email delivery failed\.$"):
        await sender.send_login_otp(
            recipient="registered-user@example.net",
            otp="123456",
            expires_in_minutes=10,
        )


@pytest.mark.parametrize(
    "response",
    [
        _response(201, content=b"not-json"),
        _response(201, json={"unexpected": "shape"}),
    ],
    ids=["malformed-json", "missing-message-id"],
)
async def test_brevo_unexpected_success_response_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    response: httpx.Response,
) -> None:
    async def fake_post(*_args: Any, **_kwargs: Any) -> httpx.Response:
        return response

    _install_mock_client(monkeypatch, fake_post)
    sender = BrevoApiOtpEmailSender(_brevo_settings())

    with pytest.raises(OtpEmailDeliveryError, match=r"^OTP email delivery failed\.$"):
        await sender.send_login_otp(
            recipient="registered-user@example.net",
            otp="123456",
            expires_in_minutes=10,
        )


async def test_brevo_failure_logs_do_not_leak_api_key_otp_or_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, dict[str, Any]]] = []

    class CapturingLogger:
        def error(self, event: str, **kwargs: Any) -> None:
            events.append((event, kwargs))

        def info(self, event: str, **kwargs: Any) -> None:
            events.append((event, kwargs))

    async def fake_post(*_args: Any, **_kwargs: Any) -> httpx.Response:
        return _response(401, json={"message": f"sensitive {_API_KEY} 987654"})

    monkeypatch.setattr(email_module, "logger", CapturingLogger())
    _install_mock_client(monkeypatch, fake_post)

    with pytest.raises(OtpEmailDeliveryError):
        await BrevoApiOtpEmailSender(_brevo_settings()).send_login_otp(
            recipient="private-recipient@example.net",
            otp="987654",
            expires_in_minutes=10,
        )

    rendered = repr(events)
    assert events == [
        (
            "otp_email_delivery_failed",
            {"provider": "brevo_api", "reason": "http_status", "status_category": "4xx"},
        )
    ]
    assert _API_KEY not in rendered
    assert "987654" not in rendered
    assert "private-recipient@example.net" not in rendered


def test_provider_factory_preserves_brevo_and_smtp_selection() -> None:
    brevo_sender = get_otp_email_sender(_brevo_settings())
    assert isinstance(brevo_sender, BrevoApiOtpEmailSender)

    base = get_settings().model_dump()
    smtp_settings = Settings(
        **{
            **base,
            "OTP_EMAIL_PROVIDER": "smtp",
            "SMTP_HOST": "smtp.example.com",
            "SMTP_FROM_EMAIL": _SENDER,
        }
    )
    assert isinstance(get_otp_email_sender(smtp_settings), SmtpOtpEmailSender)


async def test_login_otp_uses_brevo_provider(
    app: FastAPI,
    client_db: httpx.AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _brevo_settings()
    app.dependency_overrides[get_settings] = lambda: settings
    requests: list[dict[str, Any]] = []

    async def fake_post(
        _url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
    ) -> httpx.Response:
        requests.append({"headers": headers, "json": json})
        return _response(201, json={"messageId": "login-message-id"})

    _install_mock_client(monkeypatch, fake_post)
    await _seed_user(db_session, email="brevo-login@example.net")

    response = await client_db.post(
        "/api/v1/auth/login",
        json={"email": "brevo-login@example.net", "password": _PASSWORD},
    )

    assert response.status_code == 202, response.text
    assert response.json()["otp_required"] is True
    assert client_db.cookies.get("refresh_token") is None
    assert len(requests) == 1
    assert requests[0]["headers"]["api-key"] == _API_KEY
    assert requests[0]["json"]["subject"] == "Your ShikshaSathi sign-in code"


async def test_password_reset_otp_uses_brevo_provider_and_keeps_generic_response(
    app: FastAPI,
    client_db: httpx.AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _brevo_settings(login_otp_enabled=False)
    app.dependency_overrides[get_settings] = lambda: settings
    requests: list[dict[str, Any]] = []

    async def fake_post(
        _url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
    ) -> httpx.Response:
        requests.append({"headers": headers, "json": json})
        return _response(201, json={"messageId": "reset-message-id"})

    _install_mock_client(monkeypatch, fake_post)
    await _seed_user(db_session, email="brevo-reset@example.net")

    response = await client_db.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "brevo-reset@example.net"},
    )

    assert response.status_code == 202, response.text
    assert response.json() == {
        "detail": "If an active account exists for that email, a verification code has been sent.",
        "expires_in": 600,
        "resend_available_in": 60,
    }
    assert len(requests) == 1
    assert requests[0]["headers"]["api-key"] == _API_KEY
    assert requests[0]["json"]["subject"] == "ShikshaSathi password reset"
