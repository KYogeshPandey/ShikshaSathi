"""Focused Phase 7 integration-unblocker tests for the attendance roster API."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.attendance.models import AttendanceRecord
from app.modules.users.models import UserRole
from app.tests.attendance_http_helpers import seed_attendance_scope
from app.tests.phase3_http_helpers import auth_headers, create_resource, seed_user


def _roster_params(scope: dict[str, object]) -> dict[str, str]:
    classroom = scope["classroom"]
    subject = scope["subject"]
    assert isinstance(classroom, dict)
    assert isinstance(subject, dict)
    return {"classroom_id": str(classroom["id"]), "subject_id": str(subject["id"])}


async def _attendance_count(session: AsyncSession) -> int:
    statement = select(func.count()).select_from(AttendanceRecord)
    return int((await session.execute(statement)).scalar_one())


async def test_admin_roster_is_minimal_active_classroom_membership_only(
    client_db: AsyncClient,
    db_session: AsyncSession,
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="roster-admin")
    outsider = await seed_user(
        db_session,
        email="roster-outsider@example.com",
        role=UserRole.STUDENT,
    )
    other_classroom = await create_resource(
        client_db,
        path="/api/v1/classrooms",
        payload={"name": "Other roster room", "code": "roster-other-room"},
        user=scope["admin"],
    )
    await create_resource(
        client_db,
        path="/api/v1/student-profiles",
        payload={
            "user_id": str(outsider.id),
            "classroom_id": other_classroom["id"],
            "roll_number": "99",
        },
        user=scope["admin"],
    )
    inactive_profile = scope["student_profile_2"]
    assert isinstance(inactive_profile, dict)
    deactivate = await client_db.delete(
        f"/api/v1/student-profiles/{inactive_profile['id']}",
        headers=auth_headers(scope["admin"]),
    )
    assert deactivate.status_code == 200

    count_before = await _attendance_count(db_session)
    response = await client_db.get(
        "/api/v1/attendance/roster",
        params=_roster_params(scope),
        headers=auth_headers(scope["admin"]),
    )
    count_after = await _attendance_count(db_session)

    assert response.status_code == 200
    body = response.json()
    active_profile = scope["student_profile_1"]
    assert isinstance(active_profile, dict)
    assert body == [
        {
            "student_profile_id": active_profile["id"],
            "full_name": scope["student_1"].full_name,
            "roll_number": active_profile["roll_number"],
        }
    ]
    assert set(body[0]) == {"student_profile_id", "full_name", "roll_number"}
    assert not any(
        fragment in key
        for key in body[0]
        for fragment in ("biometric", "embedding", "candidate", "password", "token", "path")
    )
    assert count_after == count_before == 0


async def test_teacher_can_fetch_exact_assigned_scope_roster(
    client_db: AsyncClient,
    db_session: AsyncSession,
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="roster-teacher")

    response = await client_db.get(
        "/api/v1/attendance/roster",
        params=_roster_params(scope),
        headers=auth_headers(scope["teacher"]),
    )

    assert response.status_code == 200
    assert [item["roll_number"] for item in response.json()] == ["01", "02"]


async def test_unassigned_teacher_roster_scope_is_concealed(
    client_db: AsyncClient,
    db_session: AsyncSession,
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="roster-denied")

    response = await client_db.get(
        "/api/v1/attendance/roster",
        params=_roster_params(scope),
        headers=auth_headers(scope["other_teacher"]),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ATTENDANCE_SCOPE_NOT_FOUND"


async def test_assignment_to_different_subject_does_not_grant_roster_access(
    client_db: AsyncClient,
    db_session: AsyncSession,
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="roster-exact")
    profile_response = await client_db.get(
        "/api/v1/teacher-profiles/me",
        headers=auth_headers(scope["other_teacher"]),
    )
    assert profile_response.status_code == 200
    other_subject = await create_resource(
        client_db,
        path="/api/v1/subjects",
        payload={"name": "Other roster subject", "code": "roster-other-subject"},
        user=scope["admin"],
    )
    classroom = scope["classroom"]
    assert isinstance(classroom, dict)
    await create_resource(
        client_db,
        path="/api/v1/teacher-assignments",
        payload={
            "teacher_profile_id": profile_response.json()["id"],
            "classroom_id": classroom["id"],
            "subject_id": other_subject["id"],
        },
        user=scope["admin"],
    )

    denied = await client_db.get(
        "/api/v1/attendance/roster",
        params=_roster_params(scope),
        headers=auth_headers(scope["other_teacher"]),
    )
    allowed = await client_db.get(
        "/api/v1/attendance/roster",
        params={"classroom_id": classroom["id"], "subject_id": other_subject["id"]},
        headers=auth_headers(scope["other_teacher"]),
    )

    assert denied.status_code == 404
    assert denied.json()["error"]["code"] == "ATTENDANCE_SCOPE_NOT_FOUND"
    assert allowed.status_code == 200
    assert len(allowed.json()) == 2


async def test_authorized_empty_classroom_returns_empty_list(
    client_db: AsyncClient,
    db_session: AsyncSession,
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="roster-empty")
    classroom = await create_resource(
        client_db,
        path="/api/v1/classrooms",
        payload={"name": "Empty roster room", "code": "roster-empty-room"},
        user=scope["admin"],
    )
    subject = scope["subject"]
    assert isinstance(subject, dict)

    response = await client_db.get(
        "/api/v1/attendance/roster",
        params={"classroom_id": classroom["id"], "subject_id": subject["id"]},
        headers=auth_headers(scope["admin"]),
    )

    assert response.status_code == 200
    assert response.json() == []
