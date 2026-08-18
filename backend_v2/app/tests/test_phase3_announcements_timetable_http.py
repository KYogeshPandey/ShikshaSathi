"""Announcement visibility and timetable HTTP integration coverage."""

from __future__ import annotations

import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import UserRole
from app.tests.phase3_http_helpers import auth_headers, create_resource, seed_user


def _ids(body: dict[str, Any]) -> set[str]:
    return {str(item["id"]) for item in body["items"]}


async def test_timetable_requires_assignment_preserves_collisions_and_supports_updates(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await seed_user(db_session, email="timetable-admin@example.com", role=UserRole.ADMIN)
    teacher = await seed_user(
        db_session, email="timetable-teacher@example.com", role=UserRole.TEACHER
    )
    classroom = await create_resource(
        client_db,
        path="/api/v1/classrooms",
        payload={"name": "Timetable Class", "code": "tt-http"},
        user=admin,
    )
    subject = await create_resource(
        client_db,
        path="/api/v1/subjects",
        payload={"name": "Timetable Subject", "code": "tt-subject-http"},
        user=admin,
    )
    unrelated_subject = await create_resource(
        client_db,
        path="/api/v1/subjects",
        payload={"name": "Unassigned Subject", "code": "unassigned-http"},
        user=admin,
    )
    profile = await create_resource(
        client_db,
        path="/api/v1/teacher-profiles",
        payload={"user_id": str(teacher.id)},
        user=admin,
    )
    await create_resource(
        client_db,
        path="/api/v1/teacher-assignments",
        payload={
            "teacher_profile_id": profile["id"],
            "classroom_id": classroom["id"],
            "subject_id": subject["id"],
        },
        user=admin,
    )
    payload = {
        "teacher_profile_id": profile["id"],
        "classroom_id": classroom["id"],
        "subject_id": subject["id"],
        "day_of_week": "tuesday",
        "start_time": "09:00:00",
        "end_time": "10:00:00",
    }
    entry = await create_resource(
        client_db,
        path="/api/v1/timetable-entries",
        payload=payload,
        user=admin,
    )
    assert (
        await client_db.get(
            f"/api/v1/timetable-entries/{entry['id']}",
            headers=auth_headers(admin),
        )
    ).status_code == 200

    collision = await client_db.post(
        "/api/v1/timetable-entries", json=payload, headers=auth_headers(admin)
    )
    assert collision.status_code == 409
    assert collision.json()["error"]["code"] == "TIMETABLE_SLOT_COLLISION"

    no_assignment_payload = dict(payload)
    no_assignment_payload["subject_id"] = unrelated_subject["id"]
    no_assignment_payload["start_time"] = "11:00:00"
    no_assignment_payload["end_time"] = "12:00:00"
    no_assignment = await client_db.post(
        "/api/v1/timetable-entries",
        json=no_assignment_payload,
        headers=auth_headers(admin),
    )
    assert no_assignment.status_code == 409
    assert no_assignment.json()["error"]["code"] == "TIMETABLE_ASSIGNMENT_REQUIRED"

    invalid = dict(payload)
    invalid["start_time"] = "13:00:00"
    invalid["end_time"] = "12:00:00"
    invalid_response = await client_db.post(
        "/api/v1/timetable-entries", json=invalid, headers=auth_headers(admin)
    )
    assert invalid_response.status_code == 422
    assert invalid_response.json()["error"]["code"] == "VALIDATION_ERROR"

    updated = await client_db.patch(
        f"/api/v1/timetable-entries/{entry['id']}",
        json={"end_time": "10:30:00"},
        headers=auth_headers(admin),
    )
    assert updated.status_code == 200
    assert updated.json()["end_time"] == "10:30:00"
    deactivated = await client_db.delete(
        f"/api/v1/timetable-entries/{entry['id']}", headers=auth_headers(admin)
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False


async def test_announcement_global_role_classroom_and_inactive_visibility(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await seed_user(db_session, email="announcement-admin@example.com", role=UserRole.ADMIN)
    teacher = await seed_user(
        db_session, email="announcement-teacher@example.com", role=UserRole.TEACHER
    )
    student = await seed_user(
        db_session, email="announcement-student@example.com", role=UserRole.STUDENT
    )
    classroom = await create_resource(
        client_db,
        path="/api/v1/classrooms",
        payload={"name": "Audience Class", "code": "audience-class"},
        user=admin,
    )
    unrelated_classroom = await create_resource(
        client_db,
        path="/api/v1/classrooms",
        payload={"name": "Other Audience", "code": "other-audience"},
        user=admin,
    )
    subject = await create_resource(
        client_db,
        path="/api/v1/subjects",
        payload={"name": "Audience Subject", "code": "audience-subject"},
        user=admin,
    )
    teacher_profile = await create_resource(
        client_db,
        path="/api/v1/teacher-profiles",
        payload={"user_id": str(teacher.id)},
        user=admin,
    )
    await create_resource(
        client_db,
        path="/api/v1/student-profiles",
        payload={
            "user_id": str(student.id),
            "classroom_id": classroom["id"],
            "roll_number": "10",
        },
        user=admin,
    )
    await create_resource(
        client_db,
        path="/api/v1/teacher-assignments",
        payload={
            "teacher_profile_id": teacher_profile["id"],
            "classroom_id": classroom["id"],
            "subject_id": subject["id"],
        },
        user=admin,
    )

    announcements: dict[str, dict[str, object]] = {}
    for audience, classroom_ids in (
        ("all", []),
        ("teacher", []),
        ("student", []),
        ("classroom", [classroom["id"]]),
        ("classroom", [unrelated_classroom["id"]]),
    ):
        key = (
            audience
            if audience != "classroom"
            else ("classroom-own" if classroom_ids[0] == classroom["id"] else "classroom-other")
        )
        announcements[key] = await create_resource(
            client_db,
            path="/api/v1/announcements",
            payload={
                "title": key,
                "content": f"Visible to {key}",
                "audience": audience,
                "classroom_ids": classroom_ids,
            },
            user=admin,
        )
        assert announcements[key]["author_user_id"] == str(admin.id)

    spoofed_author = await client_db.post(
        "/api/v1/announcements",
        json={
            "title": "Spoofed author",
            "content": "Must be rejected.",
            "audience": "all",
            "author_user_id": str(uuid.uuid4()),
        },
        headers=auth_headers(admin),
    )
    assert spoofed_author.status_code == 422

    invalid_reference = await client_db.post(
        "/api/v1/announcements",
        json={
            "title": "Invalid",
            "content": "Missing classroom",
            "audience": "classroom",
            "classroom_ids": [str(uuid.uuid4())],
        },
        headers=auth_headers(admin),
    )
    assert invalid_reference.status_code == 422

    teacher_page = (
        await client_db.get("/api/v1/announcements", headers=auth_headers(teacher))
    ).json()
    assert _ids(teacher_page) == {
        announcements["all"]["id"],
        announcements["teacher"]["id"],
        announcements["classroom-own"]["id"],
    }
    student_page = (
        await client_db.get("/api/v1/announcements", headers=auth_headers(student))
    ).json()
    assert _ids(student_page) == {
        announcements["all"]["id"],
        announcements["student"]["id"],
        announcements["classroom-own"]["id"],
    }

    unrelated = await client_db.get(
        f"/api/v1/announcements/{announcements['classroom-other']['id']}",
        headers=auth_headers(student),
    )
    assert unrelated.status_code == 404

    announcement_updated = await client_db.patch(
        f"/api/v1/announcements/{announcements['teacher']['id']}",
        json={"title": "Updated teacher notice"},
        headers=auth_headers(admin),
    )
    assert announcement_updated.status_code == 200
    assert announcement_updated.json()["title"] == "Updated teacher notice"

    deactivated = await client_db.delete(
        f"/api/v1/announcements/{announcements['all']['id']}",
        headers=auth_headers(admin),
    )
    assert deactivated.status_code == 200
    teacher_after = (
        await client_db.get("/api/v1/announcements", headers=auth_headers(teacher))
    ).json()
    assert announcements["all"]["id"] not in _ids(teacher_after)
    admin_with_inactive = await client_db.get(
        "/api/v1/announcements?include_inactive=true",
        headers=auth_headers(admin),
    )
    assert announcements["all"]["id"] in _ids(admin_with_inactive.json())
