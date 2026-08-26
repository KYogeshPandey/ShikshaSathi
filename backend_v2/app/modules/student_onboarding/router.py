"""Thin Admin-only multipart API for student onboarding."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.auth.dependencies import require_roles
from app.modules.bulk_imports.parser import MAX_IMPORT_BYTES
from app.modules.student_onboarding.schemas import StudentOnboardingResult
from app.modules.student_onboarding.service import StudentOnboardingService
from app.modules.users.models import User, UserRole

router = APIRouter(prefix="/student-onboarding", tags=["student onboarding"])
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
Session = Annotated[AsyncSession, Depends(get_db_session)]
_UPLOAD_CHUNK_SIZE = 1024 * 1024


async def _iter_upload_chunks(file: UploadFile) -> AsyncIterator[bytes]:
    try:
        while chunk := await file.read(_UPLOAD_CHUNK_SIZE):
            yield chunk
    finally:
        await file.close()


@router.post("", response_model=StudentOnboardingResult)
async def onboard_students(
    admin: AdminUser,
    session: Session,
    request: Request,
    classroom_id: Annotated[
        uuid.UUID, Form(description="One active target classroom for the onboarding batch")
    ],
    students_file: Annotated[UploadFile, File(description="UTF-8 CSV or XLSX student profiles")],
    photos_zip: Annotated[
        UploadFile | None, File(description="Optional ZIP of roll-number photos")
    ] = None,
    update_existing: Annotated[
        bool,
        Form(description="Update and reactivate existing student profiles in this batch"),
    ] = False,
) -> StudentOnboardingResult:
    try:
        students_content = await students_file.read(MAX_IMPORT_BYTES + 1)
    finally:
        await students_file.close()
    return await StudentOnboardingService(session).onboard(
        current_user=admin,
        classroom_id=classroom_id,
        students_filename=students_file.filename or "",
        students_content=students_content,
        photos_chunks=_iter_upload_chunks(photos_zip) if photos_zip is not None else None,
        update_existing=update_existing,
        request_id=getattr(request.state, "request_id", None),
    )
