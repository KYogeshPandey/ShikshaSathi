"""Bulk ZIP biometric enrollment orchestration.

Atomicity contract (see ``BulkEnrollmentResult``'s docstring in
app/modules/biometric_enrollment/schemas.py for the client-facing
summary):

1. **Validation phase** — ``app.modules.biometric_enrollment.zip_security
   .validate_archive`` fully validates the archive's shape (manifest,
   path safety, size/ratio/count bounds) with **zero** side effects. This
   service then extends that with a second, still-zero-side-effect pass:
   every referenced member is streamed to its own staging file and run
   through the same Pillow-based decode/format/dimension checks single
   enrollment uses, and every row's student is resolved (must exist, be
   active, not already have an active enrollment, and not duplicate an
   existing non-deleted sample's content for that student). Every
   problem found in this phase is collected — not just the first — so a
   caller sees every reason the batch was rejected in one response.
2. **Gate** — if *any* row failed either part of the validation phase,
   the entire batch is rejected: every staged file from phase 1 is
   discarded, **zero** database rows are created, and the response
   reports ``success=False`` with every row's outcome. This is the
   literal meaning of "fully atomic" this module implements: atomicity
   is achieved by never starting a write until every row is already
   known-good, not by attempting all writes and rolling back after a
   partial failure.
3. **Execution phase** — reached only when every row passed validation.
   Each row is then processed through the same staged-PENDING-row ->
   atomic-promote -> ACTIVE sequence single enrollment uses (see
   app.modules.biometric_enrollment.service's module docstring for why a
   SQL transaction alone cannot make that filesystem rename atomic). A
   genuine infrastructure failure partway through execution (disk full,
   database connection lost) is the one scenario where this batch cannot
   be perfectly all-or-nothing — already-processed rows in this rare
   case remain enrolled, the failing row and any not yet reached are
   reported as failed, and the response's ``success`` is ``False``. This
   is documented, tested (see app/tests/test_phase5_stage2_bulk_zip.py),
   and consistent with docs/BIOMETRIC_DATA_POLICY.md's explicit
   statement that a database transaction cannot make filesystem changes
   atomic — reconciliation covers any resulting drift.
"""

from __future__ import annotations

import re
import uuid
import zipfile
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.db.transaction import service_transaction
from app.modules.attendance.models import AuditOutcome
from app.modules.attendance.repository import AuditLogRepository
from app.modules.biometric_enrollment.errors import (
    BulkEnrollmentValidationError,
    BulkEnrollmentZipInvalidError,
    BulkEnrollmentZipTooLargeError,
)
from app.modules.biometric_enrollment.image_validation import ValidatedImage, validate_image_file
from app.modules.biometric_enrollment.models import (
    EnrollmentStatus,
    SampleStatus,
)
from app.modules.biometric_enrollment.repository import (
    BiometricEnrollmentRepository,
    BiometricSampleRepository,
)
from app.modules.biometric_enrollment.schemas import BulkEnrollmentResult, BulkEnrollmentRowResult
from app.modules.biometric_enrollment.storage import (
    PrivateBiometricStorage,
    StorageCapExceededError,
)
from app.modules.biometric_enrollment.zip_security import (
    ManifestRow,
    stream_member_to_path,
    validate_archive,
)
from app.modules.profiles.repository import StudentProfileRepository
from app.modules.users.models import User

logger = structlog.get_logger(__name__)

ACTION_BULK_ENROLLMENT_ATTEMPTED = "biometric_enrollment.bulk_attempted"
ACTION_BULK_ENROLLMENT_COMPLETED = "biometric_enrollment.bulk_completed"
_ENTITY_TYPE_BULK_BATCH = "biometric_enrollment_batch"
_ENTITY_TYPE_SAMPLE = "biometric_sample"

_MAX_ROW_ERROR_LENGTH = 300


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class _PreparedRow:
    manifest_row: ManifestRow
    student_profile_id: uuid.UUID
    staging_key: str
    validated: ValidatedImage
    enrollment_id: uuid.UUID | None  # None => must be created in the execution phase


@dataclass
class _RowProblem:
    manifest_row: ManifestRow | None
    row_number: int
    student_profile_id: uuid.UUID | None
    filename: str
    code: str
    message: str


