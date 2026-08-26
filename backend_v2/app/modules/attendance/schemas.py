"""Pydantic schemas for attendance core and the audit trail.

Stage 1 defines request/response shapes only; no router exists yet to
wire these into HTTP endpoints (see docs/HANDOVER_PHASE_4_STAGE_1.md).
Mirrors the conventions already established in
``app.modules.academics.schemas`` (``_StrictRequest`` base, explicit
field validators, ``Page[...]`` for list responses).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.attendance.models import AttendanceStatus, AuditOutcome

# Maximum number of student records accepted in a single bulk-attendance
# request. An MVP-conservative bound (Phase 4 brief, instruction C),
# deliberately in the same spirit as
# ``app.modules.bulk_imports.parser.MAX_IMPORT_ROWS`` (500) but smaller,
# since a single classroom's roster is expected to be well under 200
# students and a bulk-attendance request is synchronous, not a background
# job.
MAX_BULK_ATTENDANCE_ROWS = 200


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BulkAttendanceRecordIn(_StrictRequest):
    """One student's attendance status within a bulk-attendance request."""

    student_profile_id: uuid.UUID
    status: AttendanceStatus
    remarks: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _normalize_remarks(self) -> BulkAttendanceRecordIn:
        if self.remarks is not None:
            stripped = self.remarks.strip()
            self.remarks = stripped or None
        return self


class BulkAttendanceRequest(_StrictRequest):
    """A single classroom/subject/date batch of student attendance records."""

    classroom_id: uuid.UUID
    subject_id: uuid.UUID
    attendance_date: date
    records: list[BulkAttendanceRecordIn] = Field(
        ...,
        min_length=1,
        max_length=MAX_BULK_ATTENDANCE_ROWS,
        description=(
            "Must be non-empty and contain no more than "
            f"{MAX_BULK_ATTENDANCE_ROWS} records; no duplicate "
            "student_profile_id values are allowed within one request."
        ),
    )

    @model_validator(mode="after")
    def _reject_duplicate_students(self) -> BulkAttendanceRequest:
        seen: set[uuid.UUID] = set()
        for record in self.records:
            if record.student_profile_id in seen:
                raise ValueError(
                    "records must not contain duplicate student_profile_id values "
                    f"({record.student_profile_id})."
                )
            seen.add(record.student_profile_id)
        return self


class AttendanceRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    student_profile_id: uuid.UUID
    classroom_id: uuid.UUID
    subject_id: uuid.UUID
    attendance_date: date
    status: AttendanceStatus
    remarks: str | None
    marked_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class AttendanceRosterStudentRead(BaseModel):
    """Minimal active-classroom identity needed to mark or confirm attendance."""

    student_profile_id: uuid.UUID
    full_name: str
    roll_number: str | None


class AttendanceBulkSaveResult(BaseModel):
    """The typed result of ``AttendanceService.bulk_save`` (Stage 2).

    Deliberately does not echo the submitted batch (no per-record status/
    remarks) — only counts and the resulting record IDs, per the Phase 4
    Stage 2 brief's instruction A ("Do not echo the full submitted
    batch.").
    """

    model_config = ConfigDict(from_attributes=True)

    classroom_id: uuid.UUID
    subject_id: uuid.UUID
    attendance_date: date
    created_count: int
    updated_count: int
    total_count: int
    record_ids: list[uuid.UUID]


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_user_id: uuid.UUID
    action: str
    outcome: AuditOutcome
    entity_type: str
    entity_id: uuid.UUID | None
    classroom_id: uuid.UUID | None
    subject_id: uuid.UUID | None
    request_id: str | None
    event_metadata: dict[str, Any]
    created_at: datetime


# --- Stage 3: read/statistics/export response shapes ------------------------
#
# Grouped-statistics rows and the daily-attendance response are always
# built from typed repository dataclasses
# (``app.modules.attendance.repository.StudentAttendanceAggregate`` /
# ``ClassroomAttendanceAggregate``) or ORM rows — never a raw SQLAlchemy
# ``Row`` passed straight through, per the Stage 3 brief. Paginated list
# responses (detail, student self-detail, audit logs) reuse the existing
# project-wide ``app.schemas.pagination.Page[...]`` convention rather than
# introducing a parallel pagination shape.


class AttendanceStatsGrouping(StrEnum):
    """The three supported ``GET /attendance/stats`` grouping modes."""

    OVERALL = "overall"
    STUDENT = "student"
    CLASSROOM = "classroom"


class DailyAttendanceResponse(BaseModel):
    """The exact (classroom, subject, date) daily-attendance scope.

    ``records`` is an empty list (never an error) when nothing has been
    marked yet for this scope — a typed empty result, per the Stage 3
    brief's "return a typed empty result when no attendance exists."
    """

    classroom_id: uuid.UUID
    subject_id: uuid.UUID
    attendance_date: date
    records: list[AttendanceRecordRead]


class AttendanceStatsOverall(BaseModel):
    """Raw, explainable overall counts — no ranking, trend, or prediction."""

    total_count: int
    present_count: int
    absent_count: int
    attendance_percentage: float


class AttendanceStatsByStudent(BaseModel):
    """One student's raw counts within the requested scope."""

    student_profile_id: uuid.UUID
    total_count: int
    present_count: int
    absent_count: int
    attendance_percentage: float


class AttendanceStatsByClassroom(BaseModel):
    """One classroom's raw counts within the requested scope."""

    classroom_id: uuid.UUID
    total_count: int
    present_count: int
    absent_count: int
    attendance_percentage: float


class AttendanceStatsResponse(BaseModel):
    """The typed ``GET /attendance/stats`` response, for any grouping mode.

    Exactly one of ``overall``/``by_student``/``by_classroom`` is
    populated, matching ``grouping``. This single response shape (rather
    than three separate endpoints/response models) keeps the router's
    ``response_model`` declaration simple while still returning fully
    typed rows for every grouping mode — never a raw dict or SQLAlchemy
    ``Row``.
    """

    grouping: AttendanceStatsGrouping
    classroom_id: uuid.UUID
    subject_id: uuid.UUID
    overall: AttendanceStatsOverall | None = None
    by_student: list[AttendanceStatsByStudent] | None = None
    by_classroom: list[AttendanceStatsByClassroom] | None = None


class StudentSelfStatsResponse(BaseModel):
    """``GET /attendance/me/stats`` — the caller's own raw statistics only."""

    student_profile_id: uuid.UUID
    total_count: int
    present_count: int
    absent_count: int
    attendance_percentage: float
