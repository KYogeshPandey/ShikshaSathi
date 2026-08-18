"""Versioned subject API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.academics.schemas import SubjectCreate, SubjectRead, SubjectUpdate
from app.modules.academics.subjects_service import SubjectService
from app.modules.auth.dependencies import require_roles
from app.modules.users.models import User, UserRole
from app.schemas.pagination import Page

router = APIRouter(prefix="/subjects", tags=["subjects"])
AnyUser = Annotated[
    User, Depends(require_roles(UserRole.ADMIN, UserRole.TEACHER, UserRole.STUDENT))
]
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("", response_model=Page[SubjectRead])
async def list_subjects(
    current_user: AnyUser,
    session: Session,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[SubjectRead]:
    return await SubjectService(session).list_for_user(
        current_user,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset,
    )


@router.get("/{subject_id}", response_model=SubjectRead)
async def get_subject(
    subject_id: uuid.UUID, current_user: AnyUser, session: Session
) -> SubjectRead:
    row = await SubjectService(session).get_for_user(current_user, subject_id)
    return SubjectRead.model_validate(row)


@router.post("", response_model=SubjectRead, status_code=status.HTTP_201_CREATED)
async def create_subject(
    payload: SubjectCreate, _admin: AdminUser, session: Session
) -> SubjectRead:
    row = await SubjectService(session).create(payload)
    return SubjectRead.model_validate(row)


@router.patch("/{subject_id}", response_model=SubjectRead)
async def update_subject(
    subject_id: uuid.UUID,
    payload: SubjectUpdate,
    _admin: AdminUser,
    session: Session,
) -> SubjectRead:
    row = await SubjectService(session).update(subject_id, payload)
    return SubjectRead.model_validate(row)


@router.delete("/{subject_id}", response_model=SubjectRead)
async def deactivate_subject(
    subject_id: uuid.UUID, _admin: AdminUser, session: Session
) -> SubjectRead:
    row = await SubjectService(session).deactivate(subject_id)
    return SubjectRead.model_validate(row)
