"""Versioned announcement API with role/classroom visibility."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.announcements.schemas import (
    AnnouncementCreateRequest,
    AnnouncementRead,
    AnnouncementUpdate,
)
from app.modules.announcements.service import AnnouncementService
from app.modules.auth.dependencies import require_roles
from app.modules.users.models import User, UserRole
from app.schemas.pagination import Page

router = APIRouter(prefix="/announcements", tags=["announcements"])
AnyUser = Annotated[
    User, Depends(require_roles(UserRole.ADMIN, UserRole.TEACHER, UserRole.STUDENT))
]
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("", response_model=Page[AnnouncementRead])
async def list_announcements(
    current_user: AnyUser,
    session: Session,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[AnnouncementRead]:
    return await AnnouncementService(session).list_for_user(
        current_user,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset,
    )


@router.get("/{announcement_id}", response_model=AnnouncementRead)
async def get_announcement(
    announcement_id: uuid.UUID, current_user: AnyUser, session: Session
) -> AnnouncementRead:
    return await AnnouncementService(session).get_for_user(current_user, announcement_id)


@router.post("", response_model=AnnouncementRead, status_code=status.HTTP_201_CREATED)
async def create_announcement(
    payload: AnnouncementCreateRequest,
    current_user: AdminUser,
    session: Session,
) -> AnnouncementRead:
    return await AnnouncementService(session).create(current_user, payload)


@router.patch("/{announcement_id}", response_model=AnnouncementRead)
async def update_announcement(
    announcement_id: uuid.UUID,
    payload: AnnouncementUpdate,
    _admin: AdminUser,
    session: Session,
) -> AnnouncementRead:
    return await AnnouncementService(session).update(announcement_id, payload)


@router.delete("/{announcement_id}", response_model=AnnouncementRead)
async def deactivate_announcement(
    announcement_id: uuid.UUID, _admin: AdminUser, session: Session
) -> AnnouncementRead:
    return await AnnouncementService(session).deactivate(announcement_id)
