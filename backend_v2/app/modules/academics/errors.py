"""Application-defined errors for the academic domain.

Same ``AppError`` contract as ``app.modules.users.errors`` — handled by the
existing centralized exception handler, so Stage 2 routes keep the standard
envelope without local ``try/except`` blocks.
"""

from __future__ import annotations

from fastapi import status

from app.core.exceptions import AppError


class ClassroomCodeAlreadyExistsError(AppError):
    code = "CLASSROOM_CODE_ALREADY_EXISTS"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self) -> None:
        super().__init__("A classroom with this code already exists.")


class SubjectCodeAlreadyExistsError(AppError):
    code = "SUBJECT_CODE_ALREADY_EXISTS"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self) -> None:
        super().__init__("A subject with this code already exists.")


class ClassroomNotFoundError(AppError):
    code = "CLASSROOM_NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self) -> None:
        super().__init__("Classroom not found.")


class SubjectNotFoundError(AppError):
    code = "SUBJECT_NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self) -> None:
        super().__init__("Subject not found.")


class DuplicateTeacherAssignmentError(AppError):
    """Raised when the same (teacher, classroom, subject) triple is assigned twice."""

    code = "TEACHER_ASSIGNMENT_ALREADY_EXISTS"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self) -> None:
        super().__init__("This teacher is already assigned to this subject in this classroom.")


class TeacherAssignmentReferenceError(AppError):
    """Raised when an assignment references a teacher/classroom/subject that does not exist."""

    code = "TEACHER_ASSIGNMENT_INVALID_REFERENCE"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("The referenced teacher profile, classroom, or subject does not exist.")


class TeacherAssignmentNotFoundError(AppError):
    code = "TEACHER_ASSIGNMENT_NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self) -> None:
        super().__init__("Teacher assignment not found.")


class InactiveAcademicReferenceError(AppError):
    code = "INACTIVE_ACADEMIC_REFERENCE"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self) -> None:
        super().__init__("The referenced profile, classroom, or subject is inactive.")


class TimetableCollisionError(AppError):
    """Raised on an exact classroom/teacher + day + start-time collision.

    See app/modules/academics/models.py's ``TimetableEntry`` docstring for
    exactly what "collision" means in Stage 1 (identical start time only,
    not general interval overlap).
    """

    code = "TIMETABLE_SLOT_COLLISION"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self) -> None:
        super().__init__(
            "This classroom or teacher already has a timetable entry at this day and start time."
        )


class TimetableReferenceError(AppError):
    """Raised when a timetable entry references a classroom/subject/teacher that does not exist."""

    code = "TIMETABLE_INVALID_REFERENCE"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("The referenced classroom, subject, or teacher profile does not exist.")


class InvalidTimetableSlotError(AppError):
    """Raised when ``start_time`` is not strictly before ``end_time``."""

    code = "TIMETABLE_INVALID_SLOT"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("The timetable entry's start time must be before its end time.")


class TimetableEntryNotFoundError(AppError):
    code = "TIMETABLE_ENTRY_NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self) -> None:
        super().__init__("Timetable entry not found.")


class TimetableAssignmentRequiredError(AppError):
    code = "TIMETABLE_ASSIGNMENT_REQUIRED"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self) -> None:
        super().__init__(
            "The teacher must have an active assignment for this classroom and subject."
        )
