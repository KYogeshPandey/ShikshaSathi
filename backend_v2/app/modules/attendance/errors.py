"""Application-defined errors for the attendance and audit-log domain.

Same ``AppError`` contract as every other module (e.g.
``app.modules.academics.errors``) — handled by the existing centralized
exception handler (app/core/exceptions.py), so callers never need a local
``try/except`` block to keep the standard envelope.

Stage 1 defined only the errors needed by the repositories (uniqueness
conflicts and not-found lookups). Stage 2 adds the authorization/
ownership-scope and batch-validation errors used by
``app.modules.attendance.service.AttendanceService`` — see
docs/HANDOVER_PHASE_4_STAGE_2.md.

``AttendanceScopeNotFoundError`` is deliberately the *only* error raised
for every flavor of teacher-scope denial (missing/inactive teacher
profile, missing/inactive assignment, or a classroom/subject that does
not exist) — this is the existing concealment convention already
established in ``app.modules.auth.authorization`` (a denied/unrelated
object looks identical to a genuinely missing one). The precise reason
is only ever recorded server-side, in the blocked audit log's
``event_metadata`` — never in the response returned to the client.
"""

from __future__ import annotations

from fastapi import status

from app.core.exceptions import AppError


class AttendanceRecordAlreadyExistsError(AppError):
    """Raised on a duplicate (student, classroom, subject, date) insert.

    Stage 2's service layer is expected to upsert (update-if-exists)
    rather than ever hit this in normal operation; it exists as a
    database-level backstop against a concurrent duplicate insert (e.g. a
    race between two overlapping requests), translated from the raw
    ``IntegrityError`` into a stable, client-safe error.
    """

    code = "ATTENDANCE_RECORD_ALREADY_EXISTS"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self) -> None:
        super().__init__(
            "An attendance record already exists for this student, classroom, subject, and date."
        )


class AttendanceRecordNotFoundError(AppError):
    code = "ATTENDANCE_RECORD_NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self) -> None:
        super().__init__("Attendance record not found.")


class AttendanceInvalidDateRangeError(AppError):
    """Raised when a filter's ``date_from`` is after its ``date_to``."""

    code = "ATTENDANCE_INVALID_DATE_RANGE"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("date_from must not be after date_to.")


class AuditLogNotFoundError(AppError):
    code = "AUDIT_LOG_NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self) -> None:
        super().__init__("Audit log entry not found.")


# --- Stage 2: service-layer batch validation and authorization -------------


class AttendanceBatchTooLargeError(AppError):
    """Defense-in-depth backstop behind the schema's own ``max_length``.

    Raised only when ``AttendanceService.bulk_save`` is reached with a
    ``records`` list longer than
    ``app.modules.attendance.schemas.MAX_BULK_ATTENDANCE_ROWS`` — normal
    HTTP callers can never trigger this, since ``BulkAttendanceRequest``
    already enforces the cap at request-parsing time.
    """

    code = "ATTENDANCE_BATCH_TOO_LARGE"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("A bulk attendance request cannot exceed the maximum batch size.")


class AttendanceDuplicateStudentInBatchError(AppError):
    """Defense-in-depth backstop behind the schema's own duplicate check.

    Raised only when ``AttendanceService.bulk_save`` is reached with a
    repeated ``student_profile_id`` — normal HTTP callers can never
    trigger this, since ``BulkAttendanceRequest`` already rejects
    duplicates at request-parsing time.
    """

    code = "ATTENDANCE_DUPLICATE_STUDENT_IN_BATCH"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("The batch contains a duplicate student_profile_id.")


class AttendanceRoleNotPermittedError(AppError):
    """Defense-in-depth backstop behind the router's future ``require_roles``.

    A student (or any role other than admin/teacher) reaching
    ``AttendanceService.bulk_save`` directly — bypassing the role
    dependency a future router will apply — is rejected here too.
    """

    code = "ATTENDANCE_ROLE_NOT_PERMITTED"
    status_code = status.HTTP_403_FORBIDDEN

    def __init__(self) -> None:
        super().__init__("This role is not permitted to mark attendance.")


class AttendanceScopeNotFoundError(AppError):
    """The teacher-ownership concealment error — always a plain 404.

    Raised for every flavor of teacher-scope denial: missing/inactive
    teacher profile, missing/inactive teacher assignment, or a
    classroom/subject that does not exist. See this module's docstring
    for why these are deliberately not distinguished in the response.
    """

    code = "ATTENDANCE_SCOPE_NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self) -> None:
        super().__init__("Attendance scope not found.")


class AttendanceStudentNotFoundError(AppError):
    code = "ATTENDANCE_STUDENT_NOT_FOUND"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("One or more students in this batch could not be found.")


class AttendanceInactiveStudentError(AppError):
    code = "ATTENDANCE_INACTIVE_STUDENT"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("One or more students in this batch are inactive.")


class AttendanceStudentNotInClassroomError(AppError):
    code = "ATTENDANCE_STUDENT_NOT_IN_CLASSROOM"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__(
            "One or more students in this batch do not belong to the target classroom."
        )
