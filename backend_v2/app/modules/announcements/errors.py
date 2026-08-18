"""Application-defined errors for the announcements domain.

Same ``AppError`` contract as ``app.modules.academics.errors`` /
``app.modules.profiles.errors`` — handled by the existing centralized
exception handler, so Stage 2 routes need no local ``try/except``.
"""

from __future__ import annotations

from fastapi import status

from app.core.exceptions import AppError


class AnnouncementNotFoundError(AppError):
    code = "ANNOUNCEMENT_NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self) -> None:
        super().__init__("Announcement not found.")


class AnnouncementAuthorNotFoundError(AppError):
    """Raised when ``author_user_id`` does not reference an existing user."""

    code = "ANNOUNCEMENT_AUTHOR_NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self) -> None:
        super().__init__("The referenced author does not exist.")


class InvalidAnnouncementAudienceError(AppError):
    """Raised when ``audience`` and ``classroom_ids`` are inconsistent.

    Specifically: a non-classroom audience with one or more
    ``classroom_ids`` given, or ``audience == "classroom"`` with none
    given. Re-checked at the repository layer even though the Pydantic
    schema (``AnnouncementCreate``) already validates it, since the
    repository can be called directly (tests, scripts) bypassing the
    schema — the same belt-and-suspenders pattern used throughout this
    phase.
    """

    code = "ANNOUNCEMENT_INVALID_AUDIENCE"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__(
            "Only a 'classroom' announcement may list classrooms, and it "
            "must list at least one classroom."
        )


class AnnouncementClassroomReferenceError(AppError):
    """Raised when a ``classroom_ids`` entry does not reference an existing classroom."""

    code = "ANNOUNCEMENT_CLASSROOM_INVALID_REFERENCE"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("One or more referenced classrooms do not exist.")


class AnnouncementInactiveClassroomError(AppError):
    code = "ANNOUNCEMENT_INACTIVE_CLASSROOM"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self) -> None:
        super().__init__("Announcements cannot target an inactive classroom.")
