"""Phase 4 Stage 3 HTTP coverage: bulk-save, detail, and daily endpoints.

Uses the real router → read/service → repository → Postgres path via
``client_db``/``db_session`` (see ``app/tests/conftest.py``). Does not
duplicate Stage 2's 24 service-level tests
(``test_attendance_service.py``) — only the HTTP-layer concerns Stage 3
adds: role/auth wiring, request-ID propagation, query-parameter
filtering, pagination, and the concealed-teacher-scope behavior as seen
through the router.
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
from app.tests.phase3_http_helpers import auth_headers, seed_user

TODAY = date.today().isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


# --- bulk-save ------------------------------------------------------------


async def test_bulk_unauthenticated_returns_401(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="bulk-401")
    response = await client_db.post(
        "/api/v1/attendance/bulk",
        json={
            "classroom_id": scope["classroom"]["id"],
            "subject_id": scope["subject"]["id"],
            "attendance_date": TODAY,
            "records": [
                {"student_profile_id": scope["student_profile_1"]["id"], "status": "present"}
            ],
        },
    )
    assert response.status_code == 401


async def test_bulk_inactive_user_returns_401(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="bulk-inactive")
    inactive_admin = await seed_user(
        db_session, email="bulk-inactive-admin@example.com", role=UserRole.ADMIN, is_active=False
    )
    response = await client_db.post(
        "/api/v1/attendance/bulk",
        json={
            "classroom_id": scope["classroom"]["id"],
            "subject_id": scope["subject"]["id"],
            "attendance_date": TODAY,
            "records": [
                {"student_profile_id": scope["student_profile_1"]["id"], "status": "present"}
            ],
        },
        headers=auth_headers(inactive_admin),
    )
    assert response.status_code == 401


async def test_bulk_student_role_returns_403(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="bulk-student")
    response = await client_db.post(
        "/api/v1/attendance/bulk",
        json={
            "classroom_id": scope["classroom"]["id"],
            "subject_id": scope["subject"]["id"],
            "attendance_date": TODAY,
            "records": [
                {"student_profile_id": scope["student_profile_1"]["id"], "status": "present"}
            ],
        },
        headers=auth_headers(scope["student_1"]),
    )
    assert response.status_code == 403


async def test_bulk_admin_succeeds(client_db: AsyncClient, db_session: AsyncSession) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="bulk-admin")
    result = await mark_attendance(
        client_db,
        user=scope["admin"],
        classroom_id=scope["classroom"]["id"],
        subject_id=scope["subject"]["id"],
        attendance_date=TODAY,
        records=[{"student_profile_id": scope["student_profile_1"]["id"], "status": "present"}],
    )
    assert result["created_count"] == 1
    assert result["updated_count"] == 0


async def test_bulk_assigned_teacher_succeeds(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="bulk-teacher")
    result = await mark_attendance(
        client_db,
        user=scope["teacher"],
        classroom_id=scope["classroom"]["id"],
        subject_id=scope["subject"]["id"],
        attendance_date=TODAY,
        records=[{"student_profile_id": scope["student_profile_1"]["id"], "status": "absent"}],
    )
    assert result["created_count"] == 1


async def test_bulk_unrelated_teacher_denied_and_creates_blocked_audit(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="bulk-unrelated")
    other_teacher_id = scope["other_teacher"].id
    response = await client_db.post(
        "/api/v1/attendance/bulk",
        json={
            "classroom_id": scope["classroom"]["id"],
            "subject_id": scope["subject"]["id"],
            "attendance_date": TODAY,
            "records": [
                {"student_profile_id": scope["student_profile_1"]["id"], "status": "present"}
            ],
        },
        headers=auth_headers(scope["other_teacher"]),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ATTENDANCE_SCOPE_NOT_FOUND"

    rows = (
        (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.actor_user_id == other_teacher_id,
                    AuditLog.outcome == AuditOutcome.BLOCKED,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].action == "attendance.bulk_mark"


async def test_bulk_request_id_reaches_success_audit(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="bulk-reqid")
    response = await client_db.post(
        "/api/v1/attendance/bulk",
        json={
            "classroom_id": scope["classroom"]["id"],
            "subject_id": scope["subject"]["id"],
            "attendance_date": TODAY,
            "records": [
                {"student_profile_id": scope["student_profile_1"]["id"], "status": "present"}
            ],
        },
        headers=auth_headers(scope["admin"], request_id="test-request-id-bulk-1"),
    )
    assert response.status_code == 200
    row = (
        (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.actor_user_id == scope["admin"].id,
                    AuditLog.outcome == AuditOutcome.SUCCESS,
                )
            )
        )
        .scalars()
        .one()
    )
    assert row.request_id == "test-request-id-bulk-1"


async def test_bulk_rejects_client_supplied_actor_and_marked_by_fields(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="bulk-spoof")
    for field_name in ("marked_by_user_id", "actor_user_id"):
        response = await client_db.post(
            "/api/v1/attendance/bulk",
            json={
                "classroom_id": scope["classroom"]["id"],
                "subject_id": scope["subject"]["id"],
                "attendance_date": TODAY,
                field_name: scope["other_teacher"].id.hex,
                "records": [
                    {"student_profile_id": scope["student_profile_1"]["id"], "status": "present"}
                ],
            },
            headers=auth_headers(scope["admin"]),
        )
        # BulkAttendanceRequest uses extra="forbid" — neither field exists
        # on the schema, so supplying either is a validation error, not a
        # silently-ignored extra field.
        assert response.status_code == 422, f"{field_name} should be rejected"


# --- detail -----------------------------------------------------------------


async def _mark_two_students(client_db: AsyncClient, scope: dict[str, Any], *, when: str) -> None:
    await mark_attendance(
        client_db,
        user=scope["admin"],
        classroom_id=scope["classroom"]["id"],
        subject_id=scope["subject"]["id"],
        attendance_date=when,
        records=[
            {
                "student_profile_id": scope["student_profile_1"]["id"],
                "status": "present",
            },
            {
                "student_profile_id": scope["student_profile_2"]["id"],
                "status": "absent",
            },
        ],
    )


async def test_detail_admin_and_teacher_succeed(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="detail-ok")
    await _mark_two_students(client_db, scope, when=TODAY)

    for user in (scope["admin"], scope["teacher"]):
        response = await client_db.get(
            "/api/v1/attendance/detail",
            params={"classroom_id": scope["classroom"]["id"], "subject_id": scope["subject"]["id"]},
            headers=auth_headers(user),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2


async def test_detail_unrelated_teacher_denied_and_audited(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="detail-unrelated")
    await _mark_two_students(client_db, scope, when=TODAY)

    response = await client_db.get(
        "/api/v1/attendance/detail",
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
                    AuditLog.action == "attendance.read_detail",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1


async def test_detail_deterministic_pagination(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="detail-page")
    await _mark_two_students(client_db, scope, when=TODAY)

    first_page = await client_db.get(
        "/api/v1/attendance/detail",
        params={
            "classroom_id": scope["classroom"]["id"],
            "subject_id": scope["subject"]["id"],
            "limit": 1,
            "offset": 0,
        },
        headers=auth_headers(scope["admin"]),
    )
    second_page = await client_db.get(
        "/api/v1/attendance/detail",
        params={
            "classroom_id": scope["classroom"]["id"],
            "subject_id": scope["subject"]["id"],
            "limit": 1,
            "offset": 1,
        },
        headers=auth_headers(scope["admin"]),
    )
    assert first_page.status_code == second_page.status_code == 200
    first_id = first_page.json()["items"][0]["id"]
    second_id = second_page.json()["items"][0]["id"]
    assert first_id != second_id


async def test_detail_classroom_and_subject_filtering(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    """Two distinct (classroom, subject) scopes for the same teacher.

    Confirms ``classroom_id``/``subject_id`` genuinely restrict results —
    marking attendance in scope B must never appear when querying scope A.
    """
    scope = await seed_attendance_scope(client_db, db_session, suffix="detail-filter-a")
    await _mark_two_students(client_db, scope, when=TODAY)

    other_scope = await seed_attendance_scope(client_db, db_session, suffix="detail-filter-b")
    await _mark_two_students(client_db, other_scope, when=TODAY)

    response = await client_db.get(
        "/api/v1/attendance/detail",
        params={"classroom_id": scope["classroom"]["id"], "subject_id": scope["subject"]["id"]},
        headers=auth_headers(scope["admin"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    returned_students = {item["student_profile_id"] for item in body["items"]}
    assert returned_students == {
        scope["student_profile_1"]["id"],
        scope["student_profile_2"]["id"],
    }


async def test_detail_student_filtering(client_db: AsyncClient, db_session: AsyncSession) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="detail-student-filter")
    await _mark_two_students(client_db, scope, when=TODAY)

    response = await client_db.get(
        "/api/v1/attendance/detail",
        params={
            "classroom_id": scope["classroom"]["id"],
            "subject_id": scope["subject"]["id"],
            "student_profile_id": scope["student_profile_1"]["id"],
        },
        headers=auth_headers(scope["admin"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["student_profile_id"] == scope["student_profile_1"]["id"]


async def test_detail_status_filtering(client_db: AsyncClient, db_session: AsyncSession) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="detail-status-filter")
    await _mark_two_students(client_db, scope, when=TODAY)

    response = await client_db.get(
        "/api/v1/attendance/detail",
        params={
            "classroom_id": scope["classroom"]["id"],
            "subject_id": scope["subject"]["id"],
            "status": "absent",
        },
        headers=auth_headers(scope["admin"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "absent"


async def test_detail_date_filtering(client_db: AsyncClient, db_session: AsyncSession) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="detail-date-filter")
    await _mark_two_students(client_db, scope, when=YESTERDAY)
    await mark_attendance(
        client_db,
        user=scope["admin"],
        classroom_id=scope["classroom"]["id"],
        subject_id=scope["subject"]["id"],
        attendance_date=TODAY,
        records=[{"student_profile_id": scope["student_profile_1"]["id"], "status": "present"}],
    )

    response = await client_db.get(
        "/api/v1/attendance/detail",
        params={
            "classroom_id": scope["classroom"]["id"],
            "subject_id": scope["subject"]["id"],
            "date_from": TODAY,
            "date_to": TODAY,
        },
        headers=auth_headers(scope["admin"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["attendance_date"] == TODAY


async def test_detail_invalid_date_range_returns_422(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="detail-bad-range")
    response = await client_db.get(
        "/api/v1/attendance/detail",
        params={
            "classroom_id": scope["classroom"]["id"],
            "subject_id": scope["subject"]["id"],
            "date_from": TODAY,
            "date_to": YESTERDAY,
        },
        headers=auth_headers(scope["admin"]),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ATTENDANCE_INVALID_DATE_RANGE"


# --- daily --------------------------------------------------------------


async def test_daily_exact_scope_and_empty_result(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="daily-exact")
    await _mark_two_students(client_db, scope, when=TODAY)

    response = await client_db.get(
        "/api/v1/attendance/daily",
        params={
            "classroom_id": scope["classroom"]["id"],
            "subject_id": scope["subject"]["id"],
            "attendance_date": TODAY,
        },
        headers=auth_headers(scope["teacher"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["attendance_date"] == TODAY
    assert len(body["records"]) == 2

    empty_response = await client_db.get(
        "/api/v1/attendance/daily",
        params={
            "classroom_id": scope["classroom"]["id"],
            "subject_id": scope["subject"]["id"],
            "attendance_date": YESTERDAY,
        },
        headers=auth_headers(scope["teacher"]),
    )
    assert empty_response.status_code == 200
    assert empty_response.json()["records"] == []


# --- student self-service ---------------------------------------------------


async def test_student_self_detail_and_stats_succeed(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="self-ok")
    await _mark_two_students(client_db, scope, when=TODAY)

    detail = await client_db.get(
        "/api/v1/attendance/me/detail", headers=auth_headers(scope["student_1"])
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["total"] == 1
    assert body["items"][0]["student_profile_id"] == scope["student_profile_1"]["id"]

    stats = await client_db.get(
        "/api/v1/attendance/me/stats", headers=auth_headers(scope["student_1"])
    )
    assert stats.status_code == 200
    stats_body = stats.json()
    assert stats_body["student_profile_id"] == scope["student_profile_1"]["id"]
    assert stats_body["total_count"] == 1
    assert stats_body["present_count"] == 1


async def test_student_self_detail_ignores_unsupported_student_profile_id_param(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    """No ``student_profile_id`` query parameter exists on ``/attendance/me/detail``.

    Supplying one (as if trying to look up another student) has no
    effect — the route only ever reads the caller's own identity-derived
    profile — so student 1 still only ever sees their own single record.
    """
    scope = await seed_attendance_scope(client_db, db_session, suffix="self-no-spoof")
    await _mark_two_students(client_db, scope, when=TODAY)

    response = await client_db.get(
        "/api/v1/attendance/me/detail",
        params={"student_profile_id": scope["student_profile_2"]["id"]},
        headers=auth_headers(scope["student_1"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["student_profile_id"] == scope["student_profile_1"]["id"]


async def test_student_cannot_see_another_students_records(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="self-isolated")
    await _mark_two_students(client_db, scope, when=TODAY)

    response = await client_db.get(
        "/api/v1/attendance/me/detail", headers=auth_headers(scope["student_2"])
    )
    assert response.status_code == 200
    body = response.json()
    assert all(
        item["student_profile_id"] == scope["student_profile_2"]["id"] for item in body["items"]
    )


async def test_student_self_detail_inactive_profile_returns_404(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="self-inactive")
    await client_db.patch(
        f"/api/v1/student-profiles/{scope['student_profile_1']['id']}",
        json={"is_active": False},
        headers=auth_headers(scope["admin"]),
    )
    response = await client_db.get(
        "/api/v1/attendance/me/detail", headers=auth_headers(scope["student_1"])
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "STUDENT_PROFILE_NOT_FOUND"


async def test_student_self_detail_missing_profile_returns_404(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    profile_less_student = await seed_user(
        db_session, email="self-no-profile@example.com", role=UserRole.STUDENT
    )
    response = await client_db.get(
        "/api/v1/attendance/me/detail", headers=auth_headers(profile_less_student)
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "STUDENT_PROFILE_NOT_FOUND"


async def test_student_only_route_denies_teacher_and_admin(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="self-role-denied")
    for user in (scope["teacher"], scope["admin"]):
        response = await client_db.get("/api/v1/attendance/me/detail", headers=auth_headers(user))
        assert response.status_code == 403
