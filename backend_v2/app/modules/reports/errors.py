"""Stable client-facing errors for bounded attendance reports."""

from fastapi import status

from app.core.exceptions import AppError


class ReportPeriodRequiredError(AppError):
    code = "REPORT_PERIOD_REQUIRED"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("Provide either month or both date_from and date_to.")


class ReportPeriodConflictError(AppError):
    code = "REPORT_PERIOD_CONFLICT"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("month cannot be combined with date_from or date_to.")


class ReportInvalidPeriodError(AppError):
    code = "REPORT_INVALID_PERIOD"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("The reporting period is invalid or exceeds 366 days.")


class ReportTooLargeError(AppError):
    code = "REPORT_TOO_LARGE"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("The report exceeds the maximum supported result size.")


class ReportStudentNotInScopeError(AppError):
    code = "REPORT_STUDENT_NOT_IN_SCOPE"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("The requested student is not active in this classroom.")
