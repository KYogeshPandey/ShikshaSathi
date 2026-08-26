"""Admin HTTP integration coverage for Phase 3 Stage 2."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import UserRole
from app.tests.phase3_http_helpers import auth_headers, create_resource, seed_user


async def test_admin_user_directory_is_role_filtered_and_never_exposes_credentials(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await seed_user(db_session, email="directory-admin@example.com", role=UserRole.ADMIN)
    teacher = await seed_user(
        db_session, email="directory-teacher@example.com", role=UserRole.TEACHER
    )
    await seed_user(db_session, email="directory-student@example.com", role=UserRole.STUDENT)

    response = await client_db.get(
        "/api/v1/users?role=teacher&include_inactive=true",
        headers=auth_headers(admin),
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    item = response.json()["items"][0]
    assert item["id"] == str(teacher.id)
    assert item["full_name"] == "Teacher HTTP Test"
    assert item["email"] == "directory-teacher@example.com"
    assert "password" not in item
    assert "password_hash" not in item
    denied = await client_db.get(
        "/api/v1/users?role=student",
        headers=auth_headers(teacher),
    )
    assert denied.status_code == 403


async def test_authentication_role_denial_and_request_id_envelope(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    unauthenticated = await client_db.get(
        "/api/v1/classrooms", headers={"X-Request-ID": "phase3-auth-check"}
    )
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["request_id"] == "phase3-auth-check"
    assert unauthenticated.headers["X-Request-ID"] == "phase3-auth-check"

    teacher = await seed_user(db_session, email="denied-teacher@example.com", role=UserRole.TEACHER)
    denied = await client_db.post(
        "/api/v1/classrooms",
        json={"name": "Denied", "code": "denied"},
        headers=auth_headers(teacher),
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "HTTP_403"

    inactive = await seed_user(
        db_session,
        email="inactive-stage3@example.com",
        role=UserRole.ADMIN,
        is_active=False,
    )
    rejected = await client_db.get("/api/v1/classrooms", headers=auth_headers(inactive))
    assert rejected.status_code == 401


async def test_admin_classroom_and_subject_crud_conflicts_and_pagination(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await seed_user(db_session, email="admin-crud@example.com", role=UserRole.ADMIN)

    classrooms = []
    for index in range(3):
        classrooms.append(
            await create_resource(
                client_db,
                path="/api/v1/classrooms",
                payload={"name": f"Grade {index}", "code": f"grade {index}"},
                user=admin,
            )
        )

    duplicate = await client_db.post(
        "/api/v1/classrooms",
        json={"name": "Duplicate", "code": "GRADE 0"},
        headers=auth_headers(admin),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "CLASSROOM_CODE_ALREADY_EXISTS"

    page = await client_db.get("/api/v1/classrooms?limit=2&offset=1", headers=auth_headers(admin))
    assert page.status_code == 200
    assert page.json()["total"] == 3
    assert len(page.json()["items"]) == 2

    classroom_id = classrooms[0]["id"]
    updated = await client_db.patch(
        f"/api/v1/classrooms/{classroom_id}",
        json={"name": "Updated Grade"},
        headers=auth_headers(admin),
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated Grade"
    assert (
        await client_db.get(f"/api/v1/classrooms/{classroom_id}", headers=auth_headers(admin))
    ).status_code == 200

    deactivated = await client_db.delete(
        f"/api/v1/classrooms/{classroom_id}", headers=auth_headers(admin)
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False
    assert (await client_db.get("/api/v1/classrooms", headers=auth_headers(admin))).json()[
        "total"
    ] == 2
    assert (
        await client_db.get("/api/v1/classrooms?include_inactive=true", headers=auth_headers(admin))
    ).json()["total"] == 3

    subject = await create_resource(
        client_db,
        path="/api/v1/subjects",
        payload={"name": "Mathematics", "code": "MATH", "is_elective": False},
        user=admin,
    )
    conflict = await client_db.post(
        "/api/v1/subjects",
        json={"name": "Other Math", "code": "math"},
        headers=auth_headers(admin),
    )
    assert conflict.status_code == 409
    patched = await client_db.patch(
        f"/api/v1/subjects/{subject['id']}",
        json={"is_elective": True},
        headers=auth_headers(admin),
    )
    assert patched.status_code == 200
    assert patched.json()["is_elective"] is True
    assert (
        await client_db.delete(f"/api/v1/subjects/{subject['id']}", headers=auth_headers(admin))
    ).status_code == 200


async def test_admin_profiles_membership_and_assignment_operations(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await seed_user(db_session, email="admin-profiles@example.com", role=UserRole.ADMIN)
    teacher = await seed_user(
        db_session, email="managed-teacher@example.com", role=UserRole.TEACHER
    )
    student = await seed_user(
        db_session, email="managed-student@example.com", role=UserRole.STUDENT
    )
    classroom = await create_resource(
        client_db,
        path="/api/v1/classrooms",
        payload={"name": "Managed Classroom", "code": "managed-class"},
        user=admin,
    )
    subject = await create_resource(
        client_db,
        path="/api/v1/subjects",
        payload={"name": "Science", "code": "science"},
        user=admin,
    )
    teacher_profile = await create_resource(
        client_db,
        path="/api/v1/teacher-profiles",
        payload={"user_id": str(teacher.id), "employee_code": "EMP-HTTP-1"},
        user=admin,
    )
    student_profile = await create_resource(
        client_db,
        path="/api/v1/student-profiles",
        payload={"user_id": str(student.id)},
        user=admin,
    )
    teacher_updated = await client_db.patch(
        f"/api/v1/teacher-profiles/{teacher_profile['id']}",
        json={"phone_number": "+91-555-0100"},
        headers=auth_headers(admin),
    )
    assert teacher_updated.status_code == 200
    assert teacher_updated.json()["phone_number"] == "+91-555-0100"

    duplicate_profile = await client_db.post(
        "/api/v1/teacher-profiles",
        json={"user_id": str(teacher.id)},
        headers=auth_headers(admin),
    )
    assert duplicate_profile.status_code == 409
    second_teacher = await seed_user(
        db_session, email="second-managed-teacher@example.com", role=UserRole.TEACHER
    )
    employee_code_conflict = await client_db.post(
        "/api/v1/teacher-profiles",
        json={"user_id": str(second_teacher.id), "employee_code": "EMP-HTTP-1"},
        headers=auth_headers(admin),
    )
    assert employee_code_conflict.status_code == 409
    assert employee_code_conflict.json()["error"]["code"] == "TEACHER_EMPLOYEE_CODE_ALREADY_EXISTS"
    missing_user = await client_db.post(
        "/api/v1/student-profiles",
        json={"user_id": str(uuid.uuid4())},
        headers=auth_headers(admin),
    )
    assert missing_user.status_code == 404

    missing_classroom = await client_db.put(
        f"/api/v1/student-profiles/{student_profile['id']}/classroom-membership",
        json={"classroom_id": str(uuid.uuid4()), "roll_number": "01"},
        headers=auth_headers(admin),
    )
    assert missing_classroom.status_code == 422
    assigned = await client_db.put(
        f"/api/v1/student-profiles/{student_profile['id']}/classroom-membership",
        json={"classroom_id": classroom["id"], "roll_number": "01"},
        headers=auth_headers(admin),
    )
    assert assigned.status_code == 200
    assert assigned.json()["classroom_id"] == classroom["id"]
    empty_membership = await client_db.put(
        f"/api/v1/student-profiles/{student_profile['id']}/classroom-membership",
        json={},
        headers=auth_headers(admin),
    )
    assert empty_membership.status_code == 422

    assignment = await create_resource(
        client_db,
        path="/api/v1/teacher-assignments",
        payload={
            "teacher_profile_id": teacher_profile["id"],
            "classroom_id": classroom["id"],
            "subject_id": subject["id"],
        },
        user=admin,
    )
    assert (
        await client_db.get(
            f"/api/v1/teacher-assignments/{assignment['id']}",
            headers=auth_headers(admin),
        )
    ).status_code == 200
    duplicate_assignment = await client_db.post(
        "/api/v1/teacher-assignments",
        json={
            "teacher_profile_id": teacher_profile["id"],
            "classroom_id": classroom["id"],
            "subject_id": subject["id"],
        },
        headers=auth_headers(admin),
    )
    assert duplicate_assignment.status_code == 409
    invalid_assignment = await client_db.post(
        "/api/v1/teacher-assignments",
        json={
            "teacher_profile_id": teacher_profile["id"],
            "classroom_id": classroom["id"],
            "subject_id": str(uuid.uuid4()),
        },
        headers=auth_headers(admin),
    )
    assert invalid_assignment.status_code == 422
    assert (
        await client_db.delete(
            f"/api/v1/teacher-assignments/{assignment['id']}",
            headers=auth_headers(admin),
        )
    ).status_code == 200
    assert (
        await client_db.delete(
            f"/api/v1/student-profiles/{student_profile['id']}",
            headers=auth_headers(admin),
        )
    ).json()["is_active"] is False


async def test_admin_classroom_filters_apply_before_pagination(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await seed_user(db_session, email="filtered-admin@example.com", role=UserRole.ADMIN)
    teacher = await seed_user(
        db_session, email="filtered-teacher@example.com", role=UserRole.TEACHER
    )
    classroom_a = await create_resource(
        client_db,
        path="/api/v1/classrooms",
        payload={"name": "Filtered Class A", "code": "filtered-class-a"},
        user=admin,
    )
    classroom_b = await create_resource(
        client_db,
        path="/api/v1/classrooms",
        payload={"name": "Filtered Class B", "code": "filtered-class-b"},
        user=admin,
    )
    subject = await create_resource(
        client_db,
        path="/api/v1/subjects",
        payload={"name": "Filtered Subject", "code": "filtered-subject"},
        user=admin,
    )
    teacher_profile = await create_resource(
        client_db,
        path="/api/v1/teacher-profiles",
        payload={"user_id": str(teacher.id)},
        user=admin,
    )

    for index, (classroom, roll) in enumerate(
        ((classroom_a, "101"), (classroom_b, "201"), (classroom_a, "102"))
    ):
        student = await seed_user(
            db_session,
            email=f"filtered-student-{index}@example.com",
            role=UserRole.STUDENT,
        )
        student.full_name = f"Filtered Student {index}"
        await db_session.commit()
        await create_resource(
            client_db,
            path="/api/v1/student-profiles",
            payload={
                "user_id": str(student.id),
                "classroom_id": classroom["id"],
                "roll_number": roll,
            },
            user=admin,
        )

    roster = await client_db.get(
        "/api/v1/student-profiles",
        params={"classroom_id": classroom_a["id"], "limit": 1, "offset": 1},
        headers=auth_headers(admin),
    )
    assert roster.status_code == 200, roster.text
    assert roster.json()["total"] == 2
    assert len(roster.json()["items"]) == 1
    assert roster.json()["items"][0]["classroom_id"] == classroom_a["id"]
    assert roster.json()["items"][0]["full_name"].startswith("Filtered Student")

    assignments = []
    for index, classroom in enumerate((classroom_a, classroom_b)):
        assignment = await create_resource(
            client_db,
            path="/api/v1/teacher-assignments",
            payload={
                "teacher_profile_id": teacher_profile["id"],
                "classroom_id": classroom["id"],
                "subject_id": subject["id"],
            },
            user=admin,
        )
        assignments.append(assignment)
        await create_resource(
            client_db,
            path="/api/v1/timetable-entries",
            payload={
                "teacher_profile_id": teacher_profile["id"],
                "classroom_id": classroom["id"],
                "subject_id": subject["id"],
                "day_of_week": "monday" if index == 0 else "tuesday",
                "start_time": "09:00:00",
                "end_time": "10:00:00",
            },
            user=admin,
        )

    assignment_page = await client_db.get(
        "/api/v1/teacher-assignments",
        params={"classroom_id": classroom_b["id"], "limit": 1},
        headers=auth_headers(admin),
    )
    assert assignment_page.json()["total"] == 1
    assert assignment_page.json()["items"][0]["id"] == assignments[1]["id"]
    assert assignment_page.json()["items"][0]["classroom_id"] == classroom_b["id"]

    timetable_page = await client_db.get(
        "/api/v1/timetable-entries",
        params={"classroom_id": classroom_a["id"], "limit": 1},
        headers=auth_headers(admin),
    )
    assert timetable_page.json()["total"] == 1
    assert timetable_page.json()["items"][0]["classroom_id"] == classroom_a["id"]
