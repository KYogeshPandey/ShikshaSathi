"""Versioned admin teacher-assignment API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.academics.assignments_service import TeacherAssignmentService
from app.modules.academics.schemas import (
    TeacherAssignmentCreate,
    TeacherAssignmentRead,
    TeacherAssignmentUpdate,
)
from app.modules.auth.dependencies import require_roles
from app.modules.users.models import User, UserRole
from app.schemas.pagination import Page

router = APIRouter(prefix="/teacher-assignments", tags=["teacher assignments"])
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("", response_model=Page[TeacherAssignmentRead])
async def list_teacher_assignments(
    _admin: AdminUser,
    session: Session,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[TeacherAssignmentRead]:
    return await TeacherAssignmentService(session).list(
        include_inactive=include_inactive, limit=limit, offset=offset
    )


@router.get("/{assignment_id}", response_model=TeacherAssignmentRead)
async def get_teacher_assignment(
    assignment_id: uuid.UUID, _admin: AdminUser, session: Session
) -> TeacherAssignmentRead:
    row = await TeacherAssignmentService(session).get(assignment_id)
    return TeacherAssignmentRead.model_validate(row)


@router.post("", response_model=TeacherAssignmentRead, status_code=status.HTTP_201_CREATED)
async def create_teacher_assignment(
    payload: TeacherAssignmentCreate, _admin: AdminUser, session: Session
) -> TeacherAssignmentRead:
    row = await TeacherAssignmentService(session).create(payload)
    return TeacherAssignmentRead.model_validate(row)


@router.patch("/{assignment_id}", response_model=TeacherAssignmentRead)
async def update_teacher_assignment(
    assignment_id: uuid.UUID,
    payload: TeacherAssignmentUpdate,
    _admin: AdminUser,
    session: Session,
) -> TeacherAssignmentRead:
    row = await TeacherAssignmentService(session).update(assignment_id, payload)
    return TeacherAssignmentRead.model_validate(row)


@router.delete("/{assignment_id}", response_model=TeacherAssignmentRead)
async def deactivate_teacher_assignment(
    assignment_id: uuid.UUID, _admin: AdminUser, session: Session
) -> TeacherAssignmentRead:
    row = await TeacherAssignmentService(session).deactivate(assignment_id)
    return TeacherAssignmentRead.model_validate(row)
