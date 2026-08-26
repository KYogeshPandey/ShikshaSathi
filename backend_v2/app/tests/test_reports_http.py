"""Phase 8 attendance reports: contracts, authorization, exports, and query shape."""

from __future__ import annotations

import csv
import io
import os
import tempfile
from datetime import date
from typing import Any, cast

import pytest
from httpx import AsyncClient
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.modules.academics.models import Classroom, Subject
from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.reports.csv_export import REPORT_CSV_COLUMNS
from app.modules.reports.pdf_export import build_report_pdf
from app.modules.reports.repository import ReportsRepository
from app.modules.reports.schemas import (
    AttendanceReportDetailRow,
    AttendanceReportResponse,
    AttendanceReportSummary,
    ReportPeriodRead,
)
from app.modules.users.models import UserRole
from app.tests.attendance_http_helpers import mark_attendance, seed_attendance_scope
from app.tests.phase3_http_helpers import auth_headers, create_resource, seed_user

REPORT_DATE_1 = "2026-08-01"
REPORT_DATE_2 = "2026-08-02"
REPORT_DATE_3 = "2026-08-03"


QueryValue = str | int | float | bool | None


def _params(scope: dict[str, Any], **extra: QueryValue) -> dict[str, QueryValue]:
    return {
        "classroom_id": scope["classroom"]["id"],
        "subject_id": scope["subject"]["id"],
        "month": "2026-08",
        **extra,
    }


async def _mark(
    client: AsyncClient,
    scope: dict[str, Any],
    *,
    attendance_date: str,
    student_key: str,
    status: str,
    remarks: str | None = None,
) -> None:
    record: dict[str, object] = {
        "student_profile_id": scope[student_key]["id"],
        "status": status,
    }
    if remarks is not None:
        record["remarks"] = remarks
    await mark_attendance(
        client,
        user=scope["admin"],
        classroom_id=scope["classroom"]["id"],
        subject_id=scope["subject"]["id"],
        attendance_date=attendance_date,
        records=[record],
    )


async def test_attendance_report_month_summary_detail_and_direct_db_spot_check(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="report-summary")
    scope["student_1"].full_name = "Yogesh Pandey"
    await db_session.commit()
    await _mark(
        client_db,
        scope,
        attendance_date=REPORT_DATE_1,
        student_key="student_profile_1",
        status="present",
    )
    await _mark(
        client_db,
        scope,
        attendance_date=REPORT_DATE_2,
        student_key="student_profile_1",
        status="absent",
    )
    await _mark(
        client_db,
        scope,
        attendance_date=REPORT_DATE_3,
        student_key="student_profile_1",
        status="present",
    )

    response = await client_db.get(
        "/api/v1/reports/attendance",
        params=_params(scope),
        headers=auth_headers(scope["admin"]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["period"] == {
        "month": "2026-08",
        "date_from": "2026-08-01",
        "date_to": "2026-08-31",
    }
    assert body["summary"] == {
        "total_count": 3,
        "present_count": 2,
        "absent_count": 1,
        "attendance_percentage": 66.67,
    }
    assert [row["attendance_date"] for row in body["details"]] == [
        REPORT_DATE_1,
        REPORT_DATE_2,
        REPORT_DATE_3,
    ]
    assert {row["full_name"] for row in body["details"]} == {"Yogesh Pandey"}

    database_total = int(
        (
            await db_session.execute(
                select(func.count())
                .select_from(AttendanceRecord)
                .where(
                    AttendanceRecord.classroom_id == scope["classroom"]["id"],
                    AttendanceRecord.subject_id == scope["subject"]["id"],
                    AttendanceRecord.attendance_date >= date(2026, 8, 1),
                    AttendanceRecord.attendance_date <= date(2026, 8, 31),
                )
            )
        ).scalar_one()
    )
    assert body["summary"]["total_count"] == database_total == 3


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/reports/attendance",
        "/api/v1/reports/defaulters",
        "/api/v1/reports/leaderboard",
        "/api/v1/reports/attendance/export.csv",
        "/api/v1/reports/attendance/export.pdf",
    ],
)
async def test_assigned_teacher_can_access_every_report_contract(
    client_db: AsyncClient, db_session: AsyncSession, path: str
) -> None:
    scope = await seed_attendance_scope(
        client_db, db_session, suffix=f"teacher-{path.rsplit('/', 1)[-1].replace('.', '-')}"
    )
    response = await client_db.get(
        path,
        params=_params(scope),
        headers=auth_headers(scope["teacher"]),
    )
    assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/reports/attendance",
        "/api/v1/reports/defaulters",
        "/api/v1/reports/leaderboard",
        "/api/v1/reports/attendance/export.csv",
        "/api/v1/reports/attendance/export.pdf",
    ],
)
async def test_students_cannot_access_arbitrary_reports(
    client_db: AsyncClient, db_session: AsyncSession, path: str
) -> None:
    scope = await seed_attendance_scope(
        client_db, db_session, suffix=f"student-{path.rsplit('/', 1)[-1].replace('.', '-')}"
    )
    response = await client_db.get(
        path,
        params=_params(scope),
        headers=auth_headers(scope["student_1"]),
    )
    assert response.status_code == 403


