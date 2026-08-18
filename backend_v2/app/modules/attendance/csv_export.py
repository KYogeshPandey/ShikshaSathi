"""In-memory attendance CSV generation, with formula-injection protection.

Phase 4 Stage 3. Kept as a small, focused helper module (not folded into
``router.py``) so the CSV-building logic — column order, cell escaping,
filename construction — is independently readable and testable without
needing a running FastAPI app or database.

Never writes a temporary file: the whole document is built in a single
in-memory ``io.StringIO`` buffer and returned as a ``str``, which the
router encodes to UTF-8 bytes for the HTTP response body.
"""

from __future__ import annotations

import csv
import io
import re

from app.modules.academics.models import Classroom, Subject
from app.modules.attendance.repository import AttendanceExportRow

# Stable, documented column order — never reordered based on data content.
CSV_COLUMNS: tuple[str, ...] = (
    "attendance_date",
    "classroom_code",
    "subject_code",
    "student_profile_id",
    "student_roll_number",
    "status",
    "remarks",
    "marked_by_user_id",
    "created_at",
    "updated_at",
)

# Spreadsheet applications (Excel, LibreOffice, Google Sheets) treat a cell
# beginning with any of these characters as a formula to evaluate on open —
# the classic "CSV injection" vector. A single leading apostrophe is the
# standard, widely-supported escape that forces the cell to be treated as
# literal text instead (the apostrophe itself is not displayed).
_FORMULA_TRIGGER_PREFIXES = ("=", "+", "-", "@")

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9_-]+")


def escape_csv_formula_cell(value: str) -> str:
    if value.startswith(_FORMULA_TRIGGER_PREFIXES):
        return f"'{value}"
    return value


def safe_csv_text_cell(value: str | None) -> str:
    """Every user-controlled text cell goes through this before writing.

    Applied to ``remarks`` (the only genuinely free-text, user-controlled
    field in an attendance record) and, defensively, to
    ``student_roll_number`` — an admin-entered field that is not
    currently validated against a strict character set.
    """
    if value is None:
        return ""
    return escape_csv_formula_cell(value)


def safe_filename_component(value: str, *, fallback: str) -> str:
    """Normalize a server-authorized label for Content-Disposition filenames."""
    return _UNSAFE_FILENAME_CHARS.sub("_", value) or fallback


def build_attendance_csv(
    *, classroom: Classroom, subject: Subject, rows: list[AttendanceExportRow]
) -> str:
    """Build the full CSV document (header + data rows) as an in-memory string.

    Always UTF-8-safe (plain ``str``, encoded by the router). Always
    includes the header row, even when ``rows`` is empty — a valid CSV
    with zero data rows, per the Stage 3 brief's "empty result returns
    headers" requirement. ``classroom_code``/``subject_code`` come from
    the already-authorized ``Classroom``/``Subject`` (constant for every
    row in a single export, since ``classroom_id``/``subject_id`` are
    required, exact-scope filters), never re-derived per row.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        writer.writerow(
            [
                row.attendance_date.isoformat(),
                classroom.code,
                subject.code,
                str(row.student_profile_id),
                safe_csv_text_cell(row.student_roll_number),
                row.status.value,
                safe_csv_text_cell(row.remarks),
                str(row.marked_by_user_id),
                row.created_at.isoformat(),
                row.updated_at.isoformat(),
            ]
        )
    return buffer.getvalue()


def build_export_filename(*, classroom: Classroom, subject: Subject) -> str:
    """A safe, server-controlled filename — never derived from client input.

    Built only from the already-authorized classroom/subject codes (which
    are admin-set, not attacker-controlled at request time) plus a fixed
    prefix/suffix. Any character outside ``[A-Za-z0-9_-]`` is replaced
    with ``_`` as a defensive normalization, so the resulting
    ``Content-Disposition`` header value is always a plain, unquoted-safe
    token regardless of how a code was originally entered.
    """
    safe_classroom = safe_filename_component(classroom.code, fallback="classroom")
    safe_subject = safe_filename_component(subject.code, fallback="subject")
    return f"attendance-{safe_classroom}-{safe_subject}.csv"


__all__ = [
    "CSV_COLUMNS",
    "build_attendance_csv",
    "build_export_filename",
    "escape_csv_formula_cell",
    "safe_csv_text_cell",
    "safe_filename_component",
]
