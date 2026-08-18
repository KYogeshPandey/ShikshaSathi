"""HTTP integration coverage for secure bulk ZIP biometric enrollment.

Uses the real router -> bulk_service -> zip_security -> repository ->
Postgres path via ``client_db``/``db_session``. Two distinct response
shapes are exercised deliberately (see
app/modules/biometric_enrollment/bulk_service.py's module docstring and
app/modules/biometric_enrollment/router.py):

- An **archive-level** problem (bad ZIP, missing/invalid manifest, an
  unsafe member path, an encrypted/symlink/nested member, excessive
  count/size) is raised by ``zip_security.validate_archive`` itself and
  surfaces as a plain ``422``/``413`` ``AppError`` envelope — the batch
  never reaches per-row processing at all.
- A **row-level** problem (student not found/inactive/already enrolled,
  duplicate content) is discovered per-row and surfaces as a ``200``
  response with ``BulkEnrollmentResult(success=False, ...)`` — the batch
  is still atomic (zero rows enrolled), but the shape is the friendlier,
  per-row-reported one.

In both cases, the required regression is the same: zero
``BiometricEnrollment``/``BiometricSample`` rows exist afterward.
"""

from __future__ import annotations

import io
import zipfile
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.attendance.models import AuditLog, AuditOutcome
from app.modules.biometric_enrollment.models import BiometricEnrollment, BiometricSample
from app.tests.phase3_http_helpers import auth_headers
from app.tests.phase5_stage2_http_helpers import make_jpeg_bytes, seed_enrollment_scope

_MANIFEST_HEADER = "student_profile_id,filename"


