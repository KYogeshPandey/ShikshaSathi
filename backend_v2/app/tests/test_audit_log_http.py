"""Phase 4 Stage 3 HTTP coverage: ``GET /api/v1/audit-logs`` (admin-only, read-only).

Covers role restriction (admin-only), filtering/pagination, that both a
successful bulk-save and a blocked scope-denial produce a visible audit
row, that no write route exists for this resource, and that responses
never leak secrets.
"""

from __future__ import annotations

from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.tests.attendance_http_helpers import mark_attendance, seed_attendance_scope
from app.tests.phase3_http_helpers import auth_headers

TODAY = date.today().isoformat()


async def test_admin_audit_log_list_and_detail_succeed(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="audit-list")
    await mark_attendance(
        client_db,
        user=scope["admin"],
        classroom_id=scope["classroom"]["id"],
        subject_id=scope["subject"]["id"],
        attendance_date=TODAY,
        records=[{"student_profile_id": scope["student_profile_1"]["id"], "status": "present"}],
    )
    list_response = await client_db.get(
        "/api/v1/audit-logs",
        params={"actor_user_id": str(scope["admin"].id)},
        headers=auth_headers(scope["admin"]),
    )
    assert list_response.status_code == 200
    body = list_response.json()
    assert body["total"] >= 1
    audit_log_id = body["items"][0]["id"]

    detail_response = await client_db.get(
        f"/api/v1/audit-logs/{audit_log_id}", headers=auth_headers(scope["admin"])
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == audit_log_id


async def test_audit_log_list_denies_teacher_and_student(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="audit-role-denied")
    for user in (scope["teacher"], scope["student_1"]):
        response = await client_db.get("/api/v1/audit-logs", headers=auth_headers(user))
        assert response.status_code == 403


async def test_audit_log_filtering_and_pagination(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="audit-filter")
    await mark_attendance(
        client_db,
        user=scope["admin"],
        classroom_id=scope["classroom"]["id"],
        subject_id=scope["subject"]["id"],
        attendance_date=TODAY,
        records=[{"student_profile_id": scope["student_profile_1"]["id"], "status": "present"}],
    )
    # A blocked attempt by the unrelated teacher, for a second, distinct row.
    await client_db.get(
        "/api/v1/attendance/detail",
        params={"classroom_id": scope["classroom"]["id"], "subject_id": scope["subject"]["id"]},
        headers=auth_headers(scope["other_teacher"]),
    )

    outcome_filtered = await client_db.get(
        "/api/v1/audit-logs",
        params={"outcome": "blocked", "actor_user_id": str(scope["other_teacher"].id)},
        headers=auth_headers(scope["admin"]),
    )
    assert outcome_filtered.status_code == 200
    outcome_body = outcome_filtered.json()
    assert outcome_body["total"] == 1
    assert outcome_body["items"][0]["outcome"] == "blocked"

    paginated = await client_db.get(
        "/api/v1/audit-logs",
        params={"limit": 1, "offset": 0},
        headers=auth_headers(scope["admin"]),
    )
    assert paginated.status_code == 200
    assert len(paginated.json()["items"]) == 1


async def test_audit_log_missing_id_returns_404(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="audit-404")
    response = await client_db.get(
        "/api/v1/audit-logs/00000000-0000-0000-0000-000000000000",
        headers=auth_headers(scope["admin"]),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "AUDIT_LOG_NOT_FOUND"


async def test_success_and_blocked_audits_are_both_visible(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="audit-both")
    await mark_attendance(
        client_db,
        user=scope["admin"],
        classroom_id=scope["classroom"]["id"],
        subject_id=scope["subject"]["id"],
        attendance_date=TODAY,
        records=[{"student_profile_id": scope["student_profile_1"]["id"], "status": "present"}],
    )
    await client_db.get(
        "/api/v1/attendance/daily",
        params={
            "classroom_id": scope["classroom"]["id"],
            "subject_id": scope["subject"]["id"],
            "attendance_date": TODAY,
        },
        headers=auth_headers(scope["other_teacher"]),
    )

    success_rows = await client_db.get(
        "/api/v1/audit-logs",
        params={"outcome": "success", "actor_user_id": str(scope["admin"].id)},
        headers=auth_headers(scope["admin"]),
    )
    blocked_rows = await client_db.get(
        "/api/v1/audit-logs",
        params={"outcome": "blocked", "actor_user_id": str(scope["other_teacher"].id)},
        headers=auth_headers(scope["admin"]),
    )
    assert success_rows.json()["total"] == 1
    assert blocked_rows.json()["total"] == 1


async def test_audit_log_has_no_write_routes(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="audit-no-write")
    admin_headers = auth_headers(scope["admin"])

    post_response = await client_db.post("/api/v1/audit-logs", json={}, headers=admin_headers)
    assert post_response.status_code == 405

    put_response = await client_db.put(
        "/api/v1/audit-logs/00000000-0000-0000-0000-000000000000",
        json={},
        headers=admin_headers,
    )
    assert put_response.status_code == 405

    patch_response = await client_db.patch(
        "/api/v1/audit-logs/00000000-0000-0000-0000-000000000000",
        json={},
        headers=admin_headers,
    )
    assert patch_response.status_code == 405

    delete_response = await client_db.delete(
        "/api/v1/audit-logs/00000000-0000-0000-0000-000000000000",
        headers=admin_headers,
    )
    assert delete_response.status_code == 405


async def test_audit_log_response_has_no_sensitive_metadata(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="audit-safe")
    admin_headers = auth_headers(scope["admin"])
    response = await client_db.get(
        "/api/v1/attendance/detail",
        params={"classroom_id": scope["classroom"]["id"], "subject_id": scope["subject"]["id"]},
        headers=auth_headers(scope["other_teacher"]),
    )
    assert response.status_code == 404

    audit_response = await client_db.get(
        "/api/v1/audit-logs",
        params={"actor_user_id": str(scope["other_teacher"].id)},
        headers=admin_headers,
    )
    body_text = audit_response.text
    bearer_token = admin_headers["Authorization"].split(" ", 1)[1]
    assert bearer_token not in body_text
    assert "password" not in body_text.lower()
    assert "authorization" not in body_text.lower()
