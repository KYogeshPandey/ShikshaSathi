"""Pydantic schemas for the user domain.

Only a response ("read") schema exists in Phase 2 — there is no
self-registration endpoint (instruction A: "Do not add public
self-registration unless the existing authoritative documentation
explicitly requires it for this phase," and it does not). Accounts are
created only via ``scripts/bootstrap_admin.py`` in this phase.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.users.models import UserRole


class UserRead(BaseModel):
    """The only representation of a user ever returned by the API.

    Deliberately has no ``password_hash`` field — not "hidden by
    serialization," genuinely absent from the type, so there is no
    field to accidentally include (instruction B: "Password hashes
    must never be returned by schemas or API responses.").
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime = Field(..., description="Account creation timestamp (UTC).")
