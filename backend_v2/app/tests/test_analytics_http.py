"""Milestone 3 role-aware analytics contracts, calculations, and query shape."""

from __future__ import annotations

from datetime import date
from typing import Any, cast

from httpx import AsyncClient
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.modules.analytics.repository import AnalyticsRepository
from app.modules.attendance.models import AttendanceRecord
from app.tests.attendance_http_helpers import mark_attendance, seed_attendance_scope
from app.tests.phase3_http_helpers import auth_headers


async def _mark_day(
    client: AsyncClient,
    scope: dict[str, Any],
    *,
    attendance_date: str,
    records: list[tuple[str, str]],
) -> None:
    await mark_attendance(
        client,
        user=scope["admin"],
        classroom_id=scope["classroom"]["id"],
        subject_id=scope["subject"]["id"],
        attendance_date=attendance_date,
        records=[
            {
                "student_profile_id": scope[student_key]["id"],
                "status": status,
            }
            for student_key, status in records
        ],
    )


async def _seed_two_periods(
    client: AsyncClient, session: AsyncSession, *, suffix: str
) -> dict[str, Any]:
    scope = await seed_attendance_scope(client, session, suffix=suffix)
    await _mark_day(
        client,
        scope,
        attendance_date="2026-08-10",
        records=[("student_profile_1", "present"), ("student_profile_2", "absent")],
    )
    await _mark_day(
        client,
        scope,
        attendance_date="2026-08-18",
        records=[("student_profile_1", "present"), ("student_profile_2", "absent")],
    )
    await _mark_day(
        client,
        scope,
        attendance_date="2026-08-19",
        records=[("student_profile_1", "present")],
    )
    return scope


