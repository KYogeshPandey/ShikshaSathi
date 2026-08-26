"""Versioned student-profile and classroom-membership API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.auth.dependencies import require_roles
from app.modules.profiles.membership_service import StudentClassroomMembershipService
from app.modules.profiles.schemas import (
    StudentClassroomMembershipUpdate,
    StudentProfileCreate,
    StudentProfileRead,
    StudentProfileUpdate,
)
from app.modules.profiles.student_service import StudentProfileService
from app.modules.users.models import User, UserRole
from app.schemas.pagination import Page

router = APIRouter(prefix="/student-profiles", tags=["student profiles"])
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
StudentUser = Annotated[User, Depends(require_roles(UserRole.STUDENT))]
AdminOrStudent = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.STUDENT))]
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/me", response_model=StudentProfileRead)
async def get_my_student_profile(current_user: StudentUser, session: Session) -> StudentProfileRead:
    row = await StudentProfileService(session).get_for_user(current_user)
    return StudentProfileRead.model_validate(row)


@router.get("", response_model=Page[StudentProfileRead])
async def list_student_profiles(
    _admin: AdminUser,
    session: Session,
    classroom_id: uuid.UUID | None = None,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[StudentProfileRead]:
    return await StudentProfileService(session).list(
        classroom_id=classroom_id,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset,
    )


@router.get("/{profile_id}", response_model=StudentProfileRead)
async def get_student_profile(
    profile_id: uuid.UUID, current_user: AdminOrStudent, session: Session
) -> StudentProfileRead:
    row = await StudentProfileService(session).get_for_user(current_user, profile_id)
    return StudentProfileRead.model_validate(row)


@router.post("", response_model=StudentProfileRead, status_code=status.HTTP_201_CREATED)
async def create_student_profile(
    payload: StudentProfileCreate, _admin: AdminUser, session: Session
) -> StudentProfileRead:
    row = await StudentProfileService(session).create(payload)
    return StudentProfileRead.model_validate(row)


@router.patch("/{profile_id}", response_model=StudentProfileRead)
async def update_student_profile(
    profile_id: uuid.UUID,
    payload: StudentProfileUpdate,
    _admin: AdminUser,
    session: Session,
) -> StudentProfileRead:
    row = await StudentProfileService(session).update(profile_id, payload)
    return StudentProfileRead.model_validate(row)


@router.put("/{profile_id}/classroom-membership", response_model=StudentProfileRead)
async def assign_student_classroom(
    profile_id: uuid.UUID,
    payload: StudentClassroomMembershipUpdate,
    _admin: AdminUser,
    session: Session,
) -> StudentProfileRead:
    row = await StudentClassroomMembershipService(session).assign(profile_id, payload)
    return StudentProfileRead.model_validate(row)


@router.delete("/{profile_id}", response_model=StudentProfileRead)
async def deactivate_student_profile(
    profile_id: uuid.UUID, _admin: AdminUser, session: Session
) -> StudentProfileRead:
    row = await StudentProfileService(session).deactivate(profile_id)
    return StudentProfileRead.model_validate(row)
