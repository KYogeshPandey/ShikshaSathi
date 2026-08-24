"""Application-defined errors for authentication.

Both errors below deliberately share one generic message and code per
failure family — this is the concrete mechanism behind instruction B's
"avoid account-enumeration details in login errors": unknown email,
wrong password, and a deactivated account all raise the exact same
``InvalidCredentialsError``, so the response body, status code, and
(via app/modules/auth/security.py's timing-safety dummy hash) response
timing give a caller no way to distinguish "no such account" from
"wrong password" from "account disabled".
"""

from __future__ import annotations

from fastapi import status

from app.core.exceptions import AppError


class InvalidCredentialsError(AppError):
    """Unknown email, wrong password, or a deactivated account — all three."""

    code = "INVALID_CREDENTIALS"
    status_code = status.HTTP_401_UNAUTHORIZED

    def __init__(self) -> None:
        super().__init__("Incorrect email or password.")


class InvalidRefreshTokenError(AppError):
    """Missing, malformed, expired, revoked, or reused refresh token.

    Same principle as ``InvalidCredentialsError``: every failure mode
    of ``POST /auth/refresh`` returns this one error, so a caller
    cannot distinguish "token expired" from "token was already used"
    from "no cookie was sent at all" — any of those states should
    simply require logging in again.
    """

    code = "INVALID_REFRESH_TOKEN"
    status_code = status.HTTP_401_UNAUTHORIZED

    def __init__(self) -> None:
        super().__init__("Refresh session is invalid or has expired. Please log in again.")


class OtpLoginNotEnabledError(AppError):
    code = "OTP_LOGIN_NOT_ENABLED"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self) -> None:
        super().__init__("Email verification is not enabled for login.")


class InvalidOtpChallengeError(AppError):
    code = "INVALID_OTP"
    status_code = status.HTTP_401_UNAUTHORIZED

    def __init__(self) -> None:
        super().__init__("The verification code is invalid or has already been used.")


class ExpiredOtpChallengeError(AppError):
    code = "OTP_EXPIRED"
    status_code = status.HTTP_410_GONE

    def __init__(self) -> None:
        super().__init__("The verification code has expired. Request a new code.")


class OtpAttemptsExceededError(AppError):
    code = "OTP_ATTEMPTS_EXCEEDED"
    status_code = status.HTTP_429_TOO_MANY_REQUESTS

    def __init__(self) -> None:
        super().__init__("Too many incorrect verification attempts. Request a new code.")


class OtpResendCooldownError(AppError):
    code = "OTP_RESEND_COOLDOWN"
    status_code = status.HTTP_429_TOO_MANY_REQUESTS

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            "Please wait before requesting another verification code.",
            details={"retry_after_seconds": retry_after_seconds},
        )


class OtpDeliveryUnavailableError(AppError):
    code = "OTP_DELIVERY_UNAVAILABLE"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    def __init__(self) -> None:
        super().__init__("The verification email could not be sent. Please try again shortly.")


class InvalidPasswordResetGrantError(AppError):
    code = "INVALID_PASSWORD_RESET_GRANT"
    status_code = status.HTTP_401_UNAUTHORIZED

    def __init__(self) -> None:
        super().__init__("The password reset authorization is invalid or has expired.")


class InvalidNewPasswordError(AppError):
    code = "INVALID_NEW_PASSWORD"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self, message: str) -> None:
        super().__init__(message)
