"""Phase 4 Stage 3 HTTP coverage: ``GET /api/v1/attendance/export``.

Covers authorization (same exact-scope rules as detail/stats), CSV
shape (headers, stable column order, empty-result behavior), and
formula-injection escaping for every trigger character the Stage 3
brief lists (``=``, ``+``, ``-``, ``@``).
"""

from __future__ import annotations

import csv
import io
import os
import tempfile
from datetime import date

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.attendance.csv_export import CSV_COLUMNS
from app.modules.attendance.models import AuditLog, AuditOutcome
from app.tests.attendance_http_helpers import mark_attendance, seed_attendance_scope
from app.tests.phase3_http_helpers import auth_headers

TODAY = date.today().isoformat()


def _parse_csv(body: bytes) -> list[list[str]]:
    text = body.decode("utf-8")
    return list(csv.reader(io.StringIO(text)))


async def test_csv_admin_export_succeeds(client_db: AsyncClient, db_session: AsyncSession) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="csv-admin")
    await mark_attendance(
        client_db,
        user=scope["admin"],
        classroom_id=scope["classroom"]["id"],
        subject_id=scope["subject"]["id"],
        attendance_date=TODAY,
        records=[{"student_profile_id": scope["student_profile_1"]["id"], "status": "present"}],
    )
    response = await client_db.get(
        "/api/v1/attendance/export",
        params={"classroom_id": scope["classroom"]["id"], "subject_id": scope["subject"]["id"]},
        headers=auth_headers(scope["admin"]),
    )
    assert response.status_code == 200
    rows = _parse_csv(response.content)
    assert rows[0] == list(CSV_COLUMNS)
    assert len(rows) == 2  # header + one data row


async def test_csv_assigned_teacher_export_succeeds(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="csv-teacher")
    await mark_attendance(
        client_db,
        user=scope["teacher"],
        classroom_id=scope["classroom"]["id"],
        subject_id=scope["subject"]["id"],
        attendance_date=TODAY,
        records=[{"student_profile_id": scope["student_profile_1"]["id"], "status": "present"}],
    )
    response = await client_db.get(
        "/api/v1/attendance/export",
        params={"classroom_id": scope["classroom"]["id"], "subject_id": scope["subject"]["id"]},
        headers=auth_headers(scope["teacher"]),
    )
    assert response.status_code == 200


async def test_csv_unrelated_teacher_denied_and_audited(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="csv-unrelated")
    response = await client_db.get(
        "/api/v1/attendance/export",
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
                    AuditLog.action == "attendance.export",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1


async def test_csv_student_export_is_forbidden(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="csv-student")
    response = await client_db.get(
        "/api/v1/attendance/export",
        params={"classroom_id": scope["classroom"]["id"], "subject_id": scope["subject"]["id"]},
        headers=auth_headers(scope["student_1"]),
    )
    assert response.status_code == 403


async def test_csv_content_type_and_disposition(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="csv-headers")
    response = await client_db.get(
        "/api/v1/attendance/export",
        params={"classroom_id": scope["classroom"]["id"], "subject_id": scope["subject"]["id"]},
        headers=auth_headers(scope["admin"]),
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment; filename=")
    assert disposition.endswith('.csv"')
    # Filename is server-controlled, built only from the classroom/subject
    # codes — never from any client-supplied filename/path.
    assert scope["classroom"]["code"] in disposition
    assert scope["subject"]["code"] in disposition


async def test_csv_filters_affect_exported_rows(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="csv-filter")
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
        "/api/v1/attendance/export",
        params={
            "classroom_id": scope["classroom"]["id"],
            "subject_id": scope["subject"]["id"],
            "status": "absent",
        },
        headers=auth_headers(scope["admin"]),
    )
    rows = _parse_csv(response.content)
    assert len(rows) == 2  # header + one absent row
    status_index = list(CSV_COLUMNS).index("status")
    assert rows[1][status_index] == "absent"


async def test_csv_empty_result_contains_header_row(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="csv-empty")
    response = await client_db.get(
        "/api/v1/attendance/export",
        params={"classroom_id": scope["classroom"]["id"], "subject_id": scope["subject"]["id"]},
        headers=auth_headers(scope["admin"]),
    )
    assert response.status_code == 200
    rows = _parse_csv(response.content)
    assert rows == [list(CSV_COLUMNS)]


async def test_csv_formula_injection_escaping(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    """Every trigger character in the Stage 3 brief is prefixed with an apostrophe."""
    scope = await seed_attendance_scope(client_db, db_session, suffix="csv-formula")
    remarks_index = list(CSV_COLUMNS).index("remarks")
    dangerous_remarks = ["=SUM(A1:A2)", "+1+1", "-1+1", "@echo"]

    for i, remark in enumerate(dangerous_remarks):
        student_id = (
            scope["student_profile_1"]["id"] if i % 2 == 0 else scope["student_profile_2"]["id"]
        )
        await mark_attendance(
            client_db,
            user=scope["admin"],
            classroom_id=scope["classroom"]["id"],
            subject_id=scope["subject"]["id"],
            attendance_date=TODAY,
            records=[{"student_profile_id": student_id, "status": "present", "remarks": remark}],
        )
        response = await client_db.get(
            "/api/v1/attendance/export",
            params={
                "classroom_id": scope["classroom"]["id"],
                "subject_id": scope["subject"]["id"],
                "student_profile_id": student_id,
            },
            headers=auth_headers(scope["admin"]),
        )
        assert response.status_code == 200
        rows = _parse_csv(response.content)
        exported_remark = rows[1][remarks_index]
        assert exported_remark == f"'{remark}"
        assert not exported_remark.startswith(("=", "+", "-", "@"))


async def test_csv_creates_no_temporary_file(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="csv-notemp")
    tmp_dir = tempfile.gettempdir()
    before = set(os.listdir(tmp_dir))
    response = await client_db.get(
        "/api/v1/attendance/export",
        params={"classroom_id": scope["classroom"]["id"], "subject_id": scope["subject"]["id"]},
        headers=auth_headers(scope["admin"]),
    )
    after = set(os.listdir(tmp_dir))
    assert response.status_code == 200
    assert after - before == set()


async def test_csv_output_contains_no_sensitive_data(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="csv-safe")
    headers = auth_headers(scope["admin"])
    response = await client_db.get(
        "/api/v1/attendance/export",
        params={"classroom_id": scope["classroom"]["id"], "subject_id": scope["subject"]["id"]},
        headers=headers,
    )
    body_text = response.content.decode("utf-8")
    bearer_token = headers["Authorization"].split(" ", 1)[1]
    assert bearer_token not in body_text
    assert "password" not in body_text.lower()
    assert "authorization" not in body_text.lower()
