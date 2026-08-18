"""Teacher/student object-level authorization HTTP coverage."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User, UserRole
from app.tests.phase3_http_helpers import auth_headers, create_resource, seed_user


async def _seed_two_scopes(client: AsyncClient, session: AsyncSession) -> dict[str, Any]:
    admin = await seed_user(session, email="scope-admin@example.com", role=UserRole.ADMIN)
    teacher_a = await seed_user(session, email="scope-teacher-a@example.com", role=UserRole.TEACHER)
    teacher_b = await seed_user(session, email="scope-teacher-b@example.com", role=UserRole.TEACHER)
    student_a = await seed_user(session, email="scope-student-a@example.com", role=UserRole.STUDENT)
    student_b = await seed_user(session, email="scope-student-b@example.com", role=UserRole.STUDENT)

    classroom_a = await create_resource(
        client,
        path="/api/v1/classrooms",
        payload={"name": "Scope A", "code": "scope-a"},
        user=admin,
    )
    classroom_b = await create_resource(
        client,
        path="/api/v1/classrooms",
        payload={"name": "Scope B", "code": "scope-b"},
        user=admin,
    )
    subject_a = await create_resource(
        client,
        path="/api/v1/subjects",
        payload={"name": "Subject A", "code": "subject-a"},
        user=admin,
    )
    subject_b = await create_resource(
        client,
        path="/api/v1/subjects",
        payload={"name": "Subject B", "code": "subject-b"},
        user=admin,
    )
    teacher_profile_a = await create_resource(
        client,
        path="/api/v1/teacher-profiles",
        payload={"user_id": str(teacher_a.id), "employee_code": "SCOPE-TA"},
        user=admin,
    )
    teacher_profile_b = await create_resource(
        client,
        path="/api/v1/teacher-profiles",
        payload={"user_id": str(teacher_b.id), "employee_code": "SCOPE-TB"},
        user=admin,
    )
    student_profile_a = await create_resource(
        client,
        path="/api/v1/student-profiles",
        payload={
            "user_id": str(student_a.id),
            "classroom_id": classroom_a["id"],
            "roll_number": "01",
        },
        user=admin,
    )
    student_profile_b = await create_resource(
        client,
        path="/api/v1/student-profiles",
        payload={
            "user_id": str(student_b.id),
            "classroom_id": classroom_b["id"],
            "roll_number": "01",
        },
        user=admin,
    )

    for teacher_profile, classroom, subject in (
        (teacher_profile_a, classroom_a, subject_a),
        (teacher_profile_b, classroom_b, subject_b),
    ):
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

    timetable_a = await create_resource(
        client,
        path="/api/v1/timetable-entries",
        payload={
            "teacher_profile_id": teacher_profile_a["id"],
            "classroom_id": classroom_a["id"],
            "subject_id": subject_a["id"],
            "day_of_week": "monday",
            "start_time": "09:00:00",
            "end_time": "10:00:00",
        },
        user=admin,
    )
    timetable_b = await create_resource(
        client,
        path="/api/v1/timetable-entries",
        payload={
            "teacher_profile_id": teacher_profile_b["id"],
            "classroom_id": classroom_b["id"],
            "subject_id": subject_b["id"],
            "day_of_week": "monday",
            "start_time": "10:00:00",
            "end_time": "11:00:00",
        },
        user=admin,
    )
    return {
        "admin": admin,
        "teacher_a": teacher_a,
        "student_a": student_a,
        "classroom_a": classroom_a,
        "classroom_b": classroom_b,
        "subject_a": subject_a,
        "subject_b": subject_b,
        "teacher_profile_a": teacher_profile_a,
        "teacher_profile_b": teacher_profile_b,
        "student_profile_a": student_profile_a,
        "student_profile_b": student_profile_b,
        "timetable_a": timetable_a,
        "timetable_b": timetable_b,
    }


def _item_ids(body: dict[str, Any]) -> set[str]:
    return {str(item["id"]) for item in body["items"]}


async def test_teacher_reads_only_own_profile_and_assigned_academics(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await _seed_two_scopes(client_db, db_session)
    teacher: User = scope["teacher_a"]
    headers = auth_headers(teacher)

    own = await client_db.get("/api/v1/teacher-profiles/me", headers=headers)
    assert own.status_code == 200
    assert own.json()["id"] == scope["teacher_profile_a"]["id"]
    other = await client_db.get(
        f"/api/v1/teacher-profiles/{scope['teacher_profile_b']['id']}",
        headers=headers,
    )
    assert other.status_code == 404
    assert (await client_db.get("/api/v1/teacher-profiles", headers=headers)).status_code == 403

    classrooms = await client_db.get("/api/v1/classrooms", headers=headers)
    assert _item_ids(classrooms.json()) == {scope["classroom_a"]["id"]}
    assert (
        await client_db.get(f"/api/v1/classrooms/{scope['classroom_b']['id']}", headers=headers)
    ).status_code == 404

    subjects = await client_db.get("/api/v1/subjects", headers=headers)
    assert _item_ids(subjects.json()) == {scope["subject_a"]["id"]}
    assert (
        await client_db.get(f"/api/v1/subjects/{scope['subject_b']['id']}", headers=headers)
    ).status_code == 404

    timetable = await client_db.get("/api/v1/timetable-entries", headers=headers)
    assert _item_ids(timetable.json()) == {scope["timetable_a"]["id"]}
    assert (
        await client_db.get(
            f"/api/v1/timetable-entries/{scope['timetable_a']['id']}",
            headers=headers,
        )
    ).status_code == 200
    assert (
        await client_db.get(
            f"/api/v1/timetable-entries/{scope['timetable_b']['id']}",
            headers=headers,
        )
    ).status_code == 404


async def test_student_reads_only_own_profile_classroom_subjects_and_timetable(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await _seed_two_scopes(client_db, db_session)
    student: User = scope["student_a"]
    headers = auth_headers(student)

    own = await client_db.get("/api/v1/student-profiles/me", headers=headers)
    assert own.status_code == 200
    assert own.json()["id"] == scope["student_profile_a"]["id"]
    other = await client_db.get(
        f"/api/v1/student-profiles/{scope['student_profile_b']['id']}",
        headers=headers,
    )
    assert other.status_code == 404

    classrooms = await client_db.get("/api/v1/classrooms", headers=headers)
    assert _item_ids(classrooms.json()) == {scope["classroom_a"]["id"]}
    assert (
        await client_db.get(f"/api/v1/classrooms/{scope['classroom_b']['id']}", headers=headers)
    ).status_code == 404

    subjects = await client_db.get("/api/v1/subjects", headers=headers)
    assert _item_ids(subjects.json()) == {scope["subject_a"]["id"]}
    assert (
        await client_db.get(f"/api/v1/subjects/{scope['subject_b']['id']}", headers=headers)
    ).status_code == 404

    timetable = await client_db.get("/api/v1/timetable-entries", headers=headers)
    assert _item_ids(timetable.json()) == {scope["timetable_a"]["id"]}
    assert (
        await client_db.get(
            f"/api/v1/timetable-entries/{scope['timetable_a']['id']}",
            headers=headers,
        )
    ).status_code == 200
    assert (
        await client_db.get(
            f"/api/v1/timetable-entries/{scope['timetable_b']['id']}",
            headers=headers,
        )
    ).status_code == 404


async def test_inactive_teacher_profile_hides_dependent_scoped_academics(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await _seed_two_scopes(client_db, db_session)
    admin: User = scope["admin"]
    teacher: User = scope["teacher_a"]
    student: User = scope["student_a"]

    deactivated = await client_db.delete(
        f"/api/v1/teacher-profiles/{scope['teacher_profile_a']['id']}",
        headers=auth_headers(admin),
    )
    assert deactivated.status_code == 200

    for user in (teacher, student):
        subjects = await client_db.get("/api/v1/subjects", headers=auth_headers(user))
        timetable = await client_db.get("/api/v1/timetable-entries", headers=auth_headers(user))
        assert subjects.json()["items"] == []
        assert timetable.json()["items"] == []
        assert (
            await client_db.get(
                f"/api/v1/subjects/{scope['subject_a']['id']}",
                headers=auth_headers(user),
            )
        ).status_code == 404
        assert (
            await client_db.get(
                f"/api/v1/timetable-entries/{scope['timetable_a']['id']}",
                headers=auth_headers(user),
            )
        ).status_code == 404
