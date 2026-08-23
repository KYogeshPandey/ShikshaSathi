"""Pydantic schemas for the auth endpoints (app/modules/auth/router.py).

Separates request, internal, and response models (instruction G):
``LoginRequest`` is the only request body; ``AccessTokenInfo`` /
``LoginResponse`` / ``RefreshResponse`` / ``LogoutResponse`` are
responses. There is no "internal" schema in Phase 2 — the ORM models
themselves (``User``, ``RefreshSession``) are the internal
representation, and only ``UserRead`` (app/modules/users/schemas.py)
ever crosses the API boundary.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.modules.users.normalization import normalize_email
from app.modules.users.schemas import UserRead


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("email", mode="after")
    @classmethod
    def _normalize(cls, value: str) -> str:
        # Same authoritative normalizer used by UserRepository and
        # scripts/bootstrap_admin.py (instruction G) — so a login
        # attempt for "Admin@Example.com" matches a stored
        # "admin@example.com" account.
        return normalize_email(value)


class AccessTokenInfo(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Access-token lifetime in seconds.")


class LoginResponse(BaseModel):
    user: UserRead
    token: AccessTokenInfo


class OtpChallengeResponse(BaseModel):
    otp_required: Literal[True] = True
    challenge_id: uuid.UUID
    expires_in: int = Field(..., ge=1)
    resend_available_in: int = Field(..., ge=0)


class OtpVerifyRequest(BaseModel):
    challenge_id: uuid.UUID
    otp: str = Field(..., pattern=r"^\d{6}$")


class OtpResendRequest(BaseModel):
    challenge_id: uuid.UUID


class RefreshResponse(BaseModel):
    token: AccessTokenInfo


class LogoutResponse(BaseModel):
    detail: str = "Logged out."
