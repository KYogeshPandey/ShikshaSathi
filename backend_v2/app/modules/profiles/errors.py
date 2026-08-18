"""Application-defined errors for the profiles domain."""

from __future__ import annotations

from fastapi import status

from app.core.exceptions import AppError


class UserNotFoundError(AppError):
    code = "USER_NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self) -> None:
        super().__init__("User not found.")


class ProfileRoleMismatchError(AppError):
    """Raised when creating a profile whose type does not match the User's role.

    E.g. creating a ``TeacherProfile`` for a user whose ``role`` is
    ``student`` (or vice versa). See ``app.modules.profiles.models``'
    module docstring for why this is enforced here rather than as a
    database CHECK constraint.
    """

    code = "PROFILE_ROLE_MISMATCH"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self, expected_role: str) -> None:
        super().__init__(f"The linked user's role must be '{expected_role}'.")


class InactiveProfileUserError(AppError):
    code = "PROFILE_USER_INACTIVE"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self) -> None:
        super().__init__("A profile cannot be created for an inactive user.")


class TeacherProfileAlreadyExistsError(AppError):
    code = "TEACHER_PROFILE_ALREADY_EXISTS"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self) -> None:
        super().__init__("This user already has a teacher profile.")


class TeacherEmployeeCodeAlreadyExistsError(AppError):
    code = "TEACHER_EMPLOYEE_CODE_ALREADY_EXISTS"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self) -> None:
        super().__init__("A teacher profile with this employee code already exists.")


class StudentProfileAlreadyExistsError(AppError):
    code = "STUDENT_PROFILE_ALREADY_EXISTS"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self) -> None:
        super().__init__("This user already has a student profile.")


class DuplicateClassroomRollNumberError(AppError):
    """Raised when a classroom already has a student with the given roll number."""

    code = "CLASSROOM_ROLL_NUMBER_ALREADY_EXISTS"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self) -> None:
        super().__init__("A student with this roll number already exists in this classroom.")


class TeacherProfileNotFoundError(AppError):
    code = "TEACHER_PROFILE_NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self) -> None:
        super().__init__("Teacher profile not found.")


class StudentProfileNotFoundError(AppError):
    code = "STUDENT_PROFILE_NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self) -> None:
        super().__init__("Student profile not found.")


class ClassroomMembershipReferenceError(AppError):
    code = "CLASSROOM_MEMBERSHIP_INVALID_REFERENCE"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("The referenced classroom does not exist.")


class InactiveClassroomMembershipError(AppError):
    code = "CLASSROOM_MEMBERSHIP_INACTIVE_CLASSROOM"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self) -> None:
        super().__init__("A student cannot be assigned to an inactive classroom.")


class InvalidClassroomMembershipError(AppError):
    code = "CLASSROOM_MEMBERSHIP_INVALID_STATE"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("A roll number requires an assigned classroom.")
