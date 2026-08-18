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
