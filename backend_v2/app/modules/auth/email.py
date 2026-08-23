"""Email delivery boundary for login OTPs.

The production adapter is ordinary SMTP and receives all credentials through
validated settings. The development logger is deliberately selectable only
outside production (enforced in ``Settings``). Neither adapter is selected or
configured automatically.
"""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from typing import Annotated, Protocol

import structlog
from fastapi import Depends

from app.core.config import Settings, get_settings

logger = structlog.get_logger(__name__)


class OtpEmailSender(Protocol):
    async def send_login_otp(
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
        message = EmailMessage()
        message["Subject"] = "Your ShikshaSathi sign-in code"
        message["From"] = str(self._settings.SMTP_FROM_EMAIL)
        message["To"] = recipient
        message.set_content(
            "Use this one-time code to finish signing in to ShikshaSathi:\n\n"
            f"{otp}\n\n"
            f"This code expires in {expires_in_minutes} minutes. "
            "If you did not request it, you can ignore this email."
        )
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


def get_otp_email_sender(
    settings: Annotated[Settings, Depends(get_settings)],
) -> OtpEmailSender:
    if settings.OTP_EMAIL_PROVIDER == "smtp":
        return SmtpOtpEmailSender(settings)
    if settings.OTP_EMAIL_PROVIDER == "development_log":
        return DevelopmentLogOtpEmailSender()
    return DisabledOtpEmailSender()


OtpEmailSenderDependency = Annotated[OtpEmailSender, Depends(get_otp_email_sender)]


__all__ = [
    "DevelopmentLogOtpEmailSender",
    "DisabledOtpEmailSender",
    "OtpEmailSender",
    "OtpEmailSenderDependency",
    "SmtpOtpEmailSender",
    "get_otp_email_sender",
]
