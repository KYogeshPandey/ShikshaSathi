"""HTTP coverage for bounded Phase 3 CSV/XLSX imports."""

from __future__ import annotations

import io

from httpx import AsyncClient
from openpyxl import Workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bulk_imports.parser import MAX_IMPORT_BYTES, MAX_IMPORT_ROWS
from app.modules.users.models import UserRole
from app.tests.phase3_http_helpers import auth_headers, seed_user


def _xlsx_bytes(rows: list[list[object]]) -> bytes:
    workbook = Workbook(write_only=True)
    worksheet = workbook.create_sheet()
    for row in rows:
        worksheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


async def test_csv_import_reports_row_errors_and_keeps_valid_rows(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await seed_user(db_session, email="import-admin@example.com", role=UserRole.ADMIN)
    content = (
        b"name,code,grade_level,section\n"
        b"Grade 7 A,G7-A,7,A\n"
        b"Missing Code,,7,B\n"
        b"Duplicate,G7-A,7,C\n"
    )
    response = await client_db.post(
        "/api/v1/imports/classrooms",
        files={"file": ("classrooms.csv", content, "text/csv")},
        headers=auth_headers(admin),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["total_rows"] == 3
    assert body["imported_count"] == 1
    assert body["failed_count"] == 2
    assert [error["row_number"] for error in body["errors"]] == [3, 4]
    assert {error["code"] for error in body["errors"]} == {
        "BULK_IMPORT_ROW_VALIDATION_ERROR",
        "CLASSROOM_CODE_ALREADY_EXISTS",
    }

    classrooms = await client_db.get("/api/v1/classrooms", headers=auth_headers(admin))
    assert classrooms.json()["total"] == 1
    assert classrooms.json()["items"][0]["code"] == "g7-a"


async def test_xlsx_import_succeeds_and_non_admin_is_denied(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await seed_user(db_session, email="xlsx-admin@example.com", role=UserRole.ADMIN)
    teacher = await seed_user(db_session, email="xlsx-teacher@example.com", role=UserRole.TEACHER)
    content = _xlsx_bytes(
        [
            ["name", "code", "is_elective"],
            ["Physics", "PHY", False],
            ["Robotics", "ROB", True],
        ]
    )

    denied = await client_db.post(
        "/api/v1/imports/subjects",
        files={
            "file": (
                "subjects.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=auth_headers(teacher),
    )
    assert denied.status_code == 403

    imported = await client_db.post(
        "/api/v1/imports/subjects",
        files={
            "file": (
                "subjects.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=auth_headers(admin),
    )
    assert imported.status_code == 200
    assert imported.json()["success"] is True
    assert imported.json()["imported_count"] == 2


async def test_malformed_xlsx_and_row_limit_return_stable_errors(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await seed_user(
        db_session, email="invalid-import-admin@example.com", role=UserRole.ADMIN
    )
    headers = auth_headers(admin, request_id="phase3-import-error")
    malformed = await client_db.post(
        "/api/v1/imports/classrooms",
        files={"file": ("broken.xlsx", b"not-an-xlsx", "application/octet-stream")},
        headers=headers,
    )
    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "BULK_IMPORT_INVALID_FILE"
    assert malformed.json()["request_id"] == "phase3-import-error"

    rows = ["name,code"]
    rows.extend(f"Classroom {index},classroom-{index}" for index in range(MAX_IMPORT_ROWS + 1))
    too_many = await client_db.post(
        "/api/v1/imports/classrooms",
        files={"file": ("too-many.csv", "\n".join(rows).encode(), "text/csv")},
        headers=auth_headers(admin),
    )
    assert too_many.status_code == 422
    assert too_many.json()["error"]["code"] == "BULK_IMPORT_ROW_LIMIT_EXCEEDED"


async def test_unauthenticated_bulk_import_returns_401(client_db: AsyncClient) -> None:
    response = await client_db.post(
        "/api/v1/imports/classrooms",
        files={"file": ("classrooms.csv", b"name,code\nA,a\n", "text/csv")},
    )
    assert response.status_code == 401


async def test_unsupported_file_extension_is_rejected(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await seed_user(
        db_session, email="unsupported-ext-admin@example.com", role=UserRole.ADMIN
    )
    response = await client_db.post(
        "/api/v1/imports/classrooms",
        files={"file": ("classrooms.txt", b"name,code\nA,a\n", "text/plain")},
        headers=auth_headers(admin),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "BULK_IMPORT_INVALID_FILE"


async def test_oversized_file_is_rejected(client_db: AsyncClient, db_session: AsyncSession) -> None:
    admin = await seed_user(db_session, email="oversized-admin@example.com", role=UserRole.ADMIN)
    oversized_content = b"a" * (MAX_IMPORT_BYTES + 1)
    response = await client_db.post(
        "/api/v1/imports/classrooms",
        files={"file": ("huge.csv", oversized_content, "text/csv")},
        headers=auth_headers(admin),
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "BULK_IMPORT_FILE_TOO_LARGE"


async def test_missing_required_column_in_header_is_rejected(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await seed_user(
        db_session, email="missing-header-admin@example.com", role=UserRole.ADMIN
    )
    # The header row itself omits "code" entirely (not just a blank value),
    # exercising a different path than a present-but-empty cell.
    content = b"name\nNo Code Classroom\n"
    response = await client_db.post(
        "/api/v1/imports/classrooms",
        files={"file": ("classrooms.csv", content, "text/csv")},
        headers=auth_headers(admin),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["imported_count"] == 0
    assert body["errors"][0]["code"] == "BULK_IMPORT_ROW_VALIDATION_ERROR"


async def test_xlsx_numeric_identifier_cells_normalize_successfully(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    """Excel's default "General" number format reads whole numbers back as
    ``float``/``int``, not ``str``. Classroom/subject codes, employee codes,
    and roll numbers are all string-typed identifier fields, so a purely
    numeric-looking value must still import successfully instead of failing
    Pydantic validation (the bug fixed in app/modules/bulk_imports/parser.py)."""
    admin = await seed_user(
        db_session, email="numeric-cells-admin@example.com", role=UserRole.ADMIN
    )
    teacher_user = await seed_user(
        db_session, email="numeric-cells-teacher@example.com", role=UserRole.TEACHER
    )
    student_user = await seed_user(
        db_session, email="numeric-cells-student@example.com", role=UserRole.STUDENT
    )

    # Classroom code and subject code as whole-number floats (12.0 -> "12").
    classroom_content = _xlsx_bytes(
        [["name", "code", "grade_level", "section"], ["Grade 12", 12.0, 12, "A"]]
    )
    classroom_response = await client_db.post(
        "/api/v1/imports/classrooms",
        files={"file": ("classrooms.xlsx", classroom_content, "application/octet-stream")},
        headers=auth_headers(admin),
    )
    assert classroom_response.status_code == 200
    assert classroom_response.json()["success"] is True
    assert classroom_response.json()["imported_count"] == 1

    classrooms = await client_db.get("/api/v1/classrooms", headers=auth_headers(admin))
    assert classrooms.json()["items"][0]["code"] == "12"
    assert classrooms.json()["items"][0]["grade_level"] == "12"

    subject_content = _xlsx_bytes([["name", "code", "is_elective"], ["Subject 7", 7, False]])
    subject_response = await client_db.post(
        "/api/v1/imports/subjects",
        files={"file": ("subjects.xlsx", subject_content, "application/octet-stream")},
        headers=auth_headers(admin),
    )
    assert subject_response.status_code == 200
    assert subject_response.json()["success"] is True

    # Employee code as a whole-number int.
    teacher_content = _xlsx_bytes(
        [
            ["user_id", "employee_code", "phone_number"],
            [str(teacher_user.id), 4500, "9990001111"],
        ]
    )
    teacher_response = await client_db.post(
        "/api/v1/imports/teacher-profiles",
        files={"file": ("teachers.xlsx", teacher_content, "application/octet-stream")},
        headers=auth_headers(admin),
    )
    assert teacher_response.status_code == 200
    assert teacher_response.json()["success"] is True
    assert teacher_response.json()["imported_count"] == 1

    # Roll number as a whole-number float, linked to the classroom created above.
    classroom_id = classrooms.json()["items"][0]["id"]
    student_content = _xlsx_bytes(
        [
            ["user_id", "classroom_id", "roll_number"],
            [str(student_user.id), classroom_id, 5.0],
        ]
    )
    student_response = await client_db.post(
        "/api/v1/imports/student-profiles",
        files={"file": ("students.xlsx", student_content, "application/octet-stream")},
        headers=auth_headers(admin),
    )
    assert student_response.status_code == 200
    assert student_response.json()["success"] is True
    assert student_response.json()["imported_count"] == 1


async def test_valid_rows_after_a_failed_row_still_import(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    """A failure on one row must not corrupt the shared session/transaction
    for rows processed afterwards (regression coverage for the per-row
    ``service_transaction`` commit/rollback boundary)."""
    admin = await seed_user(
        db_session, email="continue-after-failure-admin@example.com", role=UserRole.ADMIN
    )
    content = b"name,code\nFirst,first-code\nBad,\nSecond,second-code\n"
    response = await client_db.post(
        "/api/v1/imports/classrooms",
        files={"file": ("classrooms.csv", content, "text/csv")},
        headers=auth_headers(admin),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["imported_count"] == 2
    assert body["failed_count"] == 1
    assert [error["row_number"] for error in body["errors"]] == [3]

    classrooms = await client_db.get("/api/v1/classrooms", headers=auth_headers(admin))
    codes = {item["code"] for item in classrooms.json()["items"]}
    assert codes == {"first-code", "second-code"}


async def test_row_errors_never_echo_submitted_values_or_secrets(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    """Error messages/details must stay to stable code+message, never the
    submitted row, and the response body must never carry a password,
    token, or hash field (there are none on these entities, but this
    guards against a future field being added carelessly)."""
    admin = await seed_user(db_session, email="no-echo-admin@example.com", role=UserRole.ADMIN)
    secret_looking_name = "TotallyNotAPassword-hunter2-SECRET"
    content = (f"name,code\n{secret_looking_name},\n").encode()
    response = await client_db.post(
        "/api/v1/imports/classrooms",
        files={"file": ("classrooms.csv", content, "text/csv")},
        headers=auth_headers(admin),
    )
    assert response.status_code == 200
    raw_text = response.text
    assert secret_looking_name not in raw_text
    for banned in ("password", "password_hash", "token", "hash", "secret"):
        assert banned not in raw_text.lower()
