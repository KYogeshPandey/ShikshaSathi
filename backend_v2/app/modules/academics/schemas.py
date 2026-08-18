"""Pydantic schemas for the academic domain.

Update schemas use ``Optional`` fields defaulting to ``None`` and are
applied via ``model_dump(exclude_unset=True)`` at the repository layer —
the standard FastAPI/Pydantic pattern for distinguishing "field omitted"
from "field explicitly set to its default," and the simplest safe MVP
choice given no project document mandates a different partial-update
convention (Stage 1 brief, instruction C).
"""

from __future__ import annotations

import uuid
from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.academics.models import DayOfWeek
from app.modules.academics.normalization import normalize_code, normalize_name


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClassroomCreate(_StrictRequest):
    name: str = Field(..., min_length=1, max_length=255)
    code: str = Field(..., min_length=1, max_length=64)
    grade_level: str | None = Field(default=None, max_length=32)
    section: str | None = Field(default=None, max_length=32)

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str) -> str:
        normalized = normalize_name(value)
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized

    @field_validator("code")
    @classmethod
    def _normalize_code(cls, value: str) -> str:
        normalized = normalize_code(value)
        if not normalized:
            raise ValueError("code must not be blank")
        return normalized

    @field_validator("grade_level", "section")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class ClassroomUpdate(_StrictRequest):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    grade_level: str | None = Field(default=None, max_length=32)
    section: str | None = Field(default=None, max_length=32)
    is_active: bool | None = Field(default=None)

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_name(value)
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized

    @model_validator(mode="after")
    def _non_nullable_fields_cannot_be_null(self) -> ClassroomUpdate:
        for field_name in ("name", "is_active"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} must not be null")
        return self


class ClassroomRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    grade_level: str | None
    section: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SubjectCreate(_StrictRequest):
    name: str = Field(..., min_length=1, max_length=255)
    code: str = Field(..., min_length=1, max_length=64)
    is_elective: bool = Field(default=False)

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str) -> str:
        normalized = normalize_name(value)
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized

    @field_validator("code")
    @classmethod
    def _normalize_code(cls, value: str) -> str:
        normalized = normalize_code(value)
        if not normalized:
            raise ValueError("code must not be blank")
        return normalized


class SubjectUpdate(_StrictRequest):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_elective: bool | None = Field(default=None)
    is_active: bool | None = Field(default=None)

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_name(value)
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized

    @model_validator(mode="after")
    def _non_nullable_fields_cannot_be_null(self) -> SubjectUpdate:
        for field_name in ("name", "is_elective", "is_active"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} must not be null")
        return self


class SubjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    is_elective: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TeacherAssignmentCreate(_StrictRequest):
    teacher_profile_id: uuid.UUID
    classroom_id: uuid.UUID
    subject_id: uuid.UUID


class TeacherAssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    teacher_profile_id: uuid.UUID
    classroom_id: uuid.UUID
    subject_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TeacherAssignmentUpdate(_StrictRequest):
    is_active: bool


class TimetableEntryCreate(_StrictRequest):
    classroom_id: uuid.UUID
    subject_id: uuid.UUID
    teacher_profile_id: uuid.UUID
    day_of_week: DayOfWeek
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def _end_after_start(self) -> TimetableEntryCreate:
        # Cross-field validation for "start < end" is deliberately also
        # re-checked at the repository layer (InvalidTimetableSlotError)
        # and enforced again by the DB CHECK constraint
        # (ck_timetable_entries_start_before_end) — the same
        # belt-and-suspenders pattern used throughout this phase.
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be before end_time")
        return self


class TimetableEntryUpdate(_StrictRequest):
    classroom_id: uuid.UUID | None = None
    subject_id: uuid.UUID | None = None
    teacher_profile_id: uuid.UUID | None = None
    day_of_week: DayOfWeek | None = None
    start_time: time | None = None
    end_time: time | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def _provided_fields_cannot_be_null(self) -> TimetableEntryUpdate:
        for field_name in self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} must not be null")
        return self


class TimetableEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    classroom_id: uuid.UUID
    subject_id: uuid.UUID
    teacher_profile_id: uuid.UUID
    day_of_week: DayOfWeek
    start_time: time
    end_time: time
    is_active: bool
    created_at: datetime
    updated_at: datetime
