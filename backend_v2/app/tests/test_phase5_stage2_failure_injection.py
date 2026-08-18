"""Failure-injection tests for compensating cleanup.

Verifies the specific guarantee stated throughout
app/modules/biometric_enrollment/service.py and
app/modules/biometric_enrollment/bulk_service.py's docstrings: a SQL
transaction cannot roll back a filesystem rename, so every code path
that performs both must compensate explicitly when the filesystem step
fails. These tests monkeypatch
``PrivateBiometricStorage.promote``/``quarantine`` to simulate a real
``OSError`` (disk full, permission denied) at exactly the point after a
PENDING database row already exists, then assert the student is never
left with a falsely active enrollment.
"""

from __future__ import annotations

import io
import zipfile
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.attendance.repository import AuditLogRepository
from app.modules.biometric_enrollment.models import (
    BiometricEnrollment,
    BiometricSample,
    EnrollmentStatus,
    SampleStatus,
)
from app.modules.biometric_enrollment.storage import PrivateBiometricStorage
from app.tests.phase3_http_helpers import auth_headers
from app.tests.phase5_stage2_http_helpers import (
    make_jpeg_bytes,
    make_png_bytes,
    seed_enrollment_scope,
    upload_sample,
)

_MANIFEST_HEADER = "student_profile_id,filename"


