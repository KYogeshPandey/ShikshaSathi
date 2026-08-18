"""Tests for the database/filesystem drift reconciliation report.

The report is read-only (see
app/modules/biometric_enrollment/reconciliation.py's module docstring):
these tests assert findings appear for deliberately-introduced drift, and
that generating the report never itself deletes a file or changes a row.

Findings are asserted by *membership* (a specific key/sample_id appears
in the report), not by exact list equality — the storage root is shared
across the whole test session (see app/tests/conftest.py's
``BIOMETRIC_STORAGE_ROOT`` setup), so other tests' artifacts may also be
present and that is expected, not a test-isolation bug.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.biometric_enrollment.models import SampleStatus
from app.modules.biometric_enrollment.repository import (
    BiometricEnrollmentRepository,
    BiometricSampleRepository,
)
from app.modules.biometric_enrollment.storage import PrivateBiometricStorage
from app.tests.phase3_http_helpers import auth_headers
from app.tests.phase5_stage2_http_helpers import seed_enrollment_scope

_REPORT_URL = "/api/v1/biometric-enrollments/reconciliation/report"


def _storage() -> PrivateBiometricStorage:
    return PrivateBiometricStorage(get_settings())


async def test_reconciliation_report_requires_admin(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_enrollment_scope(client_db, db_session, suffix="recon-authz")

    unauthenticated = await client_db.get(_REPORT_URL)
    assert unauthenticated.status_code == 401

    as_teacher = await client_db.get(_REPORT_URL, headers=auth_headers(scope["teacher"]))
    assert as_teacher.status_code == 403

    as_student = await client_db.get(_REPORT_URL, headers=auth_headers(scope["student_1"]))
    assert as_student.status_code == 403

    as_admin = await client_db.get(_REPORT_URL, headers=auth_headers(scope["admin"]))
    assert as_admin.status_code == 200
    assert "findings" in as_admin.json()


async def test_orphaned_active_file_with_no_db_record_is_reported(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_enrollment_scope(client_db, db_session, suffix="recon-orphan-active")
    storage = _storage()
    key = storage.new_key()
    storage.active_path(key).write_bytes(b"orphaned-active-file-bytes")

    response = await client_db.get(_REPORT_URL, headers=auth_headers(scope["admin"]))
    assert response.status_code == 200
    findings = response.json()["findings"]
    matches = [
        f for f in findings if f["finding_type"] == "active_file_missing_record" and f["key"] == key
    ]
    assert len(matches) == 1

    # Read-only: the orphaned file must still be there afterward.
    assert storage.exists_active(key) is True
    storage.discard_staged(key)  # best-effort test cleanup (not part of the assertion)
    storage.active_path(key).unlink(missing_ok=True)


async def test_orphaned_staged_file_with_no_pending_record_is_reported(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_enrollment_scope(client_db, db_session, suffix="recon-orphan-staged")
    storage = _storage()
    key = storage.new_key()
    storage.staging_path(key).write_bytes(b"orphaned-staged-file-bytes")

    response = await client_db.get(_REPORT_URL, headers=auth_headers(scope["admin"]))
    assert response.status_code == 200
    findings = response.json()["findings"]
    matches = [
        f for f in findings if f["finding_type"] == "staged_file_missing_record" and f["key"] == key
    ]
    assert len(matches) == 1

    assert storage.exists_staged(key) is True
    storage.discard_staged(key)


async def test_orphaned_quarantined_file_with_no_db_record_is_reported(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_enrollment_scope(client_db, db_session, suffix="recon-orphan-quarantine")
    storage = _storage()
    key = storage.new_key()
    storage.quarantine_path(key).write_bytes(b"orphaned-quarantined-file-bytes")

    response = await client_db.get(_REPORT_URL, headers=auth_headers(scope["admin"]))
    assert response.status_code == 200
    findings = response.json()["findings"]
    matches = [
        f
        for f in findings
        if f["finding_type"] == "quarantined_file_missing_record" and f["key"] == key
    ]
    assert len(matches) == 1

    assert storage.exists_quarantined(key) is True
    storage.purge_quarantined(key)


async def test_stale_pending_sample_is_reported(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_enrollment_scope(client_db, db_session, suffix="recon-stale-pending")
    enrollments = BiometricEnrollmentRepository(db_session)
    samples = BiometricSampleRepository(db_session)

    enrollment = await enrollments.create(
        student_profile_id=uuid.UUID(scope["student_profile_1"]["id"]),
        created_by_user_id=scope["admin"].id,
    )
    sample = await samples.create_pending(
        enrollment_id=enrollment.id,
        storage_key=_storage().new_key(),
        original_filename=None,
        content_type="image/jpeg",
        file_size_bytes=1234,
        width_px=100,
        height_px=100,
        sha256_hash="a" * 64,
        created_by_user_id=scope["admin"].id,
    )
    # Backdate well past the default 60-minute staging timeout.
    sample.created_at = datetime.now(UTC) - timedelta(days=2)
    await db_session.flush()
    await db_session.commit()

    response = await client_db.get(_REPORT_URL, headers=auth_headers(scope["admin"]))
    assert response.status_code == 200
    findings = response.json()["findings"]
    matches = [
        f
        for f in findings
        if f["finding_type"] == "pending_sample_stale" and f["sample_id"] == str(sample.id)
    ]
    assert len(matches) == 1


async def test_replacement_pending_sample_is_always_reported(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_enrollment_scope(client_db, db_session, suffix="recon-replacement-pending")
    enrollments = BiometricEnrollmentRepository(db_session)
    samples = BiometricSampleRepository(db_session)

    enrollment = await enrollments.create(
        student_profile_id=uuid.UUID(scope["student_profile_2"]["id"]),
        created_by_user_id=scope["admin"].id,
    )
    sample = await samples.create_pending(
        enrollment_id=enrollment.id,
        storage_key=_storage().new_key(),
        original_filename=None,
        content_type="image/jpeg",
        file_size_bytes=1234,
        width_px=100,
        height_px=100,
        sha256_hash="b" * 64,
        created_by_user_id=scope["admin"].id,
    )
    sample.status = SampleStatus.REPLACEMENT_PENDING
    await db_session.flush()
    await db_session.commit()

    response = await client_db.get(_REPORT_URL, headers=auth_headers(scope["admin"]))
    assert response.status_code == 200
    findings = response.json()["findings"]
    matches = [
        f
        for f in findings
        if f["finding_type"] == "replacement_pending_incomplete"
        and f["sample_id"] == str(sample.id)
    ]
    assert len(matches) == 1
