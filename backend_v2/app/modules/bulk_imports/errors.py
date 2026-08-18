"""Stable client errors for bounded academic bulk imports."""

from __future__ import annotations

from fastapi import status

from app.core.exceptions import AppError


class BulkImportFileError(AppError):
    code = "BULK_IMPORT_INVALID_FILE"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self, message: str = "The import file could not be parsed.") -> None:
        super().__init__(message)


class BulkImportTooLargeError(AppError):
    code = "BULK_IMPORT_FILE_TOO_LARGE"
    status_code = status.HTTP_413_CONTENT_TOO_LARGE

    def __init__(self, max_bytes: int) -> None:
        super().__init__(
            "The import file exceeds the allowed size.",
            details={"max_bytes": max_bytes},
        )


class BulkImportRowLimitError(AppError):
    code = "BULK_IMPORT_ROW_LIMIT_EXCEEDED"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self, max_rows: int) -> None:
        super().__init__(
            "The import file contains too many data rows.",
            details={"max_rows": max_rows},
        )
