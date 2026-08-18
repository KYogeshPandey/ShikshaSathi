"""Versioned teacher-profile API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.auth.dependencies import require_roles
from app.modules.profiles.schemas import (
    TeacherProfileCreate,
    TeacherProfileRead,
    TeacherProfileUpdate,
)
from app.modules.profiles.teacher_service import TeacherProfileService
from app.modules.users.models import User, UserRole
from app.schemas.pagination import Page

router = APIRouter(prefix="/teacher-profiles", tags=["teacher profiles"])
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
TeacherUser = Annotated[User, Depends(require_roles(UserRole.TEACHER))]
AdminOrTeacher = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.TEACHER))]
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/me", response_model=TeacherProfileRead)
async def get_my_teacher_profile(current_user: TeacherUser, session: Session) -> TeacherProfileRead:
    row = await TeacherProfileService(session).get_for_user(current_user)
    return TeacherProfileRead.model_validate(row)


@router.get("", response_model=Page[TeacherProfileRead])
async def list_teacher_profiles(
    _admin: AdminUser,
    session: Session,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[TeacherProfileRead]:
    return await TeacherProfileService(session).list(
        include_inactive=include_inactive, limit=limit, offset=offset
    )


@router.get("/{profile_id}", response_model=TeacherProfileRead)
async def get_teacher_profile(
    profile_id: uuid.UUID, current_user: AdminOrTeacher, session: Session
) -> TeacherProfileRead:
    row = await TeacherProfileService(session).get_for_user(current_user, profile_id)
    return TeacherProfileRead.model_validate(row)


@router.post("", response_model=TeacherProfileRead, status_code=status.HTTP_201_CREATED)
async def create_teacher_profile(
    payload: TeacherProfileCreate, _admin: AdminUser, session: Session
) -> TeacherProfileRead:
    row = await TeacherProfileService(session).create(payload)
    return TeacherProfileRead.model_validate(row)


@router.patch("/{profile_id}", response_model=TeacherProfileRead)
async def update_teacher_profile(
    profile_id: uuid.UUID,
    payload: TeacherProfileUpdate,
    _admin: AdminUser,
    session: Session,
) -> TeacherProfileRead:
    row = await TeacherProfileService(session).update(profile_id, payload)
    return TeacherProfileRead.model_validate(row)


@router.delete("/{profile_id}", response_model=TeacherProfileRead)
async def deactivate_teacher_profile(
    profile_id: uuid.UUID, _admin: AdminUser, session: Session
) -> TeacherProfileRead:
    row = await TeacherProfileService(session).deactivate(profile_id)
    return TeacherProfileRead.model_validate(row)