class BulkEnrollmentService:
    """Orchestrates ``validate_archive`` + per-row image/DB processing."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        storage: PrivateBiometricStorage | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._storage = storage or PrivateBiometricStorage(self._settings)
        self._students = StudentProfileRepository(session)
        self._enrollments = BiometricEnrollmentRepository(session)
        self._samples = BiometricSampleRepository(session)
        self._audit_logs = AuditLogRepository(session)

    async def enroll_from_zip(
        self,
        *,
        current_user: User,
        chunks: AsyncIterator[bytes],
        request_id: str | None = None,
    ) -> BulkEnrollmentResult:
        actor_user_id = current_user.id
        zip_key = self._storage.new_key()
        try:
            await self._storage.write_bulk_zip_staged(
                zip_key, chunks, max_bytes=self._settings.MAX_BULK_ENROLLMENT_ZIP_BYTES
            )
        except StorageCapExceededError as exc:
            raise BulkEnrollmentZipTooLargeError(
                self._settings.MAX_BULK_ENROLLMENT_ZIP_BYTES
            ) from exc

        try:
            try:
                manifest_rows = validate_archive(
                    self._storage.bulk_zip_staging_path(zip_key), settings=self._settings
                )
            except (BulkEnrollmentValidationError, BulkEnrollmentZipInvalidError):
                # The archive itself is rejected before any row-level
                # processing ever begins (malformed ZIP, an unsafe/
                # path-traversal member, a missing manifest, and so on).
                # Still a bulk-enrollment attempt worth recording as
                # BLOCKED, same as a row-validation rejection below —
                # only aggregate counts are logged (via
                # `_write_batch_audit`), never a filename, member path,
                # or any archive content. The original error is always
                # re-raised unchanged immediately after.
                await self._write_batch_audit(
                    actor_user_id=actor_user_id,
                    action=ACTION_BULK_ENROLLMENT_ATTEMPTED,
                    outcome=AuditOutcome.BLOCKED,
                    total_rows=0,
                    enrolled_count=0,
                    request_id=request_id,
                )
                raise

            prepared, problems = await self._prepare_rows(manifest_rows, zip_key=zip_key)

            if problems:
                await self._write_batch_audit(
                    actor_user_id=actor_user_id,
                    action=ACTION_BULK_ENROLLMENT_ATTEMPTED,
                    outcome=AuditOutcome.BLOCKED,
                    total_rows=len(manifest_rows),
                    enrolled_count=0,
                    request_id=request_id,
                )
                for item in prepared:
                    self._storage.discard_staged(item.staging_key)
                return self._failed_result(manifest_rows, problems)

            result = await self._execute_rows(
                prepared, actor_user_id=actor_user_id, request_id=request_id
            )
            return result
        finally:
            self._storage.discard_bulk_zip_staged(zip_key)

    # --- phase 1: validation (zero side effects on failure) -------------------

    async def _prepare_rows(
        self, manifest_rows: list[ManifestRow], *, zip_key: str
    ) -> tuple[list[_PreparedRow], list[_RowProblem]]:
        prepared: list[_PreparedRow] = []
        problems: list[_RowProblem] = []

        with self._open_zip(zip_key) as zf:
            for manifest_row in manifest_rows:
                problem = await self._prepare_one_row(zf, manifest_row, prepared=prepared)
                if problem is not None:
                    problems.append(problem)

        return prepared, problems

    def _open_zip(self, zip_key: str) -> zipfile.ZipFile:
        return zipfile.ZipFile(self._storage.bulk_zip_staging_path(zip_key))

    async def _prepare_one_row(
        self,
        zf: zipfile.ZipFile,
        manifest_row: ManifestRow,
        *,
        prepared: list[_PreparedRow],
    ) -> _RowProblem | None:
        student = await self._students.get_by_id(manifest_row.student_profile_id)
        if student is None:
            return _RowProblem(
                manifest_row=manifest_row,
                row_number=manifest_row.row_number,
                student_profile_id=manifest_row.student_profile_id,
                filename=manifest_row.filename,
                code="ROW_STUDENT_NOT_FOUND",
                message="Student profile not found.",
            )
        if not student.is_active:
            return _RowProblem(
                manifest_row=manifest_row,
                row_number=manifest_row.row_number,
                student_profile_id=manifest_row.student_profile_id,
                filename=manifest_row.filename,
                code="ROW_STUDENT_INACTIVE",
                message="Student profile is inactive.",
            )

        enrollment = await self._enrollments.get_by_student_profile_id(student.id)
        if enrollment is not None:
            if enrollment.status is EnrollmentStatus.DELETION_PENDING:
                return _RowProblem(
                    manifest_row=manifest_row,
                    row_number=manifest_row.row_number,
                    student_profile_id=manifest_row.student_profile_id,
                    filename=manifest_row.filename,
                    code="ROW_ENROLLMENT_DELETION_PENDING",
                    message="Enrollment has a deletion in progress.",
                )
            existing_active = await self._samples.get_active_for_enrollment(enrollment.id)
            if existing_active is not None:
                return _RowProblem(
                    manifest_row=manifest_row,
                    row_number=manifest_row.row_number,
                    student_profile_id=manifest_row.student_profile_id,
                    filename=manifest_row.filename,
                    code="ROW_ALREADY_ACTIVE",
                    message=(
                        "Student already has an active enrollment; bulk "
                        "ingestion only creates new enrollments."
                    ),
                )

        staging_key = self._storage.new_key()
        try:
            stream_member_to_path(
                zf,
                manifest_row.zip_info,
                self._storage.staging_path(staging_key),
                max_bytes=self._settings.MAX_ENROLLMENT_IMAGE_BYTES,
            )
        except BulkEnrollmentValidationError as exc:
            self._storage.discard_staged(staging_key)
            detail = exc.details.get("errors", [{}])
            message = str(detail[0].get("message", "Archive member could not be read."))
            return _RowProblem(
                manifest_row=manifest_row,
                row_number=manifest_row.row_number,
                student_profile_id=manifest_row.student_profile_id,
                filename=manifest_row.filename,
                code="ROW_MEMBER_READ_FAILED",
                message=message[:_MAX_ROW_ERROR_LENGTH],
            )

        try:
            validated = validate_image_file(
                self._storage.staging_path(staging_key),
                settings=self._settings,
                declared_content_type=None,
            )
        except AppError as exc:
            # validate_image_file's own contract guarantees it never
            # raises anything other than an AppError subclass (see
            # image_validation.py's module docstring) — narrowed here
            # rather than a blind `except Exception` because that
            # contract makes a broader catch unnecessary. This row's
            # image is rejected; the batch's pre-validation phase
            # continues to check every other row before deciding the
            # overall outcome (see this module's module docstring).
            self._storage.discard_staged(staging_key)
            code = getattr(exc, "code", "ROW_IMAGE_INVALID")
            message = getattr(exc, "message", str(exc))
            return _RowProblem(
                manifest_row=manifest_row,
                row_number=manifest_row.row_number,
                student_profile_id=manifest_row.student_profile_id,
                filename=manifest_row.filename,
                code=str(code),
                message=str(message)[:_MAX_ROW_ERROR_LENGTH],
            )

        if enrollment is not None:
            duplicate = await self._samples.find_duplicate_content(
                enrollment_id=enrollment.id, sha256_hash=validated.sha256_hash
            )
            if duplicate is not None:
                self._storage.discard_staged(staging_key)
                return _RowProblem(
                    manifest_row=manifest_row,
                    row_number=manifest_row.row_number,
                    student_profile_id=manifest_row.student_profile_id,
                    filename=manifest_row.filename,
                    code="ROW_DUPLICATE_CONTENT",
                    message="This exact image has already been enrolled for this student.",
                )

        prepared.append(
            _PreparedRow(
                manifest_row=manifest_row,
                student_profile_id=student.id,
                staging_key=staging_key,
                validated=validated,
                enrollment_id=enrollment.id if enrollment is not None else None,
            )
        )
        return None

    # --- phase 2: execution (only reached when every row is valid) ------------

    async def _execute_rows(
        self,
        prepared: list[_PreparedRow],
        *,
        actor_user_id: uuid.UUID,
        request_id: str | None,
    ) -> BulkEnrollmentResult:
        row_results: list[BulkEnrollmentRowResult] = []
        enrolled_count = 0
        infra_failure = False

        for item in prepared:
            try:
                sample_id = await self._execute_one_row(item, actor_user_id=actor_user_id)
            except Exception as exc:
                # Deliberately broad and deliberately not re-raised: by
                # this point every row already passed full pre-validation
                # (phase 1), so any exception here is a genuine
                # infrastructure failure (disk, database), not an
                # anticipated business-rule rejection. Catching it lets
                # the loop keep processing the remaining rows and return
                # a structured, honest partial result instead of a raw
                # 500 that would hide which rows did succeed. See this
                # module's docstring for the full atomicity contract.
                #
                # A best-effort, idempotent staged-file cleanup for this
                # row: `_execute_one_row`'s own compensation already
                # handles a file it promoted (moving it via quarantine
                # out of active/), so this is a no-op for that case —
                # it only matters for a row that failed *before*
                # promoting (e.g. `create_pending`'s own transaction),
                # which would otherwise leave its staged file behind.
                self._storage.discard_staged(item.staging_key)
                infra_failure = True
                logger.error(
                    "bulk_enrollment_row_execution_failed",
                    row_number=item.manifest_row.row_number,
                    student_profile_id=str(item.manifest_row.student_profile_id),
                    exc_type=type(exc).__name__,
                    request_id=request_id,
                )
                row_results.append(
                    BulkEnrollmentRowResult(
                        row_number=item.manifest_row.row_number,
                        student_profile_id=str(item.manifest_row.student_profile_id),
                        filename=item.manifest_row.filename,
                        outcome="failed",
                        error_code="ROW_EXECUTION_FAILED",
                        error_message="An internal error occurred while enrolling this row.",
                    )
                )
                continue

            enrolled_count += 1
            row_results.append(
                BulkEnrollmentRowResult(
                    row_number=item.manifest_row.row_number,
                    student_profile_id=str(item.manifest_row.student_profile_id),
                    filename=item.manifest_row.filename,
                    outcome="enrolled",
                    sample_id=sample_id,
                )
            )

        success = not infra_failure
        await self._write_batch_audit(
            actor_user_id=actor_user_id,
            action=ACTION_BULK_ENROLLMENT_COMPLETED,
            outcome=AuditOutcome.SUCCESS if success else AuditOutcome.BLOCKED,
            total_rows=len(prepared),
            enrolled_count=enrolled_count,
            request_id=request_id,
        )
        return BulkEnrollmentResult(
            success=success,
            total_rows=len(prepared),
            enrolled_count=enrolled_count,
            failed_count=len(prepared) - enrolled_count,
            rows=row_results,
        )

    async def _execute_one_row(self, item: _PreparedRow, *, actor_user_id: uuid.UUID) -> uuid.UUID:
        enrollment_id = item.enrollment_id
        if enrollment_id is None:
            async with service_transaction(self._session):
                enrollment = await self._enrollments.create(
                    student_profile_id=item.student_profile_id,
                    created_by_user_id=actor_user_id,
                )
                enrollment_id = enrollment.id

        async with service_transaction(self._session):
            sample = await self._samples.create_pending(
                enrollment_id=enrollment_id,
                storage_key=item.staging_key,
                original_filename=_sanitize_filename(item.manifest_row.filename),
                content_type=item.validated.content_type,
                file_size_bytes=item.validated.size_bytes,
                width_px=item.validated.width_px,
                height_px=item.validated.height_px,
                sha256_hash=item.validated.sha256_hash,
                created_by_user_id=actor_user_id,
                previous_sample_id=None,
            )
            sample_id = sample.id

        try:
            self._storage.promote(item.staging_key)
        except OSError:
            try:
                async with service_transaction(self._session):
                    await self._samples.delete_row(sample)
            except Exception:
                # Intentionally swallowed: the outer `raise` below always
                # re-raises the original OSError regardless of whether
                # this compensating delete succeeds — a secondary
                # failure here must not replace that original error with
                # a less useful one. Logged so it is never silent; see
                # app.modules.biometric_enrollment.service's identical
                # `_compensate_failed_promote` for the same rationale.
                logger.error(
                    "bulk_enrollment_promote_compensation_failed", sample_id=str(sample_id)
                )
            raise

        try:
            async with service_transaction(self._session):
                await self._samples.mark_active(sample, promoted_at=_utcnow())
                persisted_enrollment = await self._enrollments.get_by_id(enrollment_id)
                if persisted_enrollment is None:
                    raise RuntimeError("Prepared biometric enrollment disappeared.")
                await self._enrollments.set_status(
                    persisted_enrollment, status=EnrollmentStatus.ACTIVE
                )
                await self._audit_logs.create(
                    actor_user_id=actor_user_id,
                    action="biometric_enrollment.sample_create",
                    outcome=AuditOutcome.SUCCESS,
                    entity_type=_ENTITY_TYPE_SAMPLE,
                    entity_id=sample_id,
                    event_metadata={
                        "student_profile_id": str(item.student_profile_id),
                        "enrollment_id": str(enrollment_id),
                        "sha256_hash": item.validated.sha256_hash,
                        "via": "bulk_zip",
                    },
                )
        except Exception:
            # The file was already promoted (an irreversible rename) but
            # the transaction that would mark it ACTIVE rolled back — see
            # app.modules.biometric_enrollment.service's identical
            # ``_compensate_promoted_file_after_activation_failure`` for
            # the full rationale (duplicated here on purpose, same as
            # ``_sanitize_filename`` above). Always re-raised: this
            # module's caller (``_execute_rows``) reports the row as
            # failed and also discards any leftover staged file.
            await self._compensate_promoted_file_after_activation_failure(
                item.staging_key, sample_id
            )
            raise
        return sample_id

    # --- shared -------------------------------------------------------------

    async def _write_batch_audit(
        self,
        *,
        actor_user_id: uuid.UUID,
        action: str,
        outcome: AuditOutcome,
        total_rows: int,
        enrolled_count: int,
        request_id: str | None,
    ) -> None:
        try:
            await self._audit_logs.create(
                actor_user_id=actor_user_id,
                action=action,
                outcome=outcome,
                entity_type=_ENTITY_TYPE_BULK_BATCH,
                request_id=request_id,
                event_metadata={"total_rows": total_rows, "enrolled_count": enrolled_count},
            )
            await self._session.commit()
        except Exception as exc:
            # Intentionally swallowed: this audit write is a best-effort
            # side effect of a request whose real, meaningful result
            # (the BulkEnrollmentResult already computed by the caller)
            # must still reach the client even if this fails. Rolled
            # back and logged so the failure is never silent and never
            # left half-committed.
            await self._session.rollback()
            logger.error("bulk_enrollment_audit_write_failed", exc_type=type(exc).__name__)

    async def _compensate_promoted_file_after_activation_failure(
        self, key: str, sample_id: uuid.UUID
    ) -> None:
        """Duplicated from ``BiometricEnrollmentService`` on purpose.

        Same rationale as ``_sanitize_filename`` below: a four-helper
        function is not worth a cross-module import of a private name.
        See app/modules/biometric_enrollment/service.py's identical
        method for the full docstring — this is the same "the rename
        already happened, the DB transaction that would mark it ACTIVE
        did not" cleanup: quarantine-then-purge the now-orphaned active
        file, remove the now-meaningless row (re-read fresh by a UUID
        captured before the risky transaction rather than trusting an
        expired ORM object), and never re-raise — the caller always re-raises the
        original failure regardless of whether this cleanup succeeds.
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
                "bulk_enrollment_post_promote_activation_compensation_failed",
                sample_id=str(sample_id),
                exc_type=type(exc).__name__,
            )

    def _failed_result(
        self, manifest_rows: list[ManifestRow], problems: list[_RowProblem]
    ) -> BulkEnrollmentResult:
        problems_by_row = {problem.row_number: problem for problem in problems}
        rows: list[BulkEnrollmentRowResult] = []
        for manifest_row in manifest_rows:
            problem = problems_by_row.get(manifest_row.row_number)
            if problem is not None:
                rows.append(
                    BulkEnrollmentRowResult(
                        row_number=manifest_row.row_number,
                        student_profile_id=str(manifest_row.student_profile_id),
                        filename=manifest_row.filename,
                        outcome="failed",
                        error_code=problem.code,
                        error_message=problem.message,
                    )
                )
            else:
                rows.append(
                    BulkEnrollmentRowResult(
                        row_number=manifest_row.row_number,
                        student_profile_id=str(manifest_row.student_profile_id),
                        filename=manifest_row.filename,
                        outcome="failed",
                        error_code="ROW_BATCH_REJECTED",
                        error_message=(
                            "This row was valid, but the batch was rejected because "
                            "another row failed validation (the batch is all-or-nothing)."
                        ),
                    )
                )
        return BulkEnrollmentResult(
            success=False,
            total_rows=len(manifest_rows),
            enrolled_count=0,
            failed_count=len(manifest_rows),
            rows=rows,
        )


def _sanitize_filename(original: str | None) -> str | None:
    """Duplicated from ``app.modules.biometric_enrollment.service`` on purpose.

    Same rationale as ``_enum_values`` in
    ``app.modules.biometric_enrollment.models``: a four-line helper is
    not worth a cross-module import of a private name.
    """
    if not original:
        return None
    base = original.replace("\\", "/").rsplit("/", 1)[-1].strip()
    base = base.lstrip(".")
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("_")
    if not cleaned:
        return None
    return cleaned[:128]