def _manifest_csv(rows: list[tuple[str, str]]) -> bytes:
    lines = [_MANIFEST_HEADER] + [f"{student_id},{filename}" for student_id, filename in rows]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _build_zip(entries: list[tuple[Any, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for entry, content in entries:
            zf.writestr(entry, content)
    return buffer.getvalue()


async def _enrollment_and_sample_counts(session: AsyncSession) -> tuple[int, int]:
    enrollment_count = (
        await session.execute(select(func.count()).select_from(BiometricEnrollment))
    ).scalar_one()
    sample_count = (
        await session.execute(select(func.count()).select_from(BiometricSample))
    ).scalar_one()
    return enrollment_count, sample_count


async def _post_zip(client: AsyncClient, *, content: bytes, user: Any) -> Any:
    return await client.post(
        "/api/v1/biometric-enrollments/bulk",
        files={"file": ("enrollment.zip", content, "application/zip")},
        headers=auth_headers(user),
    )


async def test_bulk_unauthenticated_returns_401(client_db: AsyncClient) -> None:
    zip_bytes = _build_zip([("manifest.csv", _manifest_csv([]))])
    response = await client_db.post(
        "/api/v1/biometric-enrollments/bulk",
        files={"file": ("enrollment.zip", zip_bytes, "application/zip")},
    )
    assert response.status_code == 401


async def test_bulk_forbidden_for_teacher(client_db: AsyncClient, db_session: AsyncSession) -> None:
    scope = await seed_enrollment_scope(client_db, db_session, suffix="bulk-teacher-403")
    zip_bytes = _build_zip([("manifest.csv", _manifest_csv([]))])
    response = await _post_zip(client_db, content=zip_bytes, user=scope["teacher"])
    assert response.status_code == 403


async def test_bulk_valid_batch_enrolls_every_row(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_enrollment_scope(client_db, db_session, suffix="bulk-valid")
    student_1_id = scope["student_profile_1"]["id"]
    student_2_id = scope["student_profile_2"]["id"]
    zip_bytes = _build_zip(
        [
            ("manifest.csv", _manifest_csv([(student_1_id, "one.jpg"), (student_2_id, "two.jpg")])),
            ("one.jpg", make_jpeg_bytes()),
            ("two.jpg", make_jpeg_bytes(color=(80, 90, 100))),
        ]
    )
    response = await _post_zip(client_db, content=zip_bytes, user=scope["admin"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["total_rows"] == 2
    assert body["enrolled_count"] == 2
    assert body["failed_count"] == 0
    assert {row["outcome"] for row in body["rows"]} == {"enrolled"}

    detail_response = await client_db.get(
        f"/api/v1/biometric-enrollments/{student_1_id}", headers=auth_headers(scope["admin"])
    )
    assert detail_response.json()["enrollment"]["status"] == "active"


async def test_bulk_archive_with_path_traversal_member_is_rejected_atomically(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    """The required regression: ``../../evil.jpg`` must never be extracted or enrolled."""
    scope = await seed_enrollment_scope(client_db, db_session, suffix="bulk-traversal")
    student_id = scope["student_profile_1"]["id"]
    before_counts = await _enrollment_and_sample_counts(db_session)

    zip_bytes = _build_zip(
        [
            ("manifest.csv", _manifest_csv([(student_id, "../../evil.jpg")])),
            (zipfile.ZipInfo("../../evil.jpg"), make_jpeg_bytes()),
        ]
    )
    response = await _post_zip(client_db, content=zip_bytes, user=scope["admin"])

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "BULK_ENROLLMENT_VALIDATION_FAILED"
    error_codes = {item["code"] for item in body["error"]["details"]["errors"]}
    assert "ZIP_MEMBER_PATH_TRAVERSAL" in error_codes

    after_counts = await _enrollment_and_sample_counts(db_session)
    assert after_counts == before_counts


async def test_bulk_oversized_zip_returns_413_with_correct_error_code(
    client_db: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ZIP over the configured archive-byte cap is ``BULK_ENROLLMENT_ZIP_TOO_LARGE``.

    Regression test: this used to incorrectly raise the single-image
    ``EnrollmentImageTooLargeError`` (wrong error code/message) instead
    of the archive-level ``BulkEnrollmentZipTooLargeError``.
    """
    import app.modules.biometric_enrollment.bulk_service as bulk_service_module
    from app.core.config import get_settings

    small_cap_settings = get_settings().model_copy(update={"MAX_BULK_ENROLLMENT_ZIP_BYTES": 100})
    monkeypatch.setattr(bulk_service_module, "get_settings", lambda: small_cap_settings)

    scope = await seed_enrollment_scope(client_db, db_session, suffix="bulk-zip-too-large")
    student_id = scope["student_profile_1"]["id"]
    zip_bytes = _build_zip(
        [
            ("manifest.csv", _manifest_csv([(student_id, "a.jpg")])),
            ("a.jpg", make_jpeg_bytes(size=(400, 400))),
        ]
    )
    response = await _post_zip(client_db, content=zip_bytes, user=scope["admin"])
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "BULK_ENROLLMENT_ZIP_TOO_LARGE"


async def test_bulk_archive_level_rejection_writes_blocked_audit(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    """An archive-level rejection (raised by ``validate_archive`` itself,
    before any row is ever reached — here, a path-traversal member) must
    still create a BLOCKED bulk-attempt audit record, same as a row-level
    rejection does. Only aggregate counts are ever recorded — never a
    filename, member path, or any archive content.
    """
    scope = await seed_enrollment_scope(client_db, db_session, suffix="bulk-traversal-audit")
    student_id = scope["student_profile_1"]["id"]
    zip_bytes = _build_zip(
        [
            ("manifest.csv", _manifest_csv([(student_id, "../../evil.jpg")])),
            (zipfile.ZipInfo("../../evil.jpg"), make_jpeg_bytes()),
        ]
    )
    response = await _post_zip(client_db, content=zip_bytes, user=scope["admin"])
    assert response.status_code == 422

    blocked_logs = (
        (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.actor_user_id == scope["admin"].id,
                    AuditLog.outcome == AuditOutcome.BLOCKED,
                    AuditLog.action == "biometric_enrollment.bulk_attempted",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(blocked_logs) == 1
    # Exact-equality (not just a subset check): proves nothing beyond the
    # two aggregate counts was recorded — no filename, no member path.
    assert blocked_logs[0].event_metadata == {"total_rows": 0, "enrolled_count": 0}


async def test_bulk_missing_manifest_is_rejected(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_enrollment_scope(client_db, db_session, suffix="bulk-no-manifest")
    zip_bytes = _build_zip([("a.jpg", make_jpeg_bytes())])
    response = await _post_zip(client_db, content=zip_bytes, user=scope["admin"])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "BULK_ENROLLMENT_VALIDATION_FAILED"


async def test_bulk_unreferenced_member_is_rejected(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_enrollment_scope(client_db, db_session, suffix="bulk-unreferenced")
    student_id = scope["student_profile_1"]["id"]
    zip_bytes = _build_zip(
        [
            ("manifest.csv", _manifest_csv([(student_id, "a.jpg")])),
            ("a.jpg", make_jpeg_bytes()),
            ("b.jpg", make_jpeg_bytes()),
        ]
    )
    response = await _post_zip(client_db, content=zip_bytes, user=scope["admin"])
    assert response.status_code == 422
    error_codes = {item["code"] for item in response.json()["error"]["details"]["errors"]}
    assert "ZIP_MEMBER_UNREFERENCED" in error_codes


async def test_bulk_duplicate_manifest_row_is_rejected(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_enrollment_scope(client_db, db_session, suffix="bulk-dup-row")
    student_id = scope["student_profile_1"]["id"]
    zip_bytes = _build_zip(
        [
            (
                "manifest.csv",
                _manifest_csv([(student_id, "a.jpg"), (student_id, "b.jpg")]),
            ),
            ("a.jpg", make_jpeg_bytes()),
            ("b.jpg", make_jpeg_bytes()),
        ]
    )
    response = await _post_zip(client_db, content=zip_bytes, user=scope["admin"])
    assert response.status_code == 422
    error_codes = {item["code"] for item in response.json()["error"]["details"]["errors"]}
    assert "ZIP_MANIFEST_DUPLICATE_STUDENT" in error_codes


async def test_bulk_row_with_unknown_student_fails_whole_batch_atomically(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    """Row-level (not archive-level) failure: still atomic, still zero writes."""
    scope = await seed_enrollment_scope(client_db, db_session, suffix="bulk-unknown-student")
    student_id = scope["student_profile_1"]["id"]
    unknown_student_id = "99999999-9999-9999-9999-999999999999"
    before_counts = await _enrollment_and_sample_counts(db_session)

    zip_bytes = _build_zip(
        [
            (
                "manifest.csv",
                _manifest_csv([(student_id, "a.jpg"), (unknown_student_id, "b.jpg")]),
            ),
            ("a.jpg", make_jpeg_bytes()),
            ("b.jpg", make_jpeg_bytes(color=(1, 2, 3))),
        ]
    )
    response = await _post_zip(client_db, content=zip_bytes, user=scope["admin"])
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["enrolled_count"] == 0
    assert body["failed_count"] == 2

    rows_by_number = {row["row_number"]: row for row in body["rows"]}
    # Row 3 (the unknown student) carries the real reason...
    assert rows_by_number[3]["error_code"] == "ROW_STUDENT_NOT_FOUND"
    # ...row 2 was individually valid but is reported failed too, because
    # the batch is all-or-nothing (see bulk_service.py's module docstring).
    assert rows_by_number[2]["error_code"] == "ROW_BATCH_REJECTED"

    after_counts = await _enrollment_and_sample_counts(db_session)
    assert after_counts == before_counts


async def test_bulk_row_for_already_active_student_fails_whole_batch(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_enrollment_scope(client_db, db_session, suffix="bulk-already-active")
    student_1_id = scope["student_profile_1"]["id"]
    student_2_id = scope["student_profile_2"]["id"]

    pre_enroll_zip = _build_zip(
        [
            ("manifest.csv", _manifest_csv([(student_1_id, "pre.jpg")])),
            ("pre.jpg", make_jpeg_bytes()),
        ]
    )
    pre_response = await _post_zip(client_db, content=pre_enroll_zip, user=scope["admin"])
    assert pre_response.json()["success"] is True

    before_counts = await _enrollment_and_sample_counts(db_session)
    batch_zip = _build_zip(
        [
            (
                "manifest.csv",
                _manifest_csv([(student_1_id, "a.jpg"), (student_2_id, "b.jpg")]),
            ),
            ("a.jpg", make_jpeg_bytes()),
            ("b.jpg", make_jpeg_bytes(color=(9, 8, 7))),
        ]
    )
    response = await _post_zip(client_db, content=batch_zip, user=scope["admin"])
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["enrolled_count"] == 0

    after_counts = await _enrollment_and_sample_counts(db_session)
    assert after_counts == before_counts


async def test_bulk_audit_log_written_on_success(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_enrollment_scope(client_db, db_session, suffix="bulk-audit")
    student_id = scope["student_profile_1"]["id"]
    zip_bytes = _build_zip(
        [
            ("manifest.csv", _manifest_csv([(student_id, "a.jpg")])),
            ("a.jpg", make_jpeg_bytes()),
        ]
    )
    response = await _post_zip(client_db, content=zip_bytes, user=scope["admin"])
    assert response.json()["success"] is True

    completed_logs = (
        (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.actor_user_id == scope["admin"].id,
                    AuditLog.outcome == AuditOutcome.SUCCESS,
                    AuditLog.action == "biometric_enrollment.bulk_completed",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(completed_logs) == 1
    assert completed_logs[0].event_metadata.get("enrolled_count") == 1
