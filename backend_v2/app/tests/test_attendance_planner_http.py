"""Student-only recovery planner API, schedule scope, and read-only behavior."""

from __future__ import annotations

from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.attendance.models import AttendanceRecord
from app.modules.profiles.models import TeacherProfile
from app.tests.attendance_http_helpers import mark_attendance, seed_attendance_scope
from app.tests.phase3_http_helpers import auth_headers, create_resource


async def _teacher_profile_id(session: AsyncSession, user_id: object) -> str:
    value = (
        await session.execute(select(TeacherProfile.id).where(TeacherProfile.user_id == user_id))
    ).scalar_one()
    return str(value)


async def _create_timetable_entry(
    client: AsyncClient,
    scope: dict,
    session: AsyncSession,
    *,
    subject_id: str,
    start_time: str,
) -> None:
    await create_resource(
        client,
        path="/api/v1/timetable-entries",
        payload={
            "classroom_id": scope["classroom"]["id"],
            "subject_id": subject_id,
            "teacher_profile_id": await _teacher_profile_id(session, scope["teacher"].id),
            "day_of_week": date.today().strftime("%A").lower(),
            "start_time": start_time,
            "end_time": f"{int(start_time[:2]) + 1:02d}:00",
        },
        user=scope["admin"],
    )


async def test_student_plan_is_self_only_schedule_aware_and_read_only(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="recovery-plan")
    yesterday = date.today() - timedelta(days=1)
    await mark_attendance(
        client_db,
        user=scope["admin"],
        classroom_id=scope["classroom"]["id"],
        subject_id=scope["subject"]["id"],
        attendance_date=yesterday.isoformat(),
        records=[
            {"student_profile_id": scope["student_profile_1"]["id"], "status": "present"},
            {"student_profile_id": scope["student_profile_2"]["id"], "status": "absent"},
        ],
    )
    await mark_attendance(
        client_db,
        user=scope["admin"],
        classroom_id=scope["classroom"]["id"],
        subject_id=scope["subject"]["id"],
        attendance_date=(yesterday - timedelta(days=1)).isoformat(),
        records=[
            {"student_profile_id": scope["student_profile_1"]["id"], "status": "absent"},
        ],
    )
    await _create_timetable_entry(
        client_db,
        scope,
        db_session,
        subject_id=scope["subject"]["id"],
        start_time="09:00",
    )
    await _create_timetable_entry(
        client_db,
        scope,
        db_session,
        subject_id=scope["subject"]["id"],
        start_time="10:00",
    )
    before = int(
        (
            await db_session.execute(
                select(func.count())
                .select_from(AttendanceRecord)
                .where(AttendanceRecord.student_profile_id == scope["student_profile_1"]["id"])
            )
        ).scalar_one()
    )

    response = await client_db.post(
        "/api/v1/attendance/me/recovery-plan",
        json={"target_percentage": 75, "deadline": date.today().isoformat()},
        headers=auth_headers(scope["student_1"]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["current"] == {
        "attended": 1,
        "held": 2,
        "absent": 1,
        "percentage": 50.0,
    }
    assert body["classes_required"] == 2
    assert body["scheduled_classes_remaining"] == 2
    assert body["scheduled_teaching_days_remaining"] == 1
    assert body["teaching_days_required"] == 1
    assert body["recovery_date"] == date.today().isoformat()
    assert body["subjects"][0]["subject_name"] == scope["subject"]["name"]
    assert "student_profile_id" not in response.text

    after = int(
        (
            await db_session.execute(
                select(func.count())
                .select_from(AttendanceRecord)
                .where(AttendanceRecord.student_profile_id == scope["student_profile_1"]["id"])
            )
        ).scalar_one()
    )
    assert after == before == 2


async def test_subject_filter_counts_only_subject_schedule_and_history(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="recovery-subject")
    second_subject = await create_resource(
        client_db,
        path="/api/v1/subjects",
        payload={"name": "Recovery Science", "code": "recovery-science"},
        user=scope["admin"],
    )
    teacher_profile_id = await _teacher_profile_id(db_session, scope["teacher"].id)
    await create_resource(
        client_db,
        path="/api/v1/teacher-assignments",
        payload={
            "teacher_profile_id": teacher_profile_id,
            "classroom_id": scope["classroom"]["id"],
            "subject_id": second_subject["id"],
        },
        user=scope["admin"],
    )
    await _create_timetable_entry(
        client_db,
        scope,
        db_session,
        subject_id=scope["subject"]["id"],
        start_time="09:00",
    )
    await _create_timetable_entry(
        client_db,
        scope,
        db_session,
        subject_id=second_subject["id"],
        start_time="10:00",
    )
    await mark_attendance(
        client_db,
        user=scope["admin"],
        classroom_id=scope["classroom"]["id"],
        subject_id=second_subject["id"],
        attendance_date=(date.today() - timedelta(days=1)).isoformat(),
        records=[
            {"student_profile_id": scope["student_profile_1"]["id"], "status": "present"},
        ],
    )

    response = await client_db.post(
        "/api/v1/attendance/me/recovery-plan",
        json={
            "target_percentage": 75,
            "deadline": date.today().isoformat(),
            "subject_id": second_subject["id"],
        },
        headers=auth_headers(scope["student_1"]),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scope"] == "subject"
    assert body["subject_name"] == "Recovery Science"
    assert body["current"]["attended"] == body["current"]["held"] == 1
    assert body["scheduled_classes_remaining"] == 1


async def test_planner_rejects_arbitrary_student_identity_and_non_student_roles(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="recovery-auth")
    payload = {"target_percentage": 75, "deadline": date.today().isoformat()}
    arbitrary = await client_db.post(
        "/api/v1/attendance/me/recovery-plan",
        json={**payload, "student_profile_id": scope["student_profile_2"]["id"]},
        headers=auth_headers(scope["student_1"]),
    )
    assert arbitrary.status_code == 422

    for user_key in ("teacher", "admin"):
        response = await client_db.post(
            "/api/v1/attendance/me/recovery-plan",
            json=payload,
            headers=auth_headers(scope[user_key]),
        )
        assert response.status_code == 403


async def test_planner_validates_deadline_and_handles_no_future_schedule(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="recovery-deadline")
    invalid = await client_db.post(
        "/api/v1/attendance/me/recovery-plan",
        json={
            "target_percentage": 75,
            "deadline": (date.today() - timedelta(days=1)).isoformat(),
        },
        headers=auth_headers(scope["student_1"]),
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "ATTENDANCE_PLANNER_INVALID_DEADLINE"

    no_schedule = await client_db.post(
        "/api/v1/attendance/me/recovery-plan",
        json={"target_percentage": 75, "deadline": date.today().isoformat()},
        headers=auth_headers(scope["student_1"]),
    )
    assert no_schedule.status_code == 200
    assert no_schedule.json()["scheduled_classes_remaining"] == 0
    assert no_schedule.json()["status"] == "not_reachable"
