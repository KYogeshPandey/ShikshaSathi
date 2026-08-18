"""Application-defined errors for biometric enrollment and photo ingestion.

Genuine infrastructure failures (disk full, permission denied, database
unreachable mid-write) are deliberately **not** modeled as ``AppError``
subclasses here — matching this application's existing philosophy (see
``app.core.exceptions.AppError``'s docstring: "an expected failure
mode"). Those propagate as ordinary exceptions and are handled by the
generic 500 handler, exactly like every other module in this backend;
see app/modules/biometric_enrollment/service.py's docstring for how
compensating cleanup still runs via ``try``/``finally`` around them.
"""

from __future__ import annotations

from fastapi import status

from app.core.exceptions import AppError


class EnrollmentInactiveStudentError(AppError):
    code = "ENROLLMENT_INACTIVE_STUDENT"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self) -> None:
        super().__init__("Cannot enroll biometric data for an inactive student profile.")


class EnrollmentNotFoundError(AppError):
    code = "ENROLLMENT_NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self) -> None:
        super().__init__("Biometric enrollment not found.")


class EnrollmentSampleNotFoundError(AppError):
    code = "ENROLLMENT_SAMPLE_NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self) -> None:
        super().__init__("Biometric sample not found.")


class EnrollmentAlreadyActiveError(AppError):
    """Raised when ``create`` is called but an ACTIVE sample already exists.

    The client should call the replace endpoint instead.
    """

    code = "ENROLLMENT_ALREADY_ACTIVE"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self) -> None:
        super().__init__(
            "This student already has an active biometric enrollment. "
            "Use the replace endpoint to update it."
        )


class EnrollmentDeletionPendingError(AppError):
    code = "ENROLLMENT_DELETION_PENDING"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self) -> None:
        super().__init__(
            "This enrollment has a deletion in progress and cannot accept new samples."
        )


class EnrollmentNoActiveSampleError(AppError):
    """Raised by replace/delete when there is no ACTIVE sample to act on."""

    code = "ENROLLMENT_NO_ACTIVE_SAMPLE"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self) -> None:
        super().__init__("This student has no active biometric sample yet.")


class EnrollmentDuplicateContentError(AppError):
    code = "ENROLLMENT_DUPLICATE_CONTENT"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self) -> None:
        super().__init__("This exact image has already been enrolled for this student.")


# --- image validation -------------------------------------------------------


class EnrollmentImageEmptyError(AppError):
    code = "ENROLLMENT_IMAGE_EMPTY"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("The uploaded file is empty.")


class EnrollmentImageTooLargeError(AppError):
    code = "ENROLLMENT_IMAGE_TOO_LARGE"
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE

    def __init__(self, max_bytes: int) -> None:
        super().__init__(
            f"The uploaded image exceeds the {max_bytes}-byte limit.",
            details={"max_bytes": max_bytes},
        )


class EnrollmentImageDecodeError(AppError):
    code = "ENROLLMENT_IMAGE_DECODE_FAILED"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("The uploaded file is not a valid, decodable image.")


class EnrollmentImageFormatNotAllowedError(AppError):
    code = "ENROLLMENT_IMAGE_FORMAT_NOT_ALLOWED"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self, allowed: frozenset[str]) -> None:
        super().__init__(
            "The uploaded image format is not allowed.",
            details={"allowed_formats": sorted(allowed)},
        )


class EnrollmentImageDimensionsInvalidError(AppError):
    code = "ENROLLMENT_IMAGE_DIMENSIONS_INVALID"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("The uploaded image has invalid (non-positive) dimensions.")


class EnrollmentImageTooLargeDimensionsError(AppError):
    code = "ENROLLMENT_IMAGE_DIMENSIONS_TOO_LARGE"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__(
            "The uploaded image's dimensions exceed the maximum allowed "
            "(this also guards against decompression-bomb-style images)."
        )


class EnrollmentImageAnimatedNotAllowedError(AppError):
    code = "ENROLLMENT_IMAGE_ANIMATED_NOT_ALLOWED"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("Animated/multi-frame images are not allowed for enrollment.")


class EnrollmentImageMimeMismatchError(AppError):
    code = "ENROLLMENT_IMAGE_MIME_MISMATCH"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__(
            "The declared content type does not match the image's actual, decoded format."
        )


# --- bulk ZIP ingestion -------------------------------------------------------


class BulkEnrollmentZipTooLargeError(AppError):
    code = "BULK_ENROLLMENT_ZIP_TOO_LARGE"
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE

    def __init__(self, max_bytes: int) -> None:
        super().__init__(
            f"The uploaded archive exceeds the {max_bytes}-byte limit.",
            details={"max_bytes": max_bytes},
        )


class BulkEnrollmentZipInvalidError(AppError):
    code = "BULK_ENROLLMENT_ZIP_INVALID"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self, reason: str) -> None:
        super().__init__("The uploaded archive could not be read.", details={"reason": reason})


class BulkEnrollmentValidationError(AppError):
    """Raised when the archive fails whole-batch pre-extraction validation.

    Carries every discovered problem in ``details["errors"]`` (each a
    ``{"filename_or_row": ..., "code": ..., "message": ...}`` dict) so a
    caller sees every reason the batch was rejected in one response,
    matching ``app.modules.bulk_imports``' per-row error-reporting
    convention. Raising this (rather than the first error found) means
    **zero** enrollments are ever created for a rejected batch — see
    app/modules/biometric_enrollment/bulk_service.py's module docstring
    for the full atomicity contract.
    """

    code = "BULK_ENROLLMENT_VALIDATION_FAILED"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self, errors: list[dict[str, object]]) -> None:
        super().__init__(
            "The archive was rejected: every row must be valid for any row to be enrolled.",
            details={"errors": errors},
        )
