"""Thin, authorized API for biometric enrollment and photo ingestion.

Follows ``app.modules.attendance.router``'s conventions: the router
parses the request, resolves ``request.state.request_id``, and delegates
everything else to the service layer — no business logic, no direct
repository/ORM access here.

**No response from any route in this module ever contains**: raw image
bytes, an embedding, a storage key, an absolute or temporary filesystem
path, or provider diagnostics. Every response is one of the schemas in
``app.modules.biometric_enrollment.schemas``, each of which is
safe-metadata-only by construction (see that module's docstrings).

Authorization (see docs/BIOMETRIC_DATA_POLICY.md, Stage 1, Accepted):
create/replace/delete/bulk-create/reconciliation are **admin only** —
there is no teacher role in this module at all, and no object-level
ownership check is needed for an admin route (an admin's role already
grants full scope). Reading one enrollment is admin-or-the-student-
themselves; the service layer enforces that with a concealed 404 (see
``BiometricEnrollmentService.get_detail``), matching
``app.modules.profiles.student_router``'s pattern.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.auth.dependencies import require_roles
from app.modules.biometric_enrollment.bulk_service import BulkEnrollmentService
from app.modules.biometric_enrollment.reconciliation import ReconciliationService
from app.modules.biometric_enrollment.schemas import (
    BiometricEnrollmentDetailRead,
    BiometricEnrollmentRead,
    BiometricSampleRead,
    BiometricSampleReplaceResult,
    BulkEnrollmentResult,
    ReconciliationReport,
)
from app.modules.biometric_enrollment.service import BiometricEnrollmentService
from app.modules.users.models import User, UserRole

router = APIRouter(prefix="/biometric-enrollments", tags=["biometric enrollment"])

AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
AdminOrStudentUser = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.STUDENT))]
Session = Annotated[AsyncSession, Depends(get_db_session)]

_UPLOAD_CHUNK_SIZE = 1024 * 1024


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


async def _iter_upload_chunks(file: UploadFile) -> AsyncIterator[bytes]:
    """Adapt FastAPI's ``UploadFile`` into a plain ``AsyncIterator[bytes]``.

    Keeps app.modules.biometric_enrollment.storage free of any FastAPI
    import — the storage/service layers only ever see a byte-chunk
    iterator, never an ``UploadFile``.
    """
    try:
        while True:
            chunk = await file.read(_UPLOAD_CHUNK_SIZE)
            if not chunk:
                break
            yield chunk
    finally:
        await file.close()


@router.post("/bulk", response_model=BulkEnrollmentResult)
async def bulk_enroll_from_zip(
    admin: AdminUser,
    session: Session,
    request: Request,
    file: Annotated[UploadFile, File(description="A ZIP archive with a root manifest.csv.")],
) -> BulkEnrollmentResult:
    """Secure, manifest-driven bulk enrollment from a ZIP archive.

    See app/modules/biometric_enrollment/zip_security.py and
    app/modules/biometric_enrollment/bulk_service.py's module docstrings
    for the manifest format and the exact atomicity contract. Only
    creates *new* enrollments — a row for a student who already has an
    active sample fails that row (and, per the atomicity contract, the
    whole batch).
    """
    service = BulkEnrollmentService(session)
    return await service.enroll_from_zip(
        current_user=admin, chunks=_iter_upload_chunks(file), request_id=_request_id(request)
    )


@router.get("/reconciliation/report", response_model=ReconciliationReport)
async def get_reconciliation_report(
    admin: AdminUser,
    session: Session,
) -> ReconciliationReport:
    """Admin-only, read-only drift report — never modifies data.

    See app/modules/biometric_enrollment/reconciliation.py's module
    docstring: this only reports findings, it never repairs them.
    """
    service = ReconciliationService(session)
    return await service.generate_report()


@router.get("/{student_profile_id}", response_model=BiometricEnrollmentDetailRead)
async def get_enrollment(
    student_profile_id: uuid.UUID,
    current_user: AdminOrStudentUser,
    session: Session,
    request: Request,
) -> BiometricEnrollmentDetailRead:
    """Admin: any student's enrollment + full sample history.

    Student: only their own — any other ``student_profile_id`` resolves
    to the same concealed 404 as a genuinely missing one.
    """
    service = BiometricEnrollmentService(session)
    return await service.get_detail(
        current_user=current_user,
        student_profile_id=student_profile_id,
        request_id=_request_id(request),
    )


@router.post(
    "/{student_profile_id}/samples",
    response_model=BiometricSampleRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_enrollment_sample(
    student_profile_id: uuid.UUID,
    admin: AdminUser,
    session: Session,
    request: Request,
    file: Annotated[UploadFile, File(description="A single still image (JPEG/PNG/WEBP).")],
) -> BiometricSampleRead:
    """Create the first biometric sample for a student.

    409s if the student already has an active sample — use the replace
    route (``PUT .../samples/active``) instead.
    """
    service = BiometricEnrollmentService(session)
    return await service.create_sample(
        current_user=admin,
        student_profile_id=student_profile_id,
        chunks=_iter_upload_chunks(file),
        declared_content_type=file.content_type,
        original_filename=file.filename,
        request_id=_request_id(request),
    )


@router.put(
    "/{student_profile_id}/samples/active",
    response_model=BiometricSampleReplaceResult,
)
async def replace_enrollment_sample(
    student_profile_id: uuid.UUID,
    admin: AdminUser,
    session: Session,
    request: Request,
    file: Annotated[UploadFile, File(description="A single still image (JPEG/PNG/WEBP).")],
) -> BiometricSampleReplaceResult:
    """Replace the current active sample with a newly uploaded one.

    409s if the student has no active sample yet — use the create route
    instead.
    """
    service = BiometricEnrollmentService(session)
    return await service.replace_sample(
        current_user=admin,
        student_profile_id=student_profile_id,
        chunks=_iter_upload_chunks(file),
        declared_content_type=file.content_type,
        original_filename=file.filename,
        request_id=_request_id(request),
    )


@router.delete("/{student_profile_id}", response_model=BiometricEnrollmentRead)
async def request_enrollment_deletion(
    student_profile_id: uuid.UUID,
    admin: AdminUser,
    session: Session,
    request: Request,
) -> BiometricEnrollmentRead:
    """Request deletion. Attempts to complete synchronously; safe to retry.

    See ``finalize_enrollment_deletion`` below if a prior attempt did not
    fully complete (e.g. an interrupted request).
    """
    service = BiometricEnrollmentService(session)
    return await service.request_deletion(
        current_user=admin, student_profile_id=student_profile_id, request_id=_request_id(request)
    )


@router.post(
    "/{student_profile_id}/deletion/finalize",
    response_model=BiometricEnrollmentRead,
)
async def finalize_enrollment_deletion(
    student_profile_id: uuid.UUID,
    admin: AdminUser,
    session: Session,
    request: Request,
) -> BiometricEnrollmentRead:
    """Idempotent retry for a deletion that did not fully complete.

    Safe to call any number of times, including when deletion already
    completed (a no-op returning the current, already-``DELETED`` state).
    """
    service = BiometricEnrollmentService(session)
    return await service.finalize_deletion(
        current_user=admin, student_profile_id=student_profile_id, request_id=_request_id(request)
    )
