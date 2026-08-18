"""Phase 4 Stage 3 HTTP coverage: ``GET /api/v1/attendance/stats``.

Covers all three grouping modes (overall/student/classroom), the fixed
zero-result and rounding rules, date-range filtering, and the same
concealed-teacher-scope behavior as the detail/daily endpoints.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.attendance.models import AuditLog, AuditOutcome
from app.modules.users.models import UserRole
from app.tests.attendance_http_helpers import mark_attendance, seed_attendance_scope
from app.tests.phase3_http_helpers import auth_headers, create_resource, seed_user

TODAY = date.today().isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


async def test_stats_overall_counts_and_percentage(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="stats-overall")
    await mark_attendance(
        client_db,
        user=scope["admin"],
        classroom_id=scope["classroom"]["id"],
        subject_id=scope["subject"]["id"],
        attendance_date=TODAY,
        records=[
            {"student_profile_id": scope["student_profile_1"]["id"], "status": "present"},
            {"student_profile_id": scope["student_profile_2"]["id"], "status": "absent"},
        ],
    )
    response = await client_db.get(
        "/api/v1/attendance/stats",
        params={"classroom_id": scope["classroom"]["id"], "subject_id": scope["subject"]["id"]},
        headers=auth_headers(scope["admin"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["grouping"] == "overall"
    overall = body["overall"]
    assert overall["total_count"] == 2
    assert overall["present_count"] == 1
    assert overall["absent_count"] == 1
    assert overall["attendance_percentage"] == 50.0
    assert overall["present_count"] + overall["absent_count"] == overall["total_count"]


async def test_stats_grouped_by_student(client_db: AsyncClient, db_session: AsyncSession) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="stats-student")
    await mark_attendance(
        client_db,
        user=scope["admin"],
        classroom_id=scope["classroom"]["id"],
        subject_id=scope["subject"]["id"],
        attendance_date=YESTERDAY,
        records=[
            {"student_profile_id": scope["student_profile_1"]["id"], "status": "present"},
            {"student_profile_id": scope["student_profile_2"]["id"], "status": "present"},
        ],
    )
    await mark_attendance(
        client_db,
        user=scope["admin"],
        classroom_id=scope["classroom"]["id"],
        subject_id=scope["subject"]["id"],
        attendance_date=TODAY,
        records=[
            {"student_profile_id": scope["student_profile_1"]["id"], "status": "absent"},
            {"student_profile_id": scope["student_profile_2"]["id"], "status": "present"},
        ],
    )
    response = await client_db.get(
        "/api/v1/attendance/stats",
        params={
            "classroom_id": scope["classroom"]["id"],
            "subject_id": scope["subject"]["id"],
            "grouping": "student",
        },
        headers=auth_headers(scope["admin"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["grouping"] == "student"
    by_student = {row["student_profile_id"]: row for row in body["by_student"]}
    student_1_row = by_student[scope["student_profile_1"]["id"]]
    assert student_1_row["total_count"] == 2
    assert student_1_row["present_count"] == 1
    assert student_1_row["absent_count"] == 1
    assert student_1_row["attendance_percentage"] == 50.0

    student_2_row = by_student[scope["student_profile_2"]["id"]]
    assert student_2_row["total_count"] == 2
    assert student_2_row["present_count"] == 2
    assert student_2_row["attendance_percentage"] == 100.0


async def test_stats_grouped_by_classroom(client_db: AsyncClient, db_session: AsyncSession) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="stats-classroom")
    await mark_attendance(
        client_db,
        user=scope["admin"],
        classroom_id=scope["classroom"]["id"],
        subject_id=scope["subject"]["id"],
        attendance_date=TODAY,
        records=[
            {"student_profile_id": scope["student_profile_1"]["id"], "status": "present"},
            {"student_profile_id": scope["student_profile_2"]["id"], "status": "absent"},
        ],
    )
    response = await client_db.get(
        "/api/v1/attendance/stats",
        params={
            "classroom_id": scope["classroom"]["id"],
            "subject_id": scope["subject"]["id"],
            "grouping": "classroom",
        },
        headers=auth_headers(scope["admin"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["grouping"] == "classroom"
    assert len(body["by_classroom"]) == 1
    row = body["by_classroom"][0]
    assert row["classroom_id"] == scope["classroom"]["id"]
    assert row["total_count"] == 2
    assert row["present_count"] == 1
    assert row["absent_count"] == 1


async def test_stats_zero_rows_returns_zero_percentage(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="stats-zero")
    response = await client_db.get(
        "/api/v1/attendance/stats",
        params={"classroom_id": scope["classroom"]["id"], "subject_id": scope["subject"]["id"]},
        headers=auth_headers(scope["admin"]),
    )
    assert response.status_code == 200
    overall = response.json()["overall"]
    assert overall["total_count"] == 0
    assert overall["present_count"] == 0
    assert overall["absent_count"] == 0
    assert overall["attendance_percentage"] == 0.0


async def test_stats_percentage_rounds_to_two_decimals(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="stats-round")
    other_user = await _seed_extra_student(client_db, db_session, scope, suffix="stats-round")
    await mark_attendance(
        client_db,
        user=scope["admin"],
        classroom_id=scope["classroom"]["id"],
        subject_id=scope["subject"]["id"],
        attendance_date=TODAY,
        records=[
            {"student_profile_id": scope["student_profile_1"]["id"], "status": "present"},
            {"student_profile_id": scope["student_profile_2"]["id"], "status": "absent"},
            {"student_profile_id": other_user["id"], "status": "absent"},
        ],
    )
    response = await client_db.get(
        "/api/v1/attendance/stats",
        params={"classroom_id": scope["classroom"]["id"], "subject_id": scope["subject"]["id"]},
        headers=auth_headers(scope["admin"]),
    )
    assert response.status_code == 200
    overall = response.json()["overall"]
    # 1 present out of 3 => 33.333...% rounded to 2 decimal places.
    assert overall["attendance_percentage"] == 33.33


async def _seed_extra_student(
    client_db: AsyncClient, db_session: AsyncSession, scope: dict[str, Any], *, suffix: str
) -> dict[str, Any]:
    student_3 = await seed_user(
        db_session, email=f"att-student3-{suffix}@example.com", role=UserRole.STUDENT
    )
    return await create_resource(
        client_db,
        path="/api/v1/student-profiles",
        payload={
            "user_id": str(student_3.id),
            "classroom_id": scope["classroom"]["id"],
            "roll_number": "03",
        },
        user=scope["admin"],
    )


async def test_stats_date_range_filtering(client_db: AsyncClient, db_session: AsyncSession) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="stats-date")
    await mark_attendance(
        client_db,
        user=scope["admin"],
        classroom_id=scope["classroom"]["id"],
        subject_id=scope["subject"]["id"],
        attendance_date=YESTERDAY,
        records=[{"student_profile_id": scope["student_profile_1"]["id"], "status": "absent"}],
    )
    await mark_attendance(
        client_db,
        user=scope["admin"],
        classroom_id=scope["classroom"]["id"],
        subject_id=scope["subject"]["id"],
        attendance_date=TODAY,
        records=[{"student_profile_id": scope["student_profile_1"]["id"], "status": "present"}],
    )
    response = await client_db.get(
        "/api/v1/attendance/stats",
        params={
            "classroom_id": scope["classroom"]["id"],
            "subject_id": scope["subject"]["id"],
            "date_from": TODAY,
            "date_to": TODAY,
        },
        headers=auth_headers(scope["admin"]),
    )
    assert response.status_code == 200
    overall = response.json()["overall"]
    assert overall["total_count"] == 1
    assert overall["present_count"] == 1


async def test_stats_unrelated_teacher_denied_and_audited(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="stats-unrelated")
    response = await client_db.get(
        "/api/v1/attendance/stats",
        params={"classroom_id": scope["classroom"]["id"], "subject_id": scope["subject"]["id"]},
        headers=auth_headers(scope["other_teacher"]),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ATTENDANCE_SCOPE_NOT_FOUND"

    rows = (
        (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.actor_user_id == scope["other_teacher"].id,
                    AuditLog.outcome == AuditOutcome.BLOCKED,
                    AuditLog.action == "attendance.read_stats",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
