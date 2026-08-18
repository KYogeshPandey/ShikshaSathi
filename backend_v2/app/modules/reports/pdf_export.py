"""Bounded, multi-page attendance-report PDF generation entirely in memory."""

from __future__ import annotations

import io
from collections.abc import Iterable

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

from app.modules.academics.models import Classroom, Subject
from app.modules.reports.schemas import AttendanceReportDetailRow, AttendanceReportResponse

_PAGE_HEIGHT = float(A4[1])
_LEFT = 36
_TOP = _PAGE_HEIGHT - 38
_BOTTOM = 42
_ROW_HEIGHT = 16


def _plain(value: str | None, *, limit: int) -> str:
    """Keep PDF cells single-line and bounded without interpreting markup."""
    normalized = " ".join((value or "").split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1]}…"


def _draw_header(canvas: Canvas, *, title: str, subtitle: str, summary: str) -> float:
    canvas.setFont("Helvetica-Bold", 15)
    canvas.drawString(_LEFT, _TOP, title)
    canvas.setFont("Helvetica", 9)
    canvas.drawString(_LEFT, _TOP - 18, subtitle)
    canvas.drawString(_LEFT, _TOP - 32, summary)
    y = _TOP - 56
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(_LEFT, y, "Date")
    canvas.drawString(105, y, "Roll number")
    canvas.drawString(205, y, "Student profile ID")
    canvas.drawString(430, y, "Status")
    canvas.drawString(480, y, "Remarks")
    return y - _ROW_HEIGHT


def _draw_rows(
    canvas: Canvas,
    *,
    rows: Iterable[AttendanceReportDetailRow],
    title: str,
    subtitle: str,
    summary: str,
) -> None:
    y = _draw_header(canvas, title=title, subtitle=subtitle, summary=summary)
    canvas.setFont("Helvetica", 7)
    for row in rows:
        if y < _BOTTOM:
            canvas.showPage()
            y = _draw_header(canvas, title=title, subtitle=subtitle, summary=summary)
            canvas.setFont("Helvetica", 7)
        canvas.drawString(_LEFT, y, row.attendance_date.isoformat())
        canvas.drawString(105, y, _plain(row.roll_number, limit=16) or "—")
        canvas.drawString(205, y, str(row.student_profile_id))
        canvas.drawString(430, y, row.status.value)
        canvas.drawString(480, y, _plain(row.remarks, limit=17) or "—")
        y -= _ROW_HEIGHT


def build_report_pdf(
    *, report: AttendanceReportResponse, classroom: Classroom, subject: Subject
) -> bytes:
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=A4, pageCompression=0)
    period = report.period.month or (
        f"{report.period.date_from.isoformat()} to {report.period.date_to.isoformat()}"
    )
    summary = report.summary
    _draw_rows(
        canvas,
        rows=report.details,
        title="Attendance report",
        subtitle=f"Classroom: {classroom.code}   Subject: {subject.code}   Period: {period}",
        summary=(
            f"Total: {summary.total_count}   Present: {summary.present_count}   "
            f"Absent: {summary.absent_count}   Attendance: {summary.attendance_percentage:.2f}%"
        ),
    )
    canvas.save()
    return buffer.getvalue()


__all__ = ["build_report_pdf"]
