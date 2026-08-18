"""Repositories for biometric enrollment and sample data access.

Follows ``app.modules.attendance.repository``'s conventions: thin,
single-aggregate data access; callers own the transaction boundary (only
``flush()``/``refresh()`` here, never ``commit()``); no ORM relationship
is lazy-loaded under asyncpg (every read is an explicit ``select`` or a
plain ``session.get()`` by primary key).
"""

from __future__ import annotations

import builtins
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.biometric_enrollment.models import (
    BiometricEnrollment,
    BiometricSample,
    EnrollmentStatus,
    RecognitionProcessingState,
    SampleStatus,
)


class BiometricEnrollmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, enrollment_id: uuid.UUID) -> BiometricEnrollment | None:
        return await self._session.get(BiometricEnrollment, enrollment_id)

    async def get_by_student_profile_id(
        self, student_profile_id: uuid.UUID
    ) -> BiometricEnrollment | None:
        stmt = select(BiometricEnrollment).where(
            BiometricEnrollment.student_profile_id == student_profile_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self, *, student_profile_id: uuid.UUID, created_by_user_id: uuid.UUID
    ) -> BiometricEnrollment:
        enrollment = BiometricEnrollment(
            student_profile_id=student_profile_id,
            status=EnrollmentStatus.PENDING,
            created_by_user_id=created_by_user_id,
        )
        self._session.add(enrollment)
        await self._session.flush()
        await self._session.refresh(enrollment)
        return enrollment

    async def set_status(
        self, enrollment: BiometricEnrollment, *, status: EnrollmentStatus
    ) -> BiometricEnrollment:
        enrollment.status = status
        await self._session.flush()
        return enrollment

    async def mark_deletion_requested(
        self,
        enrollment: BiometricEnrollment,
        *,
        requested_by_user_id: uuid.UUID,
        requested_at: datetime,
    ) -> BiometricEnrollment:
        enrollment.status = EnrollmentStatus.DELETION_PENDING
        enrollment.deletion_requested_by_user_id = requested_by_user_id
        enrollment.deletion_requested_at = requested_at
        await self._session.flush()
        return enrollment

    async def list_all(
        self, *, limit: int = 100, offset: int = 0
    ) -> builtins.list[BiometricEnrollment]:
        """Used only by the reconciliation report — not exposed via any API."""
        stmt = (
            select(BiometricEnrollment)
            .order_by(BiometricEnrollment.created_at, BiometricEnrollment.id)
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class BiometricSampleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, sample_id: uuid.UUID) -> BiometricSample | None:
        return await self._session.get(BiometricSample, sample_id)

    async def get_active_for_enrollment(self, enrollment_id: uuid.UUID) -> BiometricSample | None:
        stmt = select(BiometricSample).where(
            BiometricSample.enrollment_id == enrollment_id,
            BiometricSample.status == SampleStatus.ACTIVE,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_storage_key(self, storage_key: str) -> BiometricSample | None:
        stmt = select(BiometricSample).where(BiometricSample.storage_key == storage_key)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_duplicate_content(
        self, *, enrollment_id: uuid.UUID, sha256_hash: str
    ) -> BiometricSample | None:
        """Any non-DELETED sample for this enrollment with identical content."""
        stmt = select(BiometricSample).where(
            BiometricSample.enrollment_id == enrollment_id,
            BiometricSample.sha256_hash == sha256_hash,
            BiometricSample.status != SampleStatus.DELETED,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_enrollment(self, enrollment_id: uuid.UUID) -> builtins.list[BiometricSample]:
        stmt = (
            select(BiometricSample)
            .where(BiometricSample.enrollment_id == enrollment_id)
            .order_by(BiometricSample.created_at.desc(), BiometricSample.id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_live_for_enrollment(
        self, enrollment_id: uuid.UUID
    ) -> builtins.list[BiometricSample]:
        """Every sample not yet ``DELETED`` for this enrollment.

        Deletion/finalization input (see
        ``BiometricEnrollmentService._advance_deletion``): an enrollment
        may end up with more than one live sample at once (e.g. an
        ``ACTIVE`` sample plus a ``REPLACEMENT_PENDING`` one left behind
        by a stalled retirement — see ``_retire_old_sample_best_effort``)
        and every one of them — ``PENDING``, ``ACTIVE``,
        ``REPLACEMENT_PENDING``, ``DELETION_PENDING``, ``QUARANTINED`` —
        must be drained before the enrollment itself is marked
        ``DELETED``. Ordered oldest-first so drift from an older,
        stalled operation is processed before the current one.
        """
        stmt = (
            select(BiometricSample)
            .where(
                BiometricSample.enrollment_id == enrollment_id,
                BiometricSample.status != SampleStatus.DELETED,
            )
            .order_by(BiometricSample.created_at, BiometricSample.id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create_pending(
        self,
        *,
        enrollment_id: uuid.UUID,
        storage_key: str,
        original_filename: str | None,
        content_type: str,
        file_size_bytes: int,
        width_px: int,
        height_px: int,
        sha256_hash: str,
        created_by_user_id: uuid.UUID,
        previous_sample_id: uuid.UUID | None = None,
    ) -> BiometricSample:
        sample = BiometricSample(
            enrollment_id=enrollment_id,
            storage_key=storage_key,
            original_filename=original_filename,
            content_type=content_type,
            file_size_bytes=file_size_bytes,
            width_px=width_px,
            height_px=height_px,
            sha256_hash=sha256_hash,
            status=SampleStatus.PENDING,
            processing_state=RecognitionProcessingState.PENDING_PROCESSING,
            created_by_user_id=created_by_user_id,
            previous_sample_id=previous_sample_id,
        )
        self._session.add(sample)
        await self._session.flush()
        await self._session.refresh(sample)
        return sample

    async def mark_active(
        self, sample: BiometricSample, *, promoted_at: datetime
    ) -> BiometricSample:
        sample.status = SampleStatus.ACTIVE
        sample.promoted_at = promoted_at
        await self._session.flush()
        return sample

    async def mark_replacement_pending(self, sample: BiometricSample) -> BiometricSample:
        sample.status = SampleStatus.REPLACEMENT_PENDING
        await self._session.flush()
        return sample

    async def mark_deletion_pending(self, sample: BiometricSample) -> BiometricSample:
        sample.status = SampleStatus.DELETION_PENDING
        await self._session.flush()
        return sample

    async def mark_quarantined(
        self, sample: BiometricSample, *, quarantined_at: datetime
    ) -> BiometricSample:
        sample.status = SampleStatus.QUARANTINED
        sample.quarantined_at = quarantined_at
        await self._session.flush()
        return sample

    async def mark_deleted(
        self, sample: BiometricSample, *, deleted_at: datetime
    ) -> BiometricSample:
        sample.status = SampleStatus.DELETED
        sample.deleted_at = deleted_at
        await self._session.flush()
        return sample

    async def delete_row(self, sample: BiometricSample) -> None:
        """Hard-delete a still-PENDING row only (compensating cleanup path).

        Never used on a promoted (``ACTIVE`` or later) sample — see
        app/modules/biometric_enrollment/service.py's docstring on why
        DB history is otherwise preserved (soft ``DELETED`` state, not a
        row deletion).
        """
        await self._session.delete(sample)
        await self._session.flush()

    async def list_stale_pending(self, *, older_than: datetime) -> builtins.list[BiometricSample]:
        """PENDING samples older than ``older_than`` — reconciliation input only."""
        stmt = select(BiometricSample).where(
            BiometricSample.status == SampleStatus.PENDING,
            BiometricSample.created_at < older_than,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_status(self, status: SampleStatus) -> builtins.list[BiometricSample]:
        """All samples in a given status — reconciliation input only."""
        stmt = select(BiometricSample).where(BiometricSample.status == status)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # --- Phase 5 Stage 3: recognition-processing lifecycle -----------------
    # Added on top of Stage 2's repository (never modifying the methods
    # above) — see app/modules/face_recognition/processing_service.py,
    # the only caller of everything below.

    async def list_active_pending_processing(self, *, limit: int) -> builtins.list[BiometricSample]:
        """``ACTIVE`` samples still awaiting Stage 3 processing, oldest first.

        Scoped to ``status == ACTIVE`` deliberately: a ``PENDING``
        sample may still be discarded by the Stage 2 staging-timeout
        reconciliation before ever being promoted, and a
        ``DELETION_PENDING``/``QUARANTINED``/``DELETED`` sample is being
        (or has been) removed — neither is a sample Stage 3 should ever
        spend inference time processing. Bounded by ``limit`` (never an
        unbounded query) — see
        ``Settings.FACE_PROCESSING_BATCH_LIMIT``.
        """
        stmt = (
            select(BiometricSample)
            .where(
                BiometricSample.status == SampleStatus.ACTIVE,
                BiometricSample.processing_state == RecognitionProcessingState.PENDING_PROCESSING,
            )
            .order_by(BiometricSample.created_at, BiometricSample.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_processing_started(
        self, sample: BiometricSample, *, started_at: datetime
    ) -> BiometricSample:
        sample.processing_started_at = started_at
        await self._session.flush()
        return sample

    async def mark_processed(
        self, sample: BiometricSample, *, completed_at: datetime
    ) -> BiometricSample:
        sample.processing_state = RecognitionProcessingState.PROCESSED
        sample.processing_completed_at = completed_at
        sample.processing_failure_reason_code = None
        await self._session.flush()
        return sample

    async def mark_processing_failed(
        self, sample: BiometricSample, *, completed_at: datetime, reason_code: str
    ) -> BiometricSample:
        sample.processing_state = RecognitionProcessingState.PROCESSING_FAILED
        sample.processing_completed_at = completed_at
        sample.processing_failure_reason_code = reason_code
        await self._session.flush()
        return sample