async def test_unassigned_teacher_scope_is_concealed(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="report-denied")
    response = await client_db.get(
        "/api/v1/reports/leaderboard",
        params=_params(scope),
        headers=auth_headers(scope["other_teacher"]),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ATTENDANCE_SCOPE_NOT_FOUND"


@pytest.mark.parametrize(
    ("params", "error_code"),
    [
        ({}, "REPORT_PERIOD_REQUIRED"),
        (
            {"month": "2026-08", "date_from": "2026-08-01", "date_to": "2026-08-31"},
            "REPORT_PERIOD_CONFLICT",
        ),
        (
            {"date_from": "2026-08-02", "date_to": "2026-08-01"},
            "REPORT_INVALID_PERIOD",
        ),
        (
            {"date_from": "2025-01-01", "date_to": "2026-01-02"},
            "REPORT_INVALID_PERIOD",
        ),
        ({"month": "2026-13"}, "REPORT_INVALID_PERIOD"),
    ],
)
async def test_report_period_contract_is_strict_and_bounded(
    client_db: AsyncClient,
    db_session: AsyncSession,
    params: dict[str, str],
    error_code: str,
) -> None:
    scope = await seed_attendance_scope(
        client_db, db_session, suffix=f"period-{error_code.lower()}-{len(params)}"
    )
    response = await client_db.get(
        "/api/v1/reports/attendance",
        params={
            "classroom_id": scope["classroom"]["id"],
            "subject_id": scope["subject"]["id"],
            **params,
        },
        headers=auth_headers(scope["admin"]),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == error_code


async def test_student_filter_must_be_active_member_of_requested_classroom(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="student-scope")
    outsider_user = await seed_user(
        db_session, email="report-outsider@example.com", role=UserRole.STUDENT
    )
    other_classroom = await create_resource(
        client_db,
        path="/api/v1/classrooms",
        payload={"name": "Report outsider room", "code": "report-outsider-room"},
        user=scope["admin"],
    )
    outsider = await create_resource(
        client_db,
        path="/api/v1/student-profiles",
        payload={
            "user_id": str(outsider_user.id),
            "classroom_id": other_classroom["id"],
            "roll_number": "99",
        },
        user=scope["admin"],
    )
    response = await client_db.get(
        "/api/v1/reports/attendance",
        params=_params(scope, student_profile_id=outsider["id"]),
        headers=auth_headers(scope["admin"]),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REPORT_STUDENT_NOT_IN_SCOPE"


async def test_defaulters_include_zero_records_and_exclude_exact_threshold(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="defaulters")
    scope["student_2"].full_name = "Krish Sharma"
    await db_session.commit()
    await _mark(
        client_db,
        scope,
        attendance_date=REPORT_DATE_1,
        student_key="student_profile_1",
        status="present",
    )
    await _mark(
        client_db,
        scope,
        attendance_date=REPORT_DATE_2,
        student_key="student_profile_1",
        status="absent",
    )
    response = await client_db.get(
        "/api/v1/reports/defaulters",
        params=_params(scope, threshold=50),
        headers=auth_headers(scope["admin"]),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["threshold"] == 50
    assert body["zero_attendance_policy"] == "included_as_zero_percent"
    assert body["students"] == [
        {
            "student_profile_id": scope["student_profile_2"]["id"],
            "roll_number": "02",
            "full_name": "Krish Sharma",
            "total_count": 0,
            "present_count": 0,
            "absent_count": 0,
            "attendance_percentage": 0.0,
        }
    ]


async def test_leaderboard_is_deterministic_and_includes_zero_record_students(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="leaderboard")
    third_user = await seed_user(
        db_session, email="report-third@example.com", role=UserRole.STUDENT
    )
    third_profile = await create_resource(
        client_db,
        path="/api/v1/student-profiles",
        payload={
            "user_id": str(third_user.id),
            "classroom_id": scope["classroom"]["id"],
            "roll_number": "00",
        },
        user=scope["admin"],
    )
    await _mark(
        client_db,
        scope,
        attendance_date=REPORT_DATE_1,
        student_key="student_profile_1",
        status="present",
    )
    await mark_attendance(
        client_db,
        user=scope["admin"],
        classroom_id=scope["classroom"]["id"],
        subject_id=scope["subject"]["id"],
        attendance_date=REPORT_DATE_1,
        records=[{"student_profile_id": third_profile["id"], "status": "present"}],
    )
    response = await client_db.get(
        "/api/v1/reports/leaderboard",
        params=_params(scope),
        headers=auth_headers(scope["admin"]),
    )
    assert response.status_code == 200, response.text
    students = response.json()["students"]
    assert [
        (row["rank"], row["roll_number"], row["attendance_percentage"]) for row in students
    ] == [
        (1, "00", 100.0),
        (2, "01", 100.0),
        (3, "02", 0.0),
    ]


async def test_inactive_roster_members_and_their_history_are_excluded(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="inactive")
    await _mark(
        client_db,
        scope,
        attendance_date=REPORT_DATE_1,
        student_key="student_profile_2",
        status="present",
    )
    response = await client_db.delete(
        f"/api/v1/student-profiles/{scope['student_profile_2']['id']}",
        headers=auth_headers(scope["admin"]),
    )
    assert response.status_code == 200

    attendance = await client_db.get(
        "/api/v1/reports/attendance",
        params=_params(scope),
        headers=auth_headers(scope["admin"]),
    )
    leaderboard = await client_db.get(
        "/api/v1/reports/leaderboard",
        params=_params(scope),
        headers=auth_headers(scope["admin"]),
    )
    assert attendance.json()["summary"]["total_count"] == 0
    assert attendance.json()["details"] == []
    assert [row["student_profile_id"] for row in leaderboard.json()["students"]] == [
        scope["student_profile_1"]["id"]
    ]


async def test_report_csv_matches_student_filter_and_escapes_formula_cells(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="report-csv")
    scope["student_1"].full_name = "Yogesh Pandey"
    await db_session.commit()
    await _mark(
        client_db,
        scope,
        attendance_date=REPORT_DATE_1,
        student_key="student_profile_1",
        status="present",
        remarks="=2+2",
    )
    await _mark(
        client_db,
        scope,
        attendance_date=REPORT_DATE_1,
        student_key="student_profile_2",
        status="absent",
    )
    before = set(os.listdir(tempfile.gettempdir()))
    response = await client_db.get(
        "/api/v1/reports/attendance/export.csv",
        params=_params(scope, student_profile_id=scope["student_profile_1"]["id"]),
        headers=auth_headers(scope["admin"]),
    )
    after = set(os.listdir(tempfile.gettempdir()))
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"].endswith('.csv"')
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8"))))
    assert rows[0] == list(REPORT_CSV_COLUMNS)
    assert len(rows) == 2
    assert rows[1][1] == "01"
    assert rows[1][2] == "Yogesh Pandey"
    assert scope["student_profile_1"]["id"] not in rows[1]
    assert rows[1][-1] == "'=2+2"
    assert after - before == set()


async def test_empty_report_csv_is_header_only(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="report-csv-empty")
    response = await client_db.get(
        "/api/v1/reports/attendance/export.csv",
        params=_params(scope),
        headers=auth_headers(scope["admin"]),
    )
    assert list(csv.reader(io.StringIO(response.text))) == [list(REPORT_CSV_COLUMNS)]


async def test_report_pdf_headers_content_and_no_temp_file(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="report-pdf")
    scope["student_1"].full_name = "Yogesh Pandey"
    await db_session.commit()
    await _mark(
        client_db,
        scope,
        attendance_date=REPORT_DATE_1,
        student_key="student_profile_1",
        status="present",
    )
    before = set(os.listdir(tempfile.gettempdir()))
    response = await client_db.get(
        "/api/v1/reports/attendance/export.pdf",
        params=_params(scope),
        headers=auth_headers(scope["admin"]),
    )
    after = set(os.listdir(tempfile.gettempdir()))
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].endswith('.pdf"')
    assert response.content.startswith(b"%PDF")
    assert b"Attendance report" in response.content
    assert b"Attendance: 100.00%" in response.content
    assert b"Yogesh Pandey" in response.content
    assert scope["student_profile_1"]["id"].encode() not in response.content
    assert after - before == set()


def test_report_pdf_paginates_large_bounded_result_in_memory() -> None:
    student_id = "00000000-0000-0000-0000-000000000001"
    report = AttendanceReportResponse(
        classroom_id="00000000-0000-0000-0000-000000000010",
        subject_id="00000000-0000-0000-0000-000000000020",
        student_profile_id=None,
        period=ReportPeriodRead(
            month="2026-08", date_from=date(2026, 8, 1), date_to=date(2026, 8, 31)
        ),
        summary=AttendanceReportSummary(
            total_count=80, present_count=80, absent_count=0, attendance_percentage=100
        ),
        details=[
            AttendanceReportDetailRow(
                attendance_date=date(2026, 8, (index % 28) + 1),
                student_profile_id=student_id,
                roll_number=str(index),
                full_name="Yogesh Pandey",
                status=AttendanceStatus.PRESENT,
                remarks=None,
            )
            for index in range(80)
        ],
    )
    classroom = Classroom(name="Room", code="room", is_active=True)
    subject = Subject(name="Subject", code="subject", is_active=True)
    pdf = build_report_pdf(report=report, classroom=classroom, subject=subject)
    assert pdf.startswith(b"%PDF")
    assert pdf.count(b"/Type /Page") >= 2


async def test_active_roster_aggregate_is_one_set_based_select(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="set-based")
    engine = cast(AsyncEngine, db_session.bind)
    select_count = 0

    def count_selects(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        nonlocal select_count
        if statement.lstrip().upper().startswith("SELECT"):
            select_count += 1

    event.listen(engine.sync_engine, "before_cursor_execute", count_selects)
    try:
        rows = await ReportsRepository(db_session).aggregate_active_roster(
            classroom_id=scope["classroom"]["id"],
            subject_id=scope["subject"]["id"],
            date_from=date(2026, 8, 1),
            date_to=date(2026, 8, 31),
            limit=1_001,
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count_selects)

    assert len(rows) == 2
    assert select_count == 1
