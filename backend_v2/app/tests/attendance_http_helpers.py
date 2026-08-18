"""Shared seed helpers for Phase 4 Stage 3 attendance/audit-log HTTP tests.

Reuses ``app.tests.phase3_http_helpers`` (``seed_user``, ``auth_headers``,
``create_resource``) exactly as-is — no fixture logic is duplicated here,
only attendance-specific scaffolding built on top of it: one classroom,
one subject, an assigned teacher, an unrelated teacher, and two students,
plus a small helper to call ``POST /attendance/bulk`` and assert success.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User, UserRole
from app.tests.phase3_http_helpers import auth_headers, create_resource, seed_user


async def seed_attendance_scope(
    client: AsyncClient, session: AsyncSession, *, suffix: str
) -> dict[str, Any]:
    """One classroom/subject, an assigned + an unrelated teacher, two students.

    ``suffix`` keeps emails/codes unique across test functions sharing one
    database (matches the convention already used by
    ``test_phase3_scoped_access_http.py``'s per-test seed helper).
    """
    admin = await seed_user(session, email=f"att-admin-{suffix}@example.com", role=UserRole.ADMIN)
    teacher = await seed_user(
        session, email=f"att-teacher-{suffix}@example.com", role=UserRole.TEACHER
    )
    other_teacher = await seed_user(
        session, email=f"att-other-teacher-{suffix}@example.com", role=UserRole.TEACHER
    )
    student_1 = await seed_user(
        session, email=f"att-student1-{suffix}@example.com", role=UserRole.STUDENT
    )
    student_2 = await seed_user(
        session, email=f"att-student2-{suffix}@example.com", role=UserRole.STUDENT
    )

    classroom = await create_resource(
        client,
        path="/api/v1/classrooms",
        payload={"name": f"Attendance Room {suffix}", "code": f"att-room-{suffix}"},
        user=admin,
    )
    subject = await create_resource(
        client,
        path="/api/v1/subjects",
        payload={"name": f"Attendance Subject {suffix}", "code": f"att-subject-{suffix}"},
        user=admin,
    )
    teacher_profile = await create_resource(
        client,
        path="/api/v1/teacher-profiles",
        payload={"user_id": str(teacher.id), "employee_code": f"ATT-T1-{suffix}"},
        user=admin,
    )
    await create_resource(
        client,
        path="/api/v1/teacher-profiles",
        payload={"user_id": str(other_teacher.id), "employee_code": f"ATT-T2-{suffix}"},
        user=admin,
    )
    student_profile_1 = await create_resource(
        client,
        path="/api/v1/student-profiles",
        payload={
            "user_id": str(student_1.id),
            "classroom_id": classroom["id"],
            "roll_number": "01",
        },
        user=admin,
    )
    student_profile_2 = await create_resource(
        client,
        path="/api/v1/student-profiles",
        payload={
            "user_id": str(student_2.id),
            "classroom_id": classroom["id"],
            "roll_number": "02",
        },
        user=admin,
    )
    await create_resource(
        client,
        path="/api/v1/teacher-assignments",
        payload={
            "teacher_profile_id": teacher_profile["id"],
            "classroom_id": classroom["id"],
            "subject_id": subject["id"],
        },
        user=admin,
    )
    return {
        "admin": admin,
        "teacher": teacher,
        "other_teacher": other_teacher,
        "classroom": classroom,
        "subject": subject,
        "student_1": student_1,
        "student_2": student_2,
        "student_profile_1": student_profile_1,
        "student_profile_2": student_profile_2,
    }


async def mark_attendance(
    client: AsyncClient,
    *,
    user: User,
    classroom_id: str,
    subject_id: str,
    attendance_date: str,
    records: list[dict[str, Any]],
    request_id: str | None = None,
) -> Any:
    response = await client.post(
        "/api/v1/attendance/bulk",
        json={
            "classroom_id": classroom_id,
            "subject_id": subject_id,
            "attendance_date": attendance_date,
            "records": records,
        },
        headers=auth_headers(user, request_id=request_id),
    )
    assert response.status_code == 200, response.text
    return response.json()
