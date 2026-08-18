"""In-memory, formula-safe CSV export for the filtered attendance report."""

from __future__ import annotations

import csv
import io

from app.modules.academics.models import Classroom, Subject
from app.modules.attendance.csv_export import safe_csv_text_cell, safe_filename_component
from app.modules.reports.schemas import AttendanceReportResponse

REPORT_CSV_COLUMNS: tuple[str, ...] = (
    "attendance_date",
    "student_profile_id",
    "roll_number",
    "status",
    "remarks",
)


def build_report_csv(report: AttendanceReportResponse) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(REPORT_CSV_COLUMNS)
    for row in report.details:
        writer.writerow(
            [
                row.attendance_date.isoformat(),
                str(row.student_profile_id),
                safe_csv_text_cell(row.roll_number),
                row.status.value,
                safe_csv_text_cell(row.remarks),
            ]
        )
    return buffer.getvalue()


def build_report_filename(
    *, classroom: Classroom, subject: Subject, report: AttendanceReportResponse, suffix: str
) -> str:
    classroom_code = safe_filename_component(classroom.code, fallback="classroom")
    subject_code = safe_filename_component(subject.code, fallback="subject")
    period = report.period.month or (
        f"{report.period.date_from.isoformat()}_{report.period.date_to.isoformat()}"
    )
    safe_period = safe_filename_component(period, fallback="period")
    return f"attendance-report-{classroom_code}-{subject_code}-{safe_period}.{suffix}"


__all__ = ["REPORT_CSV_COLUMNS", "build_report_csv", "build_report_filename"]