async def test_admin_overview_calculates_equal_periods_and_population(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await _seed_two_periods(client_db, db_session, suffix="analytics-admin")

    response = await client_db.get(
        "/api/v1/analytics/overview",
        params={"days": 7, "date_to": "2026-08-20"},
        headers=auth_headers(scope["admin"]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["role"] == "admin"
    assert body["period"] == {
        "days": 7,
        "date_from": "2026-08-14",
        "date_to": "2026-08-20",
    }
    assert body["attendance"] == {
        "total_count": 3,
        "present_count": 2,
        "absent_count": 1,
        "attendance_percentage": 66.67,
    }
    assert body["comparison"] == {
        "period": {
            "days": 7,
            "date_from": "2026-08-07",
            "date_to": "2026-08-13",
        },
        "attendance": {
            "total_count": 2,
            "present_count": 1,
            "absent_count": 1,
            "attendance_percentage": 50.0,
        },
        "percentage_point_change": 16.67,
    }
    assert body["admin_population"] == {
        "active_students": 2,
        "active_teachers": 2,
        "active_classrooms": 1,
        "active_subjects": 1,
    }
    assert body["teacher_scope"] is None
    assert body["student_context"] is None
    assert len(body["trend"]) == 7
    assert body["trend"][0]["attendance_date"] == "2026-08-14"
    assert body["trend"][0]["total_count"] == 0
    assert body["trend"][4]["attendance_percentage"] == 50.0
    assert body["attention_classrooms"][0]["classroom_code"] == "att-room-analytics-admin"
    assert body["attendance_definition"] == ("present_marked_records_divided_by_all_marked_records")
    assert body["missing_records_policy"] == "excluded_unmarked"

    raw_current_total = int(
        (
            await db_session.execute(
                select(func.count())
                .select_from(AttendanceRecord)
                .where(
                    AttendanceRecord.attendance_date >= date(2026, 8, 14),
                    AttendanceRecord.attendance_date <= date(2026, 8, 20),
                )
            )
        ).scalar_one()
    )
    assert raw_current_total == body["attendance"]["total_count"] == 3


async def test_teacher_overview_is_limited_to_active_assignments(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await _seed_two_periods(client_db, db_session, suffix="analytics-teacher")
    params: dict[str, str | int] = {"days": 7, "date_to": "2026-08-20"}

    assigned_response = await client_db.get(
        "/api/v1/analytics/overview",
        params=params,
        headers=auth_headers(scope["teacher"]),
    )
    unrelated_response = await client_db.get(
        "/api/v1/analytics/overview",
        params=params,
        headers=auth_headers(scope["other_teacher"]),
    )

    assert assigned_response.status_code == 200, assigned_response.text
    assigned = assigned_response.json()
    assert assigned["role"] == "teacher"
    assert assigned["attendance"]["total_count"] == 3
    assert assigned["teacher_scope"] == {
        "assigned_classrooms": 1,
        "assigned_subjects": 1,
        "timetable_slots": 0,
    }
    assert assigned["admin_population"] is None
    assert assigned["attention_classrooms"] == []

    assert unrelated_response.status_code == 200, unrelated_response.text
    unrelated = unrelated_response.json()
    assert unrelated["attendance"] == {
        "total_count": 0,
        "present_count": 0,
        "absent_count": 0,
        "attendance_percentage": 0.0,
    }
    assert unrelated["comparison"]["percentage_point_change"] is None
    assert unrelated["teacher_scope"] == {
        "assigned_classrooms": 0,
        "assigned_subjects": 0,
        "timetable_slots": 0,
    }


async def test_student_overview_contains_only_the_callers_records(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await _seed_two_periods(client_db, db_session, suffix="analytics-student")
    params: dict[str, str | int] = {"days": 7, "date_to": "2026-08-20"}

    first_response = await client_db.get(
        "/api/v1/analytics/overview",
        params=params,
        headers=auth_headers(scope["student_1"]),
    )
    second_response = await client_db.get(
        "/api/v1/analytics/overview",
        params=params,
        headers=auth_headers(scope["student_2"]),
    )

    assert first_response.status_code == 200, first_response.text
    first = first_response.json()
    assert first["role"] == "student"
    assert first["attendance"] == {
        "total_count": 2,
        "present_count": 2,
        "absent_count": 0,
        "attendance_percentage": 100.0,
    }
    assert first["student_context"] == {"roll_number": "01"}
    assert first["admin_population"] is None
    assert first["teacher_scope"] is None
    assert first["attention_classrooms"] == []

    assert second_response.status_code == 200, second_response.text
    second = second_response.json()
    assert second["attendance"] == {
        "total_count": 1,
        "present_count": 0,
        "absent_count": 1,
        "attendance_percentage": 0.0,
    }
    assert second["student_context"] == {"roll_number": "02"}


async def test_empty_overview_and_request_validation(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="analytics-empty")

    response = await client_db.get(
        "/api/v1/analytics/overview",
        params={"days": 30, "date_to": "2026-08-20"},
        headers=auth_headers(scope["admin"]),
    )
    invalid = await client_db.get(
        "/api/v1/analytics/overview",
        params={"days": 14},
        headers=auth_headers(scope["admin"]),
    )
    invalid_date = await client_db.get(
        "/api/v1/analytics/overview",
        params={"date_to": "not-a-date"},
        headers=auth_headers(scope["admin"]),
    )
    unauthenticated = await client_db.get("/api/v1/analytics/overview")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["attendance"]["total_count"] == 0
    assert body["attendance"]["attendance_percentage"] == 0.0
    assert body["comparison"]["percentage_point_change"] is None
    assert len(body["trend"]) == 30
    assert all(point["total_count"] == 0 for point in body["trend"])
    assert body["attention_classrooms"] == []
    assert invalid.status_code == 422
    assert invalid_date.status_code == 422
    assert unauthenticated.status_code == 401


async def test_admin_daily_aggregate_is_one_set_based_select(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_two_periods(client_db, db_session, suffix="analytics-query")
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
        rows = await AnalyticsRepository(db_session).daily_for_admin(
            date_from=date(2026, 8, 7),
            date_to=date(2026, 8, 20),
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count_selects)

    assert sum(row.total_count for row in rows) == 5
    assert select_count == 1
