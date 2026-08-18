"""Announcement orchestration and database-driven audience visibility."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.transaction import service_transaction
from app.modules.academics.repository import ClassroomRepository
from app.modules.announcements.errors import (
    AnnouncementInactiveClassroomError,
    AnnouncementNotFoundError,
    InvalidAnnouncementAudienceError,
)
from app.modules.announcements.models import Announcement, AnnouncementAudience
from app.modules.announcements.repository import AnnouncementRepository
from app.modules.announcements.schemas import (
    AnnouncementCreateRequest,
    AnnouncementRead,
    AnnouncementUpdate,
)
from app.modules.profiles.repository import StudentProfileRepository, TeacherProfileRepository
from app.modules.users.models import User, UserRole
from app.schemas.pagination import Page


class AnnouncementService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._announcements = AnnouncementRepository(session)
        self._classrooms = ClassroomRepository(session)
        self._teachers = TeacherProfileRepository(session)
        self._students = StudentProfileRepository(session)

    async def _classroom_ids_for_user(self, current_user: User) -> set[uuid.UUID]:
        if current_user.role is UserRole.TEACHER:
            teacher_profile = await self._teachers.get_by_user_id(current_user.id)
            if teacher_profile is None or not teacher_profile.is_active:
                return set()
            return set(await self._classrooms.list_ids_for_teacher(teacher_profile.id))
        if current_user.role is UserRole.STUDENT:
            student_profile = await self._students.get_by_user_id(current_user.id)
            if (
                student_profile is not None
                and student_profile.is_active
                and student_profile.classroom_id is not None
            ):
                classroom = await self._classrooms.get_by_id(student_profile.classroom_id)
                if classroom is not None and classroom.is_active:
                    return {classroom.id}
        return set()

    async def _read(self, announcement: Announcement) -> AnnouncementRead:
        classroom_ids = await self._announcements.list_classroom_ids(announcement.id)
        return AnnouncementRead.from_model(announcement, classroom_ids)

    async def _read_many(self, announcements: list[Announcement]) -> list[AnnouncementRead]:
        classroom_ids = await self._announcements.list_classroom_ids_for_announcements(
            [announcement.id for announcement in announcements]
        )
        return [
            AnnouncementRead.from_model(
                announcement,
                classroom_ids.get(announcement.id, []),
            )
            for announcement in announcements
        ]

    async def _validate_active_targets(self, announcement: Announcement) -> None:
        classroom_ids = await self._announcements.list_classroom_ids(announcement.id)
        if announcement.audience is AnnouncementAudience.CLASSROOM and not classroom_ids:
            raise InvalidAnnouncementAudienceError()
        for classroom_id in classroom_ids:
            classroom = await self._classrooms.get_by_id(classroom_id)
            if classroom is None or not classroom.is_active:
                raise AnnouncementInactiveClassroomError()

    async def list_for_user(
        self,
        current_user: User,
        *,
        include_inactive: bool,
        limit: int,
        offset: int,
    ) -> Page[AnnouncementRead]:
        if current_user.role is UserRole.ADMIN:
            rows = await self._announcements.list(
                include_inactive=include_inactive, limit=limit, offset=offset
            )
            total = await self._announcements.count(include_inactive=include_inactive)
        else:
            classroom_ids = await self._classroom_ids_for_user(current_user)
            role_audience = (
                AnnouncementAudience.TEACHER
                if current_user.role is UserRole.TEACHER
                else AnnouncementAudience.STUDENT
            )
            rows = await self._announcements.list_visible(
                role_audience=role_audience,
                classroom_ids=classroom_ids,
                limit=limit,
                offset=offset,
            )
            total = await self._announcements.count_visible(
                role_audience=role_audience,
                classroom_ids=classroom_ids,
            )
        return Page[AnnouncementRead](
            items=await self._read_many(rows),
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_for_user(
        self, current_user: User, announcement_id: uuid.UUID
    ) -> AnnouncementRead:
        announcement = await self._announcements.get_by_id(announcement_id)
        if announcement is None:
            raise AnnouncementNotFoundError()
        if current_user.role is not UserRole.ADMIN:
            classroom_ids = await self._classroom_ids_for_user(current_user)
            role_audience = (
                AnnouncementAudience.TEACHER
                if current_user.role is UserRole.TEACHER
                else AnnouncementAudience.STUDENT
            )
            visible = await self._announcements.is_visible(
                announcement_id,
                role_audience=role_audience,
                classroom_ids=classroom_ids,
            )
            if not visible:
                raise AnnouncementNotFoundError()
        return await self._read(announcement)

    async def create(
        self, current_user: User, payload: AnnouncementCreateRequest
    ) -> AnnouncementRead:
        async with service_transaction(self._session):
            for classroom_id in payload.classroom_ids:
                classroom = await self._classrooms.get_by_id(classroom_id)
                if classroom is not None and not classroom.is_active:
                    raise AnnouncementInactiveClassroomError()
            announcement = await self._announcements.create(
                title=payload.title,
                content=payload.content,
                author_user_id=current_user.id,
                audience=payload.audience,
                classroom_ids=payload.classroom_ids,
            )
        return await self._read(announcement)

    async def update(
        self, announcement_id: uuid.UUID, payload: AnnouncementUpdate
    ) -> AnnouncementRead:
        async with service_transaction(self._session):
            announcement = await self._announcements.get_by_id(announcement_id)
            if announcement is None:
                raise AnnouncementNotFoundError()
            if payload.is_active:
                await self._validate_active_targets(announcement)
            announcement = await self._announcements.update(
                announcement, **payload.model_dump(exclude_unset=True)
            )
        return await self._read(announcement)

    async def deactivate(self, announcement_id: uuid.UUID) -> AnnouncementRead:
        async with service_transaction(self._session):
            announcement = await self._announcements.get_by_id(announcement_id)
            if announcement is None:
                raise AnnouncementNotFoundError()
            announcement = await self._announcements.deactivate(announcement)
        return await self._read(announcement)
