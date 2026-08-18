"""Enrollment/sample lifecycle orchestration for Phase 5 Stage 2.

Reuses Phase 2-4 patterns directly rather than inventing parallel
architecture:

- ``app.db.transaction.service_transaction`` — the exact commit/rollback
  boundary helper already used by ``AttendanceService``.
- ``app.modules.attendance.service.BlockedAuditWriter`` — imported and
  reused as-is (not re-implemented) for the one blocked-access case this
  module has (a non-owning student reading another student's enrollment;
  see ``BiometricEnrollmentService.get_detail``). Every other operation
  here is admin-only, gated by ``require_roles`` at the router — see
  this module's docstring section "Why there is no ownership-check
  dependency" below.
- ``app.modules.attendance.repository.AuditLogRepository`` — the
  existing, generic ``audit_logs`` table (``entity_type``/``entity_id``/
  ``event_metadata``) is reused directly; no new audit table is created.
- ``app.modules.auth.authorization`` is not imported directly (its one
  helper, ``require_own_profile``, raises immediately with no audit
  hook) — the blocked-audit write needs to happen *before* raising, so
  this module inlines the same one-line ownership check instead.

Why there is no ownership-check dependency (unlike attendance's
teacher-classroom scope check): docs/BIOMETRIC_DATA_POLICY.md (Stage 1,
Accepted) settles this — enrollment create/replace/delete is **admin
only**, with no teacher role in the picture at all. An admin's role
already grants them every student's scope, so there is no "right role,
wrong scope" case here the way there is for a teacher and a classroom.
The only object-level check in this whole module is the self-service
*read* path (a student may read only their own enrollment).

Compensating cleanup (see docs/BIOMETRIC_DATA_POLICY.md and
docs/HANDOVER_PHASE_5_STAGE_2.md for the full policy statement this
implements): a SQL transaction cannot roll back a filesystem rename.
Every method below that performs both a DB write and a filesystem
promote/quarantine operation follows the same order — stage, validate,
persist a PENDING row (its own commit), *then* attempt the filesystem
rename, with an explicit compensating DB cleanup (delete the PENDING
row, or revert a status flip) if the rename fails. If the compensating
cleanup itself fails, the failure is logged and left for
``app.modules.biometric_enrollment.reconciliation`` to report — never
silently swallowed, and never left presented to the caller as success.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.db.transaction import service_transaction
from app.modules.attendance.models import AuditOutcome
from app.modules.attendance.repository import AuditLogRepository
from app.modules.attendance.service import BlockedAuditWriter
from app.modules.biometric_enrollment.errors import (
    EnrollmentAlreadyActiveError,
    EnrollmentDeletionPendingError,
    EnrollmentDuplicateContentError,
    EnrollmentImageTooLargeError,
    EnrollmentInactiveStudentError,
    EnrollmentNoActiveSampleError,
    EnrollmentNotFoundError,
)
from app.modules.biometric_enrollment.image_validation import ValidatedImage, validate_image_file
from app.modules.biometric_enrollment.models import (
    BiometricEnrollment,
    BiometricSample,
    EnrollmentStatus,
    SampleStatus,
)
from app.modules.biometric_enrollment.repository import (
    BiometricEnrollmentRepository,
    BiometricSampleRepository,
)
from app.modules.biometric_enrollment.schemas import (
    BiometricEnrollmentDetailRead,
    BiometricEnrollmentRead,
    BiometricSampleRead,
    BiometricSampleReplaceResult,
)
from app.modules.biometric_enrollment.storage import (
    PrivateBiometricStorage,
    StorageCapExceededError,
)
from app.modules.profiles.errors import StudentProfileNotFoundError
from app.modules.profiles.models import StudentProfile
from app.modules.profiles.repository import StudentProfileRepository
from app.modules.users.models import User, UserRole

logger = structlog.get_logger(__name__)

ACTION_ENROLLMENT_SAMPLE_CREATE = "biometric_enrollment.sample_create"
ACTION_ENROLLMENT_SAMPLE_REPLACE = "biometric_enrollment.sample_replace"
ACTION_ENROLLMENT_DELETION_REQUEST = "biometric_enrollment.deletion_request"
ACTION_ENROLLMENT_DELETION_FINALIZE = "biometric_enrollment.deletion_finalize"
ACTION_ENROLLMENT_READ = "biometric_enrollment.read"

_ENTITY_TYPE_ENROLLMENT = "biometric_enrollment"
_ENTITY_TYPE_SAMPLE = "biometric_sample"

_REASON_NOT_OWN_PROFILE = "not_own_student_profile"

_FILENAME_SAFE_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_FILENAME_LENGTH = 128


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _sanitize_filename(original: str | None) -> str | None:
    """Reduce a client-supplied filename to safe, storable *metadata* only.

    Never used to build a filesystem path (see
    app/modules/biometric_enrollment/storage.py — storage keys are always
    server-generated). This only strips it down so it is safe to display
    back to an admin later: no path separators, no leading dot-segments,
    bounded length.
    """
    if not original:
        return None
    base = original.replace("\\", "/").rsplit("/", 1)[-1].strip()
    base = base.lstrip(".")
    cleaned = _FILENAME_SAFE_PATTERN.sub("_", base).strip("_")
    if not cleaned:
        return None
    return cleaned[:_MAX_FILENAME_LENGTH]


class BiometricEnrollmentService:
    """Transaction-owned, authorization-checked enrollment lifecycle."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        storage: PrivateBiometricStorage | None = None,
        blocked_audit_writer: BlockedAuditWriter | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._storage = storage or PrivateBiometricStorage(self._settings)
        self._enrollments = BiometricEnrollmentRepository(session)
        self._samples = BiometricSampleRepository(session)
        self._students = StudentProfileRepository(session)
        self._audit_logs = AuditLogRepository(session)
        self._blocked_audit_writer = blocked_audit_writer or BlockedAuditWriter.from_session(
            session
        )

    # --- reads -------------------------------------------------------------

    async def get_detail(
        self,
        *,
        current_user: User,
        student_profile_id: uuid.UUID,
        request_id: str | None = None,
    ) -> BiometricEnrollmentDetailRead:
        """Admin: any student. Student: only their own profile (else concealed 404)."""
        profile = await self._students.get_by_id(student_profile_id)
        if profile is None:
            raise StudentProfileNotFoundError()

        if current_user.role is not UserRole.ADMIN:
            if profile.user_id != current_user.id:
                await self._write_blocked_read_audit(
                    current_user=current_user,
                    reason_code=_REASON_NOT_OWN_PROFILE,
                    request_id=request_id,
                )
                raise StudentProfileNotFoundError()
            if not profile.is_active:
                raise StudentProfileNotFoundError()

        enrollment = await self._enrollments.get_by_student_profile_id(student_profile_id)
        if enrollment is None:
            raise EnrollmentNotFoundError()
        samples = await self._samples.list_for_enrollment(enrollment.id)
        return BiometricEnrollmentDetailRead(
            enrollment=BiometricEnrollmentRead.model_validate(enrollment),
            samples=[BiometricSampleRead.model_validate(sample) for sample in samples],
        )

    async def _write_blocked_read_audit(
        self, *, current_user: User, reason_code: str, request_id: str | None
    ) -> None:
        try:
            await self._blocked_audit_writer.write(
                actor_user_id=current_user.id,
                action=ACTION_ENROLLMENT_READ,
                entity_type=_ENTITY_TYPE_ENROLLMENT,
                classroom_id=None,
                subject_id=None,
                request_id=request_id,
                reason_code=reason_code,
                attempted_action=ACTION_ENROLLMENT_READ,
            )
        except Exception as exc:
            # The blocked-audit write deliberately uses its own
            # independent session/transaction (BlockedAuditWriter, reused
            # as-is from app.modules.attendance.service) so a failure
            # here never touches the main session. That failure must
            # never replace or suppress the concealed-404 the caller is
            # about to raise regardless — the request is still rejected
            # either way, just without a durable audit row this one time.
            logger.error(
                "blocked_audit_write_failed",
                reason_code=reason_code,
                request_id=request_id,
                exc_type=type(exc).__name__,
            )
        else:
            logger.warning("biometric_enrollment_read_blocked", reason_code=reason_code)

    # --- create --------------------------------------------------------------

    async def create_sample(
        self,
        *,
        current_user: User,
        student_profile_id: uuid.UUID,
        chunks: AsyncIterator[bytes],
        declared_content_type: str | None,
        original_filename: str | None,
        request_id: str | None = None,
    ) -> BiometricSampleRead:
        profile = await self._resolve_active_student(student_profile_id)
        enrollment = await self._get_or_create_enrollment(
            student_profile_id=profile.id, actor_id=current_user.id
        )
        if enrollment.status is EnrollmentStatus.DELETION_PENDING:
            raise EnrollmentDeletionPendingError()

        existing_active = await self._samples.get_active_for_enrollment(enrollment.id)
        if existing_active is not None:
            raise EnrollmentAlreadyActiveError()

        key, validated = await self._stage_and_validate(
            chunks=chunks, declared_content_type=declared_content_type
        )
        try:
            sample = await self._create_pending_row(
                enrollment_id=enrollment.id,
                key=key,
                validated=validated,
                original_filename=original_filename,
                actor_id=current_user.id,
                previous_sample_id=None,
            )
            sample_id = sample.id
        except Exception:
            # Deliberately broad: unlike _stage_and_validate's image-decode
            # step, _create_pending_row can also raise a genuine database
            # error (e.g. an IntegrityError from the partial unique index
            # racing a concurrent duplicate), not only an EnrollmentError.
            # Any of those must still discard the now-orphaned staged
            # file — the original exception is always re-raised unchanged
            # immediately after, never swallowed.
            self._storage.discard_staged(key)
            raise

        try:
            self._storage.promote(key)
        except OSError:
            await self._compensate_failed_promote(sample)
            raise

        try:
            async with service_transaction(self._session):
                await self._samples.mark_active(sample, promoted_at=_utcnow())
                await self._enrollments.set_status(enrollment, status=EnrollmentStatus.ACTIVE)
                await self._audit_logs.create(
                    actor_user_id=current_user.id,
                    action=ACTION_ENROLLMENT_SAMPLE_CREATE,
                    outcome=AuditOutcome.SUCCESS,
                    entity_type=_ENTITY_TYPE_SAMPLE,
                    entity_id=sample_id,
                    request_id=request_id,
                    event_metadata={
                        "student_profile_id": str(student_profile_id),
                        "enrollment_id": str(enrollment.id),
                        "sha256_hash": validated.sha256_hash,
                        "content_type": validated.content_type,
                        "file_size_bytes": validated.size_bytes,
                    },
                )
                # ``updated_at`` is generated by the UPDATE above and is
                # therefore expired by SQLAlchemy. Refresh and serialize
                # while async database I/O is still explicit; serializing
                # the ORM row after commit would attempt an implicit lazy
                # load and raise MissingGreenlet under asyncpg.
                await self._session.refresh(sample)
                response = BiometricSampleRead.model_validate(sample)
        except Exception:
            # The file was already promoted (an irreversible rename) but
            # the transaction that would mark it ACTIVE rolled back — see
            # ``_compensate_promoted_file_after_activation_failure``'s
            # docstring for why this is a distinct case from a failed
            # *promote* itself, handled above.
            await self._compensate_promoted_file_after_activation_failure(key, sample_id)
            raise
        return response

    # --- replace ---------------------------------------------------------------

    async def replace_sample(
        self,
        *,
        current_user: User,
        student_profile_id: uuid.UUID,
        chunks: AsyncIterator[bytes],
        declared_content_type: str | None,
        original_filename: str | None,
        request_id: str | None = None,
    ) -> BiometricSampleReplaceResult:
        profile = await self._resolve_active_student(student_profile_id)
        enrollment = await self._enrollments.get_by_student_profile_id(profile.id)
        if enrollment is None:
            raise EnrollmentNoActiveSampleError()
        if enrollment.status is EnrollmentStatus.DELETION_PENDING:
            raise EnrollmentDeletionPendingError()
        enrollment_id = enrollment.id

        old_sample = await self._samples.get_active_for_enrollment(enrollment_id)
        if old_sample is None:
            raise EnrollmentNoActiveSampleError()
        old_sample_id = old_sample.id

        key, validated = await self._stage_and_validate(
            chunks=chunks, declared_content_type=declared_content_type
        )
        try:
            new_sample = await self._create_pending_row(
                enrollment_id=enrollment_id,
                key=key,
                validated=validated,
                original_filename=original_filename,
                actor_id=current_user.id,
                previous_sample_id=old_sample_id,
            )
            new_sample_id = new_sample.id
        except Exception:
            # Same rationale as create_sample's identical block above:
            # _create_pending_row can raise a real database error, not
            # only an EnrollmentError, and any of them must still discard
            # the orphaned staged file before the original exception
            # propagates unchanged.
            self._storage.discard_staged(key)
            raise

        try:
            self._storage.promote(key)
        except OSError:
            # The old sample has not been touched yet at this point (see
            # ordering below) — compensate only the orphaned new row.
            await self._compensate_failed_promote(new_sample)
            raise

        try:
            async with service_transaction(self._session):
                # Order matters: flip the old sample off ACTIVE *before*
                # marking the new one ACTIVE, so the partial unique index
                # (one ACTIVE sample per enrollment) is never transiently
                # violated within this transaction.
                await self._samples.mark_replacement_pending(old_sample)
                await self._samples.mark_active(new_sample, promoted_at=_utcnow())
                await self._audit_logs.create(
                    actor_user_id=current_user.id,
                    action=ACTION_ENROLLMENT_SAMPLE_REPLACE,
                    outcome=AuditOutcome.SUCCESS,
                    entity_type=_ENTITY_TYPE_SAMPLE,
                    entity_id=new_sample_id,
                    request_id=request_id,
                    event_metadata={
                        "student_profile_id": str(student_profile_id),
                        "enrollment_id": str(enrollment_id),
                        "previous_sample_id": str(old_sample_id),
                        "sha256_hash": validated.sha256_hash,
                    },
                )
                await self._session.refresh(new_sample)
                new_sample_response = BiometricSampleRead.model_validate(new_sample)
        except Exception:
            # This whole transaction rolled back together, so the old
            # sample's committed DB state is untouched — it is still the
            # durable ACTIVE sample, exactly as if this replace attempt
            # had never happened. Only the new sample's now-orphaned
            # promoted file and PENDING row need cleanup.
            await self._compensate_promoted_file_after_activation_failure(key, new_sample_id)
            raise

        # The replace operation's core guarantee (the student now has a
        # new active sample) is already durable at this point. Retiring
        # the old file is best-effort from here — a failure is logged and
        # left as reconciliation-visible drift (a REPLACEMENT_PENDING
        # sample whose file was never quarantined/purged), not surfaced
        # as an error on this call. See this module's docstring and
        # docs/HANDOVER_PHASE_5_STAGE_2.md's "known risks".
        await self._retire_old_sample_best_effort(old_sample, request_id=request_id)

        return BiometricSampleReplaceResult(
            enrollment_id=enrollment_id,
            previous_sample_id=old_sample_id,
            new_sample=new_sample_response,
        )

    async def _retire_old_sample_best_effort(
        self, sample: BiometricSample, *, request_id: str | None
    ) -> None:
        sample_id = sample.id
        try:
            if self._storage.exists_active(sample.storage_key):
                self._storage.quarantine(sample.storage_key)
            async with service_transaction(self._session):
                await self._samples.mark_quarantined(sample, quarantined_at=_utcnow())
            self._storage.purge_quarantined(sample.storage_key)
            async with service_transaction(self._session):
                await self._samples.mark_deleted(sample, deleted_at=_utcnow())
        except Exception as exc:
            # Intentionally swallowed, not re-raised: the caller already
            # has a durable, successful result (the new sample is
            # ACTIVE) by the time this runs — a failure here must not
            # turn that into a caller-visible error. Logged so it is
            # never silent, and left as reconciliation-visible drift
            # (see this class's replace_sample docstring above).
            logger.error(
                "biometric_sample_retirement_failed",
                sample_id=str(sample_id),
                request_id=request_id,
                exc_type=type(exc).__name__,
            )

    # --- deletion (request + idempotent finalize/retry) ------------------------

    async def request_deletion(
        self, *, current_user: User, student_profile_id: uuid.UUID, request_id: str | None = None
    ) -> BiometricEnrollmentRead:
        enrollment = await self._resolve_enrollment_or_404(student_profile_id)
        result = await self._advance_deletion(
            enrollment,
            actor_user_id=current_user.id,
            request_id=request_id,
            action=ACTION_ENROLLMENT_DELETION_REQUEST,
        )
        return BiometricEnrollmentRead.model_validate(result)

    async def finalize_deletion(
        self, *, current_user: User, student_profile_id: uuid.UUID, request_id: str | None = None
    ) -> BiometricEnrollmentRead:
        """Idempotent retry: safe to call again after a partial deletion attempt."""
        enrollment = await self._resolve_enrollment_or_404(student_profile_id)
        result = await self._advance_deletion(
            enrollment,
            actor_user_id=current_user.id,
            request_id=request_id,
            action=ACTION_ENROLLMENT_DELETION_FINALIZE,
        )
        return BiometricEnrollmentRead.model_validate(result)

    async def _advance_deletion(
        self,
        enrollment: BiometricEnrollment,
        *,
        actor_user_id: uuid.UUID,
        request_id: str | None,
        action: str,
    ) -> BiometricEnrollment:
        """Resumable deletion state machine — safe to call at any stage.

        Every non-``DELETED`` sample belonging to this enrollment is
        drained — not only the current ``ACTIVE`` one. This matters
        because an enrollment can end up with more than one live sample
        at once (e.g. an ``ACTIVE`` sample plus a stalled
        ``REPLACEMENT_PENDING`` one left behind by a failed retirement —
        see ``_retire_old_sample_best_effort``); every one of ``PENDING``,
        ``ACTIVE``, ``REPLACEMENT_PENDING``, ``DELETION_PENDING`` and
        ``QUARANTINED`` is cascaded through its remaining lifecycle
        (using the ORM object's live ``status``, which every helper below
        mutates in place) before the enrollment itself is ever marked
        ``DELETED``. The enrollment is never marked ``DELETED`` while any
        live sample — or its underlying file — still exists, and an
        enrollment already recorded as ``DELETED`` is not treated as
        "nothing to do" if live sample drift is later discovered (e.g.
        left behind by an earlier partial failure of this very method) —
        that drift is still drained here before returning.
        """
        live_samples = await self._samples.list_live_for_enrollment(enrollment.id)

        if enrollment.status is EnrollmentStatus.DELETED and not live_samples:
            return enrollment

        if enrollment.status is not EnrollmentStatus.DELETION_PENDING:
            async with service_transaction(self._session):
                await self._enrollments.mark_deletion_requested(
                    enrollment, requested_by_user_id=actor_user_id, requested_at=_utcnow()
                )

        processed_sample_ids: list[uuid.UUID] = []
        for sample in live_samples:
            await self._advance_sample_deletion(sample)
            processed_sample_ids.append(sample.id)

        remaining_live = await self._samples.list_live_for_enrollment(enrollment.id)
        if remaining_live:
            # Could not fully drain every live sample this call (a prior
            # step above would have raised on a genuine failure, but a
            # defensive re-check costs nothing) — leave the enrollment in
            # DELETION_PENDING for a future retry rather than falsely
            # marking it DELETED while drift remains.
            await self._session.refresh(enrollment)
            return enrollment

        async with service_transaction(self._session):
            await self._enrollments.set_status(enrollment, status=EnrollmentStatus.DELETED)
            await self._audit_logs.create(
                actor_user_id=actor_user_id,
                action=action,
                outcome=AuditOutcome.SUCCESS,
                entity_type=_ENTITY_TYPE_ENROLLMENT,
                entity_id=enrollment.id,
                request_id=request_id,
                event_metadata={
                    "student_profile_id": str(enrollment.student_profile_id),
                    "sample_ids": [str(sample_id) for sample_id in processed_sample_ids],
                },
            )
            await self._session.refresh(enrollment)
        return enrollment

    async def _advance_sample_deletion(self, sample: BiometricSample) -> None:
        """Cascade one live sample through every remaining removal step.

        Safe to call at any point in the sample's own state machine —
        mirrors ``_advance_deletion``'s resumability contract above. A
        ``PENDING`` sample (never promoted, so it has no active file —
        only possible here if a crash landed between committing that row
        and promoting its file) is hard-deleted directly, matching
        ``_compensate_failed_promote``'s established "still-PENDING row"
        contract. Every other live status funnels through the same
        deletion-pending -> quarantine -> purge -> deleted sequence
        ``replace_sample``'s best-effort retirement also uses.
        """
        if sample.status is SampleStatus.PENDING:
            self._storage.discard_staged(sample.storage_key)
            async with service_transaction(self._session):
                await self._samples.delete_row(sample)
            return

        if sample.status in (SampleStatus.ACTIVE, SampleStatus.REPLACEMENT_PENDING):
            async with service_transaction(self._session):
                await self._samples.mark_deletion_pending(sample)
        if sample.status is SampleStatus.DELETION_PENDING:
            if self._storage.exists_active(sample.storage_key):
                self._storage.quarantine(sample.storage_key)
            async with service_transaction(self._session):
                await self._samples.mark_quarantined(sample, quarantined_at=_utcnow())
        if sample.status is SampleStatus.QUARANTINED:
            self._storage.purge_quarantined(sample.storage_key)
            async with service_transaction(self._session):
                await self._samples.mark_deleted(sample, deleted_at=_utcnow())

    # --- shared helpers ----------------------------------------------------

    async def _resolve_active_student(self, student_profile_id: uuid.UUID) -> StudentProfile:
        profile = await self._students.get_by_id(student_profile_id)
        if profile is None:
            raise StudentProfileNotFoundError()
        if not profile.is_active:
            raise EnrollmentInactiveStudentError()
        return profile

    async def _resolve_enrollment_or_404(
        self, student_profile_id: uuid.UUID
    ) -> BiometricEnrollment:
        if await self._students.get_by_id(student_profile_id) is None:
            raise StudentProfileNotFoundError()
        enrollment = await self._enrollments.get_by_student_profile_id(student_profile_id)
        if enrollment is None:
            raise EnrollmentNotFoundError()
        return enrollment

    async def _get_or_create_enrollment(
        self, *, student_profile_id: uuid.UUID, actor_id: uuid.UUID
    ) -> BiometricEnrollment:
        enrollment = await self._enrollments.get_by_student_profile_id(student_profile_id)
        if enrollment is not None:
            return enrollment
        async with service_transaction(self._session):
            enrollment = await self._enrollments.create(
                student_profile_id=student_profile_id, created_by_user_id=actor_id
            )
        return enrollment

    async def _stage_and_validate(
        self, *, chunks: AsyncIterator[bytes], declared_content_type: str | None
    ) -> tuple[str, ValidatedImage]:
        key = self._storage.new_key()
        try:
            await self._storage.write_staged(
                key, chunks, max_bytes=self._settings.MAX_ENROLLMENT_IMAGE_BYTES
            )
        except StorageCapExceededError as exc:
            raise EnrollmentImageTooLargeError(self._settings.MAX_ENROLLMENT_IMAGE_BYTES) from exc

        try:
            validated = validate_image_file(
                self._storage.staging_path(key),
                settings=self._settings,
                declared_content_type=declared_content_type,
            )
        except AppError:
            # validate_image_file's own contract (see
            # image_validation.py's module docstring) is to never raise
            # anything other than an AppError subclass — narrowed here
            # (rather than a blind `except Exception`) precisely because
            # that contract makes a broader catch unnecessary. Cleanup-
            # then-reraise: the staged file must not survive a rejected
            # image, and the original error is always re-raised unchanged.
            self._storage.discard_staged(key)
            raise
        return key, validated

    async def _create_pending_row(
        self,
        *,
        enrollment_id: uuid.UUID,
        key: str,
        validated: ValidatedImage,
        original_filename: str | None,
        actor_id: uuid.UUID,
        previous_sample_id: uuid.UUID | None,
    ) -> BiometricSample:
        async with service_transaction(self._session):
            duplicate = await self._samples.find_duplicate_content(
                enrollment_id=enrollment_id, sha256_hash=validated.sha256_hash
            )
            if duplicate is not None:
                raise EnrollmentDuplicateContentError()
            sample = await self._samples.create_pending(
                enrollment_id=enrollment_id,
                storage_key=key,
                original_filename=_sanitize_filename(original_filename),
                content_type=validated.content_type,
                file_size_bytes=validated.size_bytes,
                width_px=validated.width_px,
                height_px=validated.height_px,
                sha256_hash=validated.sha256_hash,
                created_by_user_id=actor_id,
                previous_sample_id=previous_sample_id,
            )
        return sample

    async def _compensate_failed_promote(self, sample: BiometricSample) -> None:
        """A staged-to-active rename failed: remove the now-orphaned PENDING row.

        Never leaves the student with a falsely active enrollment. If
        this compensating delete itself fails, the row is left PENDING
        with no active/quarantined file behind it — exactly the drift
        shape ``app.modules.biometric_enrollment.reconciliation`` is
        built to detect.
        """
        sample_id = sample.id
        try:
            async with service_transaction(self._session):
                await self._samples.delete_row(sample)
        except Exception as exc:
            # Intentionally swallowed: every caller of this method is
            # about to `raise` the original OSError from the failed
            # promote regardless of what happens here — letting a
            # secondary failure from this cleanup attempt propagate
            # instead would replace that original, more useful error.
            # Logged so a failed compensation is never silent.
            logger.error(
                "biometric_sample_promote_compensation_failed",
                sample_id=str(sample_id),
                exc_type=type(exc).__name__,
            )

    async def _compensate_promoted_file_after_activation_failure(
        self, key: str, sample_id: uuid.UUID
    ) -> None:
        """The rename succeeded, but the transaction that would mark it ACTIVE did not.

        Distinct from ``_compensate_failed_promote`` above: that method
        only ever has to clean up a still-PENDING *row* — the filesystem
        rename itself never happened. Here, ``self._storage.promote(key)``
        already completed (an irreversible ``os.replace``), and only
        *afterward* did the DB transaction that marks the sample ACTIVE
        (and, for a fresh enrollment, flips the enrollment to ACTIVE and
        writes the audit row) fail and roll back. That leaves a real file
        sitting in the active/ zone with no corresponding ACTIVE database
        row — it must be moved out of active/ (via quarantine, the only
        sanctioned exit from that zone — see
        app/modules/biometric_enrollment/storage.py) and purged, and the
        now-meaningless row removed, exactly as if this create/replace
        attempt had never been made. The current, true row state is
        re-read from the database by a UUID captured before the risky
        transaction, since rollback may expire every attribute on the
        in-memory ORM object. Never
        re-raises — as with ``_compensate_failed_promote``, every caller
        is about to re-raise the original failure regardless; a
        secondary failure here is logged for
        ``app.modules.biometric_enrollment.reconciliation`` to report
        instead of replacing the original, more useful error.
        """
        try:
            if self._storage.exists_active(key):
                self._storage.quarantine(key)
                self._storage.purge_quarantined(key)
            async with service_transaction(self._session):
                fresh = await self._samples.get_by_id(sample_id)
                if fresh is not None and fresh.status is SampleStatus.PENDING:
                    await self._samples.delete_row(fresh)
        except Exception as exc:
            logger.error(
                "biometric_sample_post_promote_activation_compensation_failed",
                sample_id=str(sample_id),
                exc_type=type(exc).__name__,
            )
