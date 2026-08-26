"""Versioned timetable API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.academics.schemas import (
    TimetableEntryCreate,
    TimetableEntryRead,
    TimetableEntryUpdate,
)
from app.modules.academics.timetable_service import TimetableService
from app.modules.auth.dependencies import require_roles
from app.modules.users.models import User, UserRole
from app.schemas.pagination import Page

router = APIRouter(prefix="/timetable-entries", tags=["timetable"])
AnyUser = Annotated[
    User, Depends(require_roles(UserRole.ADMIN, UserRole.TEACHER, UserRole.STUDENT))
]
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("", response_model=Page[TimetableEntryRead])
async def list_timetable_entries(
    current_user: AnyUser,
    session: Session,
    classroom_id: uuid.UUID | None = None,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[TimetableEntryRead]:
    return await TimetableService(session).list_for_user(
        current_user,
        classroom_id=classroom_id,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset,
    )


@router.get("/{entry_id}", response_model=TimetableEntryRead)
async def get_timetable_entry(
    entry_id: uuid.UUID, current_user: AnyUser, session: Session
) -> TimetableEntryRead:
    row = await TimetableService(session).get_for_user(current_user, entry_id)
    return TimetableEntryRead.model_validate(row)


@router.post("", response_model=TimetableEntryRead, status_code=status.HTTP_201_CREATED)
async def create_timetable_entry(
    payload: TimetableEntryCreate, _admin: AdminUser, session: Session
) -> TimetableEntryRead:
    row = await TimetableService(session).create(payload)
    return TimetableEntryRead.model_validate(row)


@router.patch("/{entry_id}", response_model=TimetableEntryRead)
async def update_timetable_entry(
    entry_id: uuid.UUID,
    payload: TimetableEntryUpdate,
    _admin: AdminUser,
    session: Session,
) -> TimetableEntryRead:
    row = await TimetableService(session).update(entry_id, payload)
    return TimetableEntryRead.model_validate(row)


@router.delete("/{entry_id}", response_model=TimetableEntryRead)
async def deactivate_timetable_entry(
    entry_id: uuid.UUID, _admin: AdminUser, session: Session
) -> TimetableEntryRead:
    row = await TimetableService(session).deactivate(entry_id)
    return TimetableEntryRead.model_validate(row)
