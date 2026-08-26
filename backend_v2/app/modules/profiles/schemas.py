"""Pydantic schemas for the profiles domain.

Neither ``TeacherProfileRead`` nor ``StudentProfileRead`` contains
``password_hash``, ``email``, or any other credential field — those
schemas reference ``user_id`` only, so the caller composes with
``app.modules.users.schemas.UserRead`` when a combined view is needed
(Stage 2 concern; Stage 1 only defines the profile-owned fields, per
instruction B: "no password hash, token hash, or secret field may
appear").
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TeacherProfileCreate(_StrictRequest):
    user_id: uuid.UUID
    employee_code: str | None = Field(default=None, max_length=64)
    phone_number: str | None = Field(default=None, max_length=32)

    @field_validator("employee_code", "phone_number")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class TeacherProfileUpdate(_StrictRequest):
    employee_code: str | None = Field(default=None, max_length=64)
    phone_number: str | None = Field(default=None, max_length=32)
    is_active: bool | None = Field(default=None)

    @field_validator("employee_code", "phone_number")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def _active_cannot_be_null(self) -> TeacherProfileUpdate:
        if "is_active" in self.model_fields_set and self.is_active is None:
            raise ValueError("is_active must not be null")
        return self


class TeacherProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    employee_code: str | None
    phone_number: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class StudentProfileCreate(_StrictRequest):
    user_id: uuid.UUID
    classroom_id: uuid.UUID | None = Field(default=None)
    roll_number: str | None = Field(default=None, max_length=32)

    @field_validator("roll_number")
    @classmethod
    def _strip_roll_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def _roll_number_requires_classroom(self) -> StudentProfileCreate:
        if self.classroom_id is None and self.roll_number is not None:
            raise ValueError("roll_number requires classroom_id")
        return self


class StudentProfileUpdate(_StrictRequest):
    classroom_id: uuid.UUID | None = Field(default=None)
    roll_number: str | None = Field(default=None, max_length=32)
    is_active: bool | None = Field(default=None)

    @field_validator("roll_number")
    @classmethod
    def _strip_roll_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def _active_cannot_be_null(self) -> StudentProfileUpdate:
        if "is_active" in self.model_fields_set and self.is_active is None:
            raise ValueError("is_active must not be null")
        return self

    @model_validator(mode="after")
    def _explicit_unassignment_cannot_keep_roll_number(self) -> StudentProfileUpdate:
        if (
            "classroom_id" in self.model_fields_set
            and self.classroom_id is None
            and self.roll_number is not None
        ):
            raise ValueError("roll_number requires classroom_id")
        return self


class StudentClassroomMembershipUpdate(_StrictRequest):
    classroom_id: uuid.UUID | None
    roll_number: str | None = Field(default=None, max_length=32)

    @field_validator("roll_number")
    @classmethod
    def _strip_roll_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def _roll_number_requires_classroom(self) -> StudentClassroomMembershipUpdate:
        if self.classroom_id is None and self.roll_number is not None:
            raise ValueError("roll_number requires classroom_id")
        return self


class StudentProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    full_name: str | None = None
    classroom_id: uuid.UUID | None
    roll_number: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
