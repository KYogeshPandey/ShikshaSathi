"""Versioned classroom API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.academics.classrooms_service import ClassroomService
from app.modules.academics.schemas import ClassroomCreate, ClassroomRead, ClassroomUpdate
from app.modules.auth.dependencies import require_roles
from app.modules.users.models import User, UserRole
from app.schemas.pagination import Page

router = APIRouter(prefix="/classrooms", tags=["classrooms"])
AnyUser = Annotated[
    User, Depends(require_roles(UserRole.ADMIN, UserRole.TEACHER, UserRole.STUDENT))
]
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("", response_model=Page[ClassroomRead])
async def list_classrooms(
    current_user: AnyUser,
    session: Session,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ClassroomRead]:
    return await ClassroomService(session).list_for_user(
        current_user,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset,
    )


@router.get("/{classroom_id}", response_model=ClassroomRead)
async def get_classroom(
    classroom_id: uuid.UUID, current_user: AnyUser, session: Session
) -> ClassroomRead:
    row = await ClassroomService(session).get_for_user(current_user, classroom_id)
    return ClassroomRead.model_validate(row)


@router.post("", response_model=ClassroomRead, status_code=status.HTTP_201_CREATED)
async def create_classroom(
    payload: ClassroomCreate, _admin: AdminUser, session: Session
) -> ClassroomRead:
    row = await ClassroomService(session).create(payload)
    return ClassroomRead.model_validate(row)


@router.patch("/{classroom_id}", response_model=ClassroomRead)
async def update_classroom(
    classroom_id: uuid.UUID,
    payload: ClassroomUpdate,
    _admin: AdminUser,
    session: Session,
) -> ClassroomRead:
    row = await ClassroomService(session).update(classroom_id, payload)
    return ClassroomRead.model_validate(row)


@router.delete("/{classroom_id}", response_model=ClassroomRead)
async def deactivate_classroom(
    classroom_id: uuid.UUID, _admin: AdminUser, session: Session
) -> ClassroomRead:
    row = await ClassroomService(session).deactivate(classroom_id)
    return ClassroomRead.model_validate(row)
