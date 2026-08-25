"""Email delivery boundary for login and password-reset OTPs.

Production adapters support ordinary SMTP and Brevo's HTTPS transactional
email API. Both receive credentials through validated settings. The
development logger is deliberately selectable only outside production
(enforced in ``Settings``). No adapter is selected or configured
automatically.
"""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Annotated, Protocol

import httpx
import structlog
from fastapi import Depends
from httpx import AsyncClient

from app.core.config import Settings, get_settings

logger = structlog.get_logger(__name__)

_BREVO_TRANSACTIONAL_EMAIL_URL = "https://api.brevo.com/v3/smtp/email"


@dataclass(frozen=True, slots=True)
class _OtpEmailContent:
    subject: str
    body: str


def _login_otp_content(*, otp: str, expires_in_minutes: int) -> _OtpEmailContent:
    return _OtpEmailContent(
        subject="Your ShikshaSathi sign-in code",
        body=(
            "Use this one-time code to finish signing in to ShikshaSathi:\n\n"
            f"{otp}\n\n"
            f"This code expires in {expires_in_minutes} minutes. "
            "If you did not request it, you can ignore this email."
        ),
    )


def _password_reset_otp_content(*, otp: str, expires_in_minutes: int) -> _OtpEmailContent:
    return _OtpEmailContent(
        subject="ShikshaSathi password reset",
        body=(
            "ShikshaSathi Password Reset\n\n"
            "Your password reset verification code is:\n\n"
            f"{otp}\n\n"
            f"This code expires in {expires_in_minutes} minutes. "
            "If you did not request a password reset, you can ignore this email."
        ),
    )


class OtpEmailSender(Protocol):
    async def send_login_otp(
        self,
        *,
        recipient: str,
        otp: str,
        expires_in_minutes: int,
    ) -> None: ...

    async def send_password_reset_otp(
        self,
        *,
        recipient: str,
        otp: str,
        expires_in_minutes: int,
    ) -> None: ...


class DisabledOtpEmailSender:
    """Inert adapter used while the feature flag is off."""

    async def send_login_otp(
        self,
        *,
        recipient: str,
        otp: str,
        expires_in_minutes: int,
    ) -> None:
        del recipient, otp, expires_in_minutes
        raise RuntimeError("OTP email delivery is not configured.")

    async def send_password_reset_otp(
        self,
        *,
        recipient: str,
        otp: str,
        expires_in_minutes: int,
    ) -> None:
        del recipient, otp, expires_in_minutes
        raise RuntimeError("OTP email delivery is not configured.")


class DevelopmentLogOtpEmailSender:
    """Explicit non-production adapter for local/manual verification only."""

    async def send_login_otp(
        self,
        *,
        recipient: str,
        otp: str,
        expires_in_minutes: int,
    ) -> None:
        logger.warning(
            "development_login_otp",
            recipient=recipient,
            otp=otp,
            expires_in_minutes=expires_in_minutes,
        )

    async def send_password_reset_otp(
        self,
        *,
        recipient: str,
        otp: str,
        expires_in_minutes: int,
    ) -> None:
        logger.warning(
            "development_password_reset_otp",
            recipient=recipient,
            otp=otp,
            expires_in_minutes=expires_in_minutes,
        )


class SmtpOtpEmailSender:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send_login_otp(
        self,
        *,
        recipient: str,
        otp: str,
        expires_in_minutes: int,
    ) -> None:
        content = _login_otp_content(otp=otp, expires_in_minutes=expires_in_minutes)
        message = EmailMessage()
        message["Subject"] = content.subject
        message["From"] = str(self._settings.SMTP_FROM_EMAIL)
        message["To"] = recipient
        message.set_content(content.body)
        await asyncio.to_thread(self._send_sync, message)

    async def send_password_reset_otp(
        self,
        *,
        recipient: str,
        otp: str,
        expires_in_minutes: int,
    ) -> None:
        content = _password_reset_otp_content(otp=otp, expires_in_minutes=expires_in_minutes)
        message = EmailMessage()
        message["Subject"] = content.subject
        message["From"] = str(self._settings.SMTP_FROM_EMAIL)
        message["To"] = recipient
        message.set_content(content.body)
        await asyncio.to_thread(self._send_sync, message)

    def _send_sync(self, message: EmailMessage) -> None:
        settings = self._settings
        assert settings.SMTP_HOST is not None  # validated when SMTP is enabled
        if settings.SMTP_USE_SSL:
            client: smtplib.SMTP = smtplib.SMTP_SSL(
                settings.SMTP_HOST,
                settings.SMTP_PORT,
                timeout=settings.SMTP_TIMEOUT_SECONDS,
                context=ssl.create_default_context(),
            )
        else:
            client = smtplib.SMTP(
                settings.SMTP_HOST,
                settings.SMTP_PORT,
                timeout=settings.SMTP_TIMEOUT_SECONDS,
            )
        with client:
            client.ehlo()
            if settings.SMTP_STARTTLS:
                client.starttls(context=ssl.create_default_context())
                client.ehlo()
            if settings.SMTP_USERNAME is not None:
                assert settings.SMTP_PASSWORD is not None
                client.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            client.send_message(message)


