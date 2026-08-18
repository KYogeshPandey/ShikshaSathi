"""Application-defined errors for the user domain.

Follows the same ``AppError`` contract as app/core/exceptions.py so
these are handled by the same centralized exception handler and
returned in the same standard envelope — no route needs its own
``try/except`` for this (instruction G: "Map unique-email conflicts to
a stable application error.").
"""

from __future__ import annotations

from fastapi import status

from app.core.exceptions import AppError


class EmailAlreadyExistsError(AppError):
    """Raised when creating a user whose email already exists.

    The message is deliberately generic and does not echo the
    submitted email back — this endpoint is not customer-facing in
    Phase 2 (only ``scripts/bootstrap_admin.py`` creates users), but
    the same discipline as the login-error messages (no
    account-enumeration detail) is kept here for when Phase 3 exposes
    an admin-facing "create user" endpoint on top of this repository.
    """

    code = "EMAIL_ALREADY_EXISTS"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self) -> None:
        super().__init__("A user with this email already exists.")
