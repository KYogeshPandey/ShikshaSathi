"""Repository for the announcements domain.

``AnnouncementRepository.create`` validates, in order: the author
exists, the audience/classroom_ids combination is internally
consistent, and (for a ``classroom`` audience) every listed classroom
actually exists — all *before* inserting anything, so a rejected create
never leaves a partial ``Announcement`` row with no audience rows (or
vice versa). This mirrors ``app.modules.profiles.repository``'s
"load the referenced row first, validate, then insert" shape.
"""

from __future__ import annotations

import builtins
import uuid

from sqlalchemy import exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.modules.academics.models import Classroom
from app.modules.announcements.errors import (
    AnnouncementAuthorNotFoundError,
    AnnouncementClassroomReferenceError,
    InvalidAnnouncementAudienceError,
)
from app.modules.announcements.models import (
    Announcement,
    AnnouncementAudience,
    AnnouncementClassroom,
)
from app.modules.users.models import User

_ANNOUNCEMENT_CLASSROOM_UNIQUE_CONSTRAINT = "uq_announcement_classrooms_announcement_classroom"


def _matches_constraint(exc: IntegrityError, constraint_name: str) -> bool:
    candidates = (
        exc.orig,
        getattr(exc.orig, "__cause__", None),
        getattr(exc.orig, "__context__", None),
    )
    for candidate in candidates:
        if getattr(candidate, "constraint_name", None) == constraint_name:
            return True
    return constraint_name in str(exc.orig)


class AnnouncementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, announcement_id: uuid.UUID) -> Announcement | None:
        return await self._session.get(Announcement, announcement_id)

    async def list_classroom_ids(self, announcement_id: uuid.UUID) -> builtins.list[uuid.UUID]:
        """The current audience of a ``classroom``-scoped announcement.

        Returns an empty list for any non-classroom audience (correctly —
        it has no ``announcement_classrooms`` rows) as well as for an
        unknown id, so callers can compose this with
        ``AnnouncementRead.from_model`` unconditionally.
        """
        stmt = select(AnnouncementClassroom.classroom_id).where(
            AnnouncementClassroom.announcement_id == announcement_id
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_classroom_ids_for_announcements(
        self, announcement_ids: builtins.list[uuid.UUID]
    ) -> dict[uuid.UUID, builtins.list[uuid.UUID]]:
        if not announcement_ids:
            return {}
        stmt = (
            select(
                AnnouncementClassroom.announcement_id,
                AnnouncementClassroom.classroom_id,
            )
            .where(AnnouncementClassroom.announcement_id.in_(announcement_ids))
            .order_by(
                AnnouncementClassroom.announcement_id,
                AnnouncementClassroom.created_at,
            )
        )
        grouped: dict[uuid.UUID, builtins.list[uuid.UUID]] = {
            announcement_id: [] for announcement_id in announcement_ids
        }
        for announcement_id, classroom_id in (await self._session.execute(stmt)).all():
            grouped[announcement_id].append(classroom_id)
        return grouped

    async def list(
        self, *, include_inactive: bool = False, limit: int = 50, offset: int = 0
    ) -> builtins.list[Announcement]:
        stmt = (
            select(Announcement)
            .order_by(Announcement.created_at.desc(), Announcement.id)
            .limit(limit)
            .offset(offset)
        )
        if not include_inactive:
            stmt = stmt.where(Announcement.is_active.is_(True))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, *, include_inactive: bool = False) -> int:
        stmt = select(func.count()).select_from(Announcement)
        if not include_inactive:
            stmt = stmt.where(Announcement.is_active.is_(True))
        return int((await self._session.execute(stmt)).scalar_one())

    def _visibility_conditions(
        self,
        *,
        role_audience: AnnouncementAudience,
        classroom_ids: set[uuid.UUID],
    ) -> builtins.list[ColumnElement[bool]]:
        conditions: builtins.list[ColumnElement[bool]] = [
            Announcement.audience == AnnouncementAudience.ALL,
            Announcement.audience == role_audience,
        ]
        if classroom_ids:
            classroom_target = exists(
                select(AnnouncementClassroom.id).where(
                    AnnouncementClassroom.announcement_id == Announcement.id,
                    AnnouncementClassroom.classroom_id.in_(classroom_ids),
                )
            )
            conditions.append(
                (Announcement.audience == AnnouncementAudience.CLASSROOM) & classroom_target
            )
        return conditions

    async def list_visible(
        self,
        *,
        role_audience: AnnouncementAudience,
        classroom_ids: set[uuid.UUID],
        limit: int,
        offset: int,
    ) -> builtins.list[Announcement]:
        stmt = (
            select(Announcement)
            .where(
                Announcement.is_active.is_(True),
                or_(
                    *self._visibility_conditions(
                        role_audience=role_audience,
                        classroom_ids=classroom_ids,
                    )
                ),
            )
            .order_by(Announcement.created_at.desc(), Announcement.id)
            .limit(limit)
            .offset(offset)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def count_visible(
        self,
        *,
        role_audience: AnnouncementAudience,
        classroom_ids: set[uuid.UUID],
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(Announcement)
            .where(
                Announcement.is_active.is_(True),
                or_(
                    *self._visibility_conditions(
                        role_audience=role_audience,
                        classroom_ids=classroom_ids,
                    )
                ),
            )
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def is_visible(
        self,
        announcement_id: uuid.UUID,
        *,
        role_audience: AnnouncementAudience,
        classroom_ids: set[uuid.UUID],
    ) -> bool:
        stmt = select(Announcement.id).where(
            Announcement.id == announcement_id,
            Announcement.is_active.is_(True),
            or_(
                *self._visibility_conditions(
                    role_audience=role_audience,
                    classroom_ids=classroom_ids,
                )
            ),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def _existing_classroom_ids(
        self, classroom_ids: builtins.list[uuid.UUID]
    ) -> set[uuid.UUID]:
        if not classroom_ids:
            return set()
        stmt = select(Classroom.id).where(Classroom.id.in_(classroom_ids))
        result = await self._session.execute(stmt)
        return set(result.scalars().all())

    async def create(
        self,
        *,
        title: str,
        content: str,
        author_user_id: uuid.UUID,
        audience: AnnouncementAudience,
        classroom_ids: builtins.list[uuid.UUID] | None = None,
    ) -> Announcement:
        """Create an announcement and (for a classroom audience) its audience rows.

        Raises ``AnnouncementAuthorNotFoundError`` if ``author_user_id``
        does not exist, ``InvalidAnnouncementAudienceError`` if
        ``audience``/``classroom_ids`` are inconsistent, or
        ``AnnouncementClassroomReferenceError`` if any ``classroom_ids``
        entry does not exist. All three are checked before anything is
        inserted.
        """
        classroom_ids = classroom_ids or []

        if audience is not AnnouncementAudience.CLASSROOM and classroom_ids:
            raise InvalidAnnouncementAudienceError()
        if audience is AnnouncementAudience.CLASSROOM and not classroom_ids:
            raise InvalidAnnouncementAudienceError()

        author = await self._session.get(User, author_user_id)
        if author is None:
            raise AnnouncementAuthorNotFoundError()

        if classroom_ids:
            existing = await self._existing_classroom_ids(classroom_ids)
            if set(classroom_ids) - existing:
                raise AnnouncementClassroomReferenceError()

        announcement = Announcement(
            title=title,
            content=content,
            author_user_id=author_user_id,
            audience=audience,
        )
        self._session.add(announcement)
        try:
            await self._session.flush()

            target_classroom_id: uuid.UUID
            for target_classroom_id in classroom_ids:
                self._session.add(
                    AnnouncementClassroom(
                        announcement_id=announcement.id,
                        classroom_id=target_classroom_id,
                    )
                )
            if classroom_ids:
                await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            if _matches_constraint(exc, _ANNOUNCEMENT_CLASSROOM_UNIQUE_CONSTRAINT):
                # classroom_ids is already de-duplicated by the schema
                # layer (AnnouncementCreate), but the repository can be
                # called directly bypassing that — treat a duplicate
                # target the same way schema-level dedupe would have.
                raise InvalidAnnouncementAudienceError() from exc
            if "foreign key" in str(exc.orig).lower():
                raise AnnouncementClassroomReferenceError() from exc
            raise
        return announcement

    async def update(self, announcement: Announcement, **changes: object) -> Announcement:
        for field, value in changes.items():
            setattr(announcement, field, value)
        await self._session.flush()
        await self._session.refresh(announcement)
        return announcement

    async def deactivate(self, announcement: Announcement) -> Announcement:
        announcement.is_active = False
        await self._session.flush()
        await self._session.refresh(announcement)
        return announcement