def _manifest_csv(rows: list[tuple[str, str]]) -> bytes:
    """Duplicated from test_phase5_stage2_bulk_zip_http.py on purpose — a
    four-line CSV builder is not worth a cross-test-module import; no
    other test file in this suite imports from another one either.
    """
    lines = [_MANIFEST_HEADER] + [f"{student_id},{filename}" for student_id, filename in rows]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _build_zip(entries: list[tuple[Any, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for entry, content in entries:
            zf.writestr(entry, content)
    return buffer.getvalue()


async def _post_zip(client: AsyncClient, *, content: bytes, user: Any) -> Any:
    return await client.post(
        "/api/v1/biometric-enrollments/bulk",
        files={"file": ("enrollment.zip", content, "application/zip")},
        headers=auth_headers(user),
    )


def _break_promote(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(self: PrivateBiometricStorage, key: str) -> None:
        raise OSError("simulated disk failure during promote")

    monkeypatch.setattr(PrivateBiometricStorage, "promote", _raise)


def _capture_promoted_keys(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Spy on a real ``promote`` call, recording which key(s) it actually
    promoted to the active/ zone. Needed because API responses never
    expose a storage key (see this module's schemas' contract) and a
    compensated row's sample DB row is gone by the time the test can
    inspect it — this is the only way to learn which key to check
    ``active``/``quarantined`` membership for afterward.
    """
    captured: list[str] = []
    original_promote = PrivateBiometricStorage.promote

    def _spy(self: PrivateBiometricStorage, key: str) -> None:
        original_promote(self, key)
        captured.append(key)

    monkeypatch.setattr(PrivateBiometricStorage, "promote", _spy)
    return captured


def _capture_new_keys(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Spy on every storage key generated during the patched window.

    Used to verify complete cleanup (no leftover file in *any* zone) for
    every row in a batch, without assuming exact ``list_*_keys()`` set
    equality — the storage root is shared across the whole test session
    (see test_phase5_stage2_reconciliation.py's module docstring), so
    only membership of specifically-known keys is ever safe to assert.
    """
    captured: list[str] = []
    original_new_key = PrivateBiometricStorage.new_key

    def _spy(self: PrivateBiometricStorage) -> str:
        key = original_new_key(self)
        captured.append(key)
        return key

    monkeypatch.setattr(PrivateBiometricStorage, "new_key", _spy)
    return captured


def _break_audit_create_for_action(monkeypatch: pytest.MonkeyPatch, *, action: str) -> None:
    """Fail only the audit write for one specific ``action``.

    Simulates a database/audit failure that happens strictly *after* a
    filesystem promote already succeeded — narrowed by ``action`` (every
    call already passes it as a keyword argument; see
    app/modules/attendance/repository.py's ``AuditLogRepository.create``)
    so this doesn't also break the scope-seeding helpers' own, unrelated
    audit writes, which share the same repository class.
    """
    original_create = AuditLogRepository.create

    async def _raise_for_action(self: AuditLogRepository, *args: object, **kwargs: object) -> Any:
        if kwargs.get("action") == action:
            raise RuntimeError("simulated database failure writing final status/audit")
        return await original_create(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(AuditLogRepository, "create", _raise_for_action)


async def test_create_sample_promote_failure_leaves_no_falsely_active_sample(
    client_db: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    scope = await seed_enrollment_scope(client_db, db_session, suffix="fail-create-promote")
    student_profile_id = scope["student_profile_1"]["id"]

    _break_promote(monkeypatch)
    with pytest.raises(OSError, match="simulated disk failure during promote"):
        await upload_sample(
            client_db,
            student_profile_id=student_profile_id,
            user=scope["admin"],
            content=make_jpeg_bytes(),
        )

    remaining_samples = (
        (
            await db_session.execute(
                select(BiometricSample).where(
                    BiometricSample.status.in_([SampleStatus.ACTIVE, SampleStatus.PENDING])
                )
            )
        )
        .scalars()
        .all()
    )
    # The compensating cleanup must have deleted the orphaned PENDING row —
    # no PENDING or (impossibly, without a successful promote) ACTIVE row
    # should exist for this student at all.
    assert remaining_samples == []


async def test_create_sample_promote_failure_allows_retry_after_fix(
    client_db: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After a transient failure is fixed, the same student can enroll normally."""
    scope = await seed_enrollment_scope(client_db, db_session, suffix="fail-create-retry")
    student_profile_id = scope["student_profile_1"]["id"]

    _break_promote(monkeypatch)
    with pytest.raises(OSError, match="simulated disk failure during promote"):
        await upload_sample(
            client_db,
            student_profile_id=student_profile_id,
            user=scope["admin"],
            content=make_jpeg_bytes(),
        )

    monkeypatch.undo()
    second_attempt = await upload_sample(
        client_db,
        student_profile_id=student_profile_id,
        user=scope["admin"],
        content=make_jpeg_bytes(),
    )
    assert second_attempt.status_code == 201
    assert second_attempt.json()["status"] == "active"


async def test_replace_sample_promote_failure_leaves_old_sample_active(
    client_db: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed *replace* must never disturb the still-good old sample."""
    scope = await seed_enrollment_scope(client_db, db_session, suffix="fail-replace-promote")
    student_profile_id = scope["student_profile_1"]["id"]

    created = await upload_sample(
        client_db,
        student_profile_id=student_profile_id,
        user=scope["admin"],
        content=make_jpeg_bytes(),
    )
    assert created.status_code == 201
    original_sample_id = created.json()["id"]

    _break_promote(monkeypatch)
    with pytest.raises(OSError, match="simulated disk failure during promote"):
        await upload_sample(
            client_db,
            student_profile_id=student_profile_id,
            user=scope["admin"],
            content=make_png_bytes(),
            filename="new.png",
            content_type="image/png",
            method="put",
        )

    original_sample = await db_session.get(BiometricSample, original_sample_id)
    assert original_sample is not None
    assert original_sample.status is SampleStatus.ACTIVE

    other_samples = (
        (
            await db_session.execute(
                select(BiometricSample).where(BiometricSample.id != original_sample_id)
            )
        )
        .scalars()
        .all()
    )
    assert other_samples == []


async def test_replace_sample_retirement_failure_does_not_fail_the_replace_call(
    client_db: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Best-effort old-sample retirement.

    A quarantine failure must not undo the already-durable "new sample is
    active" result — see
    ``BiometricEnrollmentService._retire_old_sample_best_effort``'s
    docstring.
    """
    scope = await seed_enrollment_scope(client_db, db_session, suffix="fail-replace-retire")
    student_profile_id = scope["student_profile_1"]["id"]

    created = await upload_sample(
        client_db,
        student_profile_id=student_profile_id,
        user=scope["admin"],
        content=make_jpeg_bytes(),
    )
    assert created.status_code == 201
    old_sample_id = created.json()["id"]

    def _raise_quarantine(self: PrivateBiometricStorage, key: str) -> None:
        raise OSError("simulated disk failure during quarantine")

    monkeypatch.setattr(PrivateBiometricStorage, "quarantine", _raise_quarantine)

    replace_response = await upload_sample(
        client_db,
        student_profile_id=student_profile_id,
        user=scope["admin"],
        content=make_png_bytes(),
        filename="new.png",
        content_type="image/png",
        method="put",
    )
    # The replace call itself still succeeds — the new sample is durably
    # active regardless of whether the old file could be retired yet.
    assert replace_response.status_code == 200, replace_response.text
    body = replace_response.json()
    assert body["new_sample"]["status"] == "active"

    old_sample = await db_session.get(BiometricSample, old_sample_id)
    assert old_sample is not None
    # Retirement stalled at REPLACEMENT_PENDING — reconciliation-visible
    # drift, not a caller-facing error. See
    # test_phase5_stage2_reconciliation.py.
    assert old_sample.status is SampleStatus.REPLACEMENT_PENDING


async def test_finalize_deletion_resumes_after_quarantine_failure(
    client_db: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The deletion state machine resumes correctly after a mid-flight failure."""
    scope = await seed_enrollment_scope(client_db, db_session, suffix="fail-delete-resume")
    student_profile_id = scope["student_profile_1"]["id"]

    created = await upload_sample(
        client_db,
        student_profile_id=student_profile_id,
        user=scope["admin"],
        content=make_jpeg_bytes(),
    )
    assert created.status_code == 201
    sample_id = created.json()["id"]

    def _raise_quarantine(self: PrivateBiometricStorage, key: str) -> None:
        raise OSError("simulated disk failure during quarantine")

    monkeypatch.setattr(PrivateBiometricStorage, "quarantine", _raise_quarantine)
    with pytest.raises(OSError, match="simulated disk failure during quarantine"):
        await client_db.delete(
            f"/api/v1/biometric-enrollments/{student_profile_id}",
            headers=auth_headers(scope["admin"]),
        )

    sample_mid_flight = await db_session.get(BiometricSample, sample_id)
    assert sample_mid_flight is not None
    assert sample_mid_flight.status is SampleStatus.DELETION_PENDING

    monkeypatch.undo()
    retry = await client_db.post(
        f"/api/v1/biometric-enrollments/{student_profile_id}/deletion/finalize",
        headers=auth_headers(scope["admin"]),
    )
    assert retry.status_code == 200
    assert retry.json()["status"] == "deleted"

    sample_after = await db_session.get(BiometricSample, sample_id)
    assert sample_after is not None
    assert sample_after.status is SampleStatus.DELETED


async def test_finalize_deletion_drains_stalled_replacement_artifact_too(
    client_db: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deletion must drain *every* live sample, not just the current ACTIVE one.

    Reproduces exactly the drift shape left behind by
    ``test_replace_sample_retirement_failure_does_not_fail_the_replace_call``
    above: a REPLACEMENT_PENDING sample (old) left behind by a failed
    retirement, plus the new ACTIVE sample. Enrollment deletion must
    remove both — including purging the old sample's still-active file —
    before the enrollment itself is marked DELETED. Regression test for
    the bug where deletion only ever looked at the single current ACTIVE
    (or DELETION_PENDING/QUARANTINED) sample and immediately marked the
    enrollment DELETED regardless, leaving the REPLACEMENT_PENDING
    sample's row and file behind forever.
    """
    scope = await seed_enrollment_scope(client_db, db_session, suffix="delete-drains-stalled")
    student_profile_id = scope["student_profile_1"]["id"]

    created = await upload_sample(
        client_db,
        student_profile_id=student_profile_id,
        user=scope["admin"],
        content=make_jpeg_bytes(),
    )
    assert created.status_code == 201
    old_sample_id = created.json()["id"]

    def _raise_quarantine(self: PrivateBiometricStorage, key: str) -> None:
        raise OSError("simulated disk failure during quarantine")

    monkeypatch.setattr(PrivateBiometricStorage, "quarantine", _raise_quarantine)
    replace_response = await upload_sample(
        client_db,
        student_profile_id=student_profile_id,
        user=scope["admin"],
        content=make_png_bytes(),
        filename="new.png",
        content_type="image/png",
        method="put",
    )
    assert replace_response.status_code == 200, replace_response.text
    new_sample_id = replace_response.json()["new_sample"]["id"]

    old_sample = await db_session.get(BiometricSample, old_sample_id)
    assert old_sample is not None
    assert old_sample.status is SampleStatus.REPLACEMENT_PENDING
    old_sample_storage_key = old_sample.storage_key

    monkeypatch.undo()

    delete_response = await client_db.delete(
        f"/api/v1/biometric-enrollments/{student_profile_id}", headers=auth_headers(scope["admin"])
    )
    assert delete_response.status_code == 200, delete_response.text
    assert delete_response.json()["status"] == "deleted"

    old_sample_after = await db_session.get(BiometricSample, old_sample_id)
    new_sample_after = await db_session.get(BiometricSample, new_sample_id)
    assert old_sample_after is not None
    assert new_sample_after is not None
    assert old_sample_after.status is SampleStatus.DELETED
    assert new_sample_after.status is SampleStatus.DELETED
    assert old_sample_after.deleted_at is not None
    assert new_sample_after.deleted_at is not None

    storage = PrivateBiometricStorage(get_settings())
    assert storage.exists_active(old_sample_storage_key) is False
    assert storage.exists_quarantined(old_sample_storage_key) is False


async def test_create_sample_activation_failure_after_promote_leaves_no_falsely_active_sample(
    client_db: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A DB/audit failure *after* the file is already promoted.

    Unlike ``test_create_sample_promote_failure_leaves_no_falsely_active_sample``
    above (which breaks the filesystem rename itself), this breaks the
    *subsequent* transaction that marks the sample ACTIVE — the rename
    has already happened and is irreversible, so this specifically
    exercises ``_compensate_promoted_file_after_activation_failure``
    rather than ``_compensate_failed_promote``.
    """
    scope = await seed_enrollment_scope(client_db, db_session, suffix="fail-create-activation")
    student_profile_id = scope["student_profile_1"]["id"]

    promoted_keys = _capture_promoted_keys(monkeypatch)
    _break_audit_create_for_action(monkeypatch, action="biometric_enrollment.sample_create")

    with pytest.raises(RuntimeError, match="simulated database failure"):
        await upload_sample(
            client_db,
            student_profile_id=student_profile_id,
            user=scope["admin"],
            content=make_jpeg_bytes(),
        )
    assert len(promoted_keys) == 1

    remaining_samples = (
        (
            await db_session.execute(
                select(BiometricSample).where(
                    BiometricSample.status.in_([SampleStatus.ACTIVE, SampleStatus.PENDING])
                )
            )
        )
        .scalars()
        .all()
    )
    assert remaining_samples == []

    enrollment = (
        await db_session.execute(
            select(BiometricEnrollment).where(
                BiometricEnrollment.student_profile_id == student_profile_id
            )
        )
    ).scalar_one()
    assert enrollment.status is not EnrollmentStatus.ACTIVE

    storage = PrivateBiometricStorage(get_settings())
    assert storage.exists_active(promoted_keys[0]) is False
    assert storage.exists_quarantined(promoted_keys[0]) is False


async def test_create_sample_activation_failure_allows_retry_after_fix(
    client_db: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After a transient activation failure is fixed, the same student can enroll normally."""
    scope = await seed_enrollment_scope(client_db, db_session, suffix="fail-create-act-retry")
    student_profile_id = scope["student_profile_1"]["id"]

    _break_audit_create_for_action(monkeypatch, action="biometric_enrollment.sample_create")
    with pytest.raises(RuntimeError, match="simulated database failure"):
        await upload_sample(
            client_db,
            student_profile_id=student_profile_id,
            user=scope["admin"],
            content=make_jpeg_bytes(),
        )

    monkeypatch.undo()
    await db_session.refresh(scope["admin"])
    second_attempt = await upload_sample(
        client_db,
        student_profile_id=student_profile_id,
        user=scope["admin"],
        content=make_jpeg_bytes(),
    )
    assert second_attempt.status_code == 201
    assert second_attempt.json()["status"] == "active"


async def test_replace_sample_activation_failure_preserves_old_active_sample(
    client_db: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A DB/audit failure *after* the replacement file is already promoted.

    The old sample must remain the durable, unmodified ACTIVE sample —
    the whole activation transaction (old -> REPLACEMENT_PENDING, new ->
    ACTIVE, audit) rolled back together — and the new sample's now-
    orphaned promoted file/row must be cleaned up, exactly as if the
    replace attempt had never been made.
    """
    scope = await seed_enrollment_scope(client_db, db_session, suffix="fail-replace-activation")
    student_profile_id = scope["student_profile_1"]["id"]

    created = await upload_sample(
        client_db,
        student_profile_id=student_profile_id,
        user=scope["admin"],
        content=make_jpeg_bytes(),
    )
    assert created.status_code == 201
    original_sample_id = created.json()["id"]

    promoted_keys = _capture_promoted_keys(monkeypatch)
    _break_audit_create_for_action(monkeypatch, action="biometric_enrollment.sample_replace")

    with pytest.raises(RuntimeError, match="simulated database failure"):
        await upload_sample(
            client_db,
            student_profile_id=student_profile_id,
            user=scope["admin"],
            content=make_png_bytes(),
            filename="new.png",
            content_type="image/png",
            method="put",
        )
    assert len(promoted_keys) == 1

    original_sample = await db_session.get(BiometricSample, original_sample_id)
    assert original_sample is not None
    assert original_sample.status is SampleStatus.ACTIVE

    other_samples = (
        (
            await db_session.execute(
                select(BiometricSample).where(BiometricSample.id != original_sample_id)
            )
        )
        .scalars()
        .all()
    )
    assert other_samples == []

    storage = PrivateBiometricStorage(get_settings())
    assert storage.exists_active(promoted_keys[0]) is False
    assert storage.exists_quarantined(promoted_keys[0]) is False


async def test_bulk_activation_failure_after_promote_compensates_and_reports_row_failed(
    client_db: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bulk's analogue of the create/replace activation-failure tests above.

    The final-activate audit write fails after the row's file was
    already promoted; the row must be reported ``failed`` (batch
    ``success: false``, HTTP 200 — see
    test_phase5_stage2_bulk_zip_http.py's module docstring on this
    module's two distinct response shapes), no active/pending sample or
    falsely-active enrollment may remain, and the promoted file must be
    gone from active/ (moved out via quarantine, then purged).
    """
    scope = await seed_enrollment_scope(client_db, db_session, suffix="bulk-fail-activation")
    student_profile_id = scope["student_profile_1"]["id"]

    promoted_keys = _capture_promoted_keys(monkeypatch)
    _break_audit_create_for_action(monkeypatch, action="biometric_enrollment.sample_create")

    zip_bytes = _build_zip(
        [
            ("manifest.csv", _manifest_csv([(student_profile_id, "a.jpg")])),
            ("a.jpg", make_jpeg_bytes()),
        ]
    )
    response = await _post_zip(client_db, content=zip_bytes, user=scope["admin"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is False
    assert body["rows"][0]["outcome"] == "failed"
    assert body["rows"][0]["error_code"] == "ROW_EXECUTION_FAILED"
    assert len(promoted_keys) == 1

    remaining_samples = (
        (
            await db_session.execute(
                select(BiometricSample).where(
                    BiometricSample.status.in_([SampleStatus.ACTIVE, SampleStatus.PENDING])
                )
            )
        )
        .scalars()
        .all()
    )
    assert remaining_samples == []

    storage = PrivateBiometricStorage(get_settings())
    assert storage.exists_active(promoted_keys[0]) is False
    assert storage.exists_quarantined(promoted_keys[0]) is False


async def test_bulk_execution_failure_discards_staged_file_for_every_failed_row(
    client_db: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every row that fails during execution must have its staged file discarded.

    Regression test: ``_execute_rows``'s per-row exception handler used
    to log the failure and mark the row ``failed`` without ever touching
    the filesystem — leaking a staged file for each failed row. Two rows
    are used deliberately (plural "every failed row"), both broken via
    the same simulated promote failure.
    """
    scope = await seed_enrollment_scope(client_db, db_session, suffix="bulk-fail-discard-staged")
    student_profile_id_1 = scope["student_profile_1"]["id"]
    student_profile_id_2 = scope["student_profile_2"]["id"]

    captured_keys = _capture_new_keys(monkeypatch)
    _break_promote(monkeypatch)

    zip_bytes = _build_zip(
        [
            (
                "manifest.csv",
                _manifest_csv([(student_profile_id_1, "a.jpg"), (student_profile_id_2, "b.jpg")]),
            ),
            ("a.jpg", make_jpeg_bytes()),
            ("b.jpg", make_jpeg_bytes(color=(90, 90, 90))),
        ]
    )
    response = await _post_zip(client_db, content=zip_bytes, user=scope["admin"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is False
    assert body["failed_count"] == 2
    assert all(row["outcome"] == "failed" for row in body["rows"])

    # Every staging key generated while handling this request — one per
    # row, since row 0 fails during preparation would not reach here at
    # all; both rows failed during *execution*, after a staging key
    # already existed — must be gone from every zone afterward.
    assert captured_keys, "test setup must generate at least one storage key to check"
    storage = PrivateBiometricStorage(get_settings())
    for key in captured_keys:
        assert key not in storage.list_staged_keys()
        assert key not in storage.list_active_keys()
        assert key not in storage.list_quarantined_keys()

    remaining_samples = (
        (
            await db_session.execute(
                select(BiometricSample).where(
                    BiometricSample.status.in_([SampleStatus.ACTIVE, SampleStatus.PENDING])
                )
            )
        )
        .scalars()
        .all()
    )
    assert remaining_samples == []
