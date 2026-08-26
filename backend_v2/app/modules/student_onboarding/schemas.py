"""Safe, typed result contract for the student-onboarding workflow."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class StudentOnboardingIssue(BaseModel):
    code: str
    message: str


class StudentOnboardingStudentResult(BaseModel):
    row_number: int = Field(..., ge=2)
    student_profile_id: uuid.UUID | None = None
    full_name: str | None = None
    roll_number: str | None = None
    profile_status: Literal["imported", "existing", "failed"]
    photo_filename: str | None = None
    photo_status: Literal["not_provided", "matched", "missing", "duplicate", "invalid"]
    biometric_status: Literal[
        "not_requested", "not_processed", "enrolled", "failed", "already_enrolled"
    ]
    issues: list[StudentOnboardingIssue]


class StudentOnboardingUnmatchedFile(BaseModel):
    filename: str
    code: str
    message: str


class StudentOnboardingResult(BaseModel):
    classroom_id: uuid.UUID
    classroom_name: str
    total_students: int = Field(..., ge=0)
    profile_success_count: int = Field(..., ge=0)
    face_success_count: int = Field(..., ge=0)
    students: list[StudentOnboardingStudentResult]
    unmatched_files: list[StudentOnboardingUnmatchedFile]