class OtpEmailDeliveryError(RuntimeError):
    """Provider-neutral failure safe to pass through internal auth layers."""


class BrevoApiOtpEmailSender:
    """Send OTP mail over Brevo's fixed HTTPS transactional-email endpoint."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send_login_otp(
        self,
        *,
        recipient: str,
        otp: str,
        expires_in_minutes: int,
    ) -> None:
        await self._send(
            recipient=recipient,
            content=_login_otp_content(otp=otp, expires_in_minutes=expires_in_minutes),
        )

    async def send_password_reset_otp(
        self,
        *,
        recipient: str,
        otp: str,
        expires_in_minutes: int,
    ) -> None:
        await self._send(
            recipient=recipient,
            content=_password_reset_otp_content(
                otp=otp,
                expires_in_minutes=expires_in_minutes,
            ),
        )

    async def _send(self, *, recipient: str, content: _OtpEmailContent) -> None:
        api_key = self._settings.BREVO_API_KEY
        sender_email = self._settings.SMTP_FROM_EMAIL
        assert api_key is not None  # validated when Brevo API delivery is enabled
        assert sender_email is not None  # validated when Brevo API delivery is enabled

        headers = {
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json",
        }
        payload = {
            "sender": {"name": "ShikshaSathi", "email": str(sender_email)},
            "to": [{"email": recipient}],
            "subject": content.subject,
            "textContent": content.body,
        }

        try:
            async with AsyncClient(
                timeout=self._settings.BREVO_API_TIMEOUT_SECONDS,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    _BREVO_TRANSACTIONAL_EMAIL_URL,
                    headers=headers,
                    json=payload,
                )
        except httpx.TimeoutException:
            self._log_failure("timeout")
            raise OtpEmailDeliveryError("OTP email delivery failed.") from None
        except httpx.RequestError:
            self._log_failure("network")
            raise OtpEmailDeliveryError("OTP email delivery failed.") from None

        if not 200 <= response.status_code < 300:
            status_category = (
                f"{response.status_code // 100}xx"
                if 400 <= response.status_code < 600
                else "unexpected"
            )
            self._log_failure("http_status", status_category=status_category)
            raise OtpEmailDeliveryError("OTP email delivery failed.")

        try:
            response_data = response.json()
        except ValueError:
            self._log_failure("malformed_response")
            raise OtpEmailDeliveryError("OTP email delivery failed.") from None

        message_id = response_data.get("messageId") if isinstance(response_data, dict) else None
        if not isinstance(message_id, str) or not message_id.strip():
            self._log_failure("unexpected_response")
            raise OtpEmailDeliveryError("OTP email delivery failed.")

        logger.info("otp_email_delivery_succeeded", provider="brevo_api")

    @staticmethod
    def _log_failure(reason: str, *, status_category: str | None = None) -> None:
        event: dict[str, str] = {"provider": "brevo_api", "reason": reason}
        if status_category is not None:
            event["status_category"] = status_category
        logger.error("otp_email_delivery_failed", **event)


def get_otp_email_sender(
    settings: Annotated[Settings, Depends(get_settings)],
) -> OtpEmailSender:
    if settings.OTP_EMAIL_PROVIDER == "brevo_api":
        return BrevoApiOtpEmailSender(settings)
    if settings.OTP_EMAIL_PROVIDER == "smtp":
        return SmtpOtpEmailSender(settings)
    if settings.OTP_EMAIL_PROVIDER == "development_log":
        return DevelopmentLogOtpEmailSender()
    return DisabledOtpEmailSender()


OtpEmailSenderDependency = Annotated[OtpEmailSender, Depends(get_otp_email_sender)]


__all__ = [
    "BrevoApiOtpEmailSender",
    "DevelopmentLogOtpEmailSender",
    "DisabledOtpEmailSender",
    "OtpEmailDeliveryError",
    "OtpEmailSender",
    "OtpEmailSenderDependency",
    "SmtpOtpEmailSender",
    "get_otp_email_sender",
]
