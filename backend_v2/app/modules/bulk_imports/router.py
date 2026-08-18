"""Admin-only bounded CSV/XLSX academic import API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.auth.dependencies import require_roles
from app.modules.bulk_imports.parser import MAX_IMPORT_BYTES
from app.modules.bulk_imports.schemas import BulkImportEntity, BulkImportResult
from app.modules.bulk_imports.service import BulkImportService
from app.modules.users.models import User, UserRole

router = APIRouter(prefix="/imports", tags=["bulk imports"])
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.post("/{entity}", response_model=BulkImportResult)
async def import_academic_records(
    entity: BulkImportEntity,
    _admin: AdminUser,
    session: Session,
    file: Annotated[UploadFile, File(description="UTF-8 CSV or XLSX file")],
) -> BulkImportResult:
    try:
        content = await file.read(MAX_IMPORT_BYTES + 1)
    finally:
        await file.close()
    return await BulkImportService(session).import_file(
        entity=entity,
        filename=file.filename or "",
        content=content,
    )
