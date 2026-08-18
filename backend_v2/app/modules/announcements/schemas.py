"""Pydantic schemas for the announcements domain.

``AnnouncementRead`` cannot be built purely via ``from_attributes``
because ``classroom_ids`` is not a plain column on ``Announcement`` (no
ORM ``relationship()`` is declared in Stage 1 — see
``app.modules.announcements.models``' module docstring, matching the
same "no back-refs yet" choice made for ``TeacherAssignment``). Use
``AnnouncementRead.from_model`` to combine the ORM row with its
separately-queried classroom-id list.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.announcements.models import AnnouncementAudience

if TYPE_CHECKING:
    from app.modules.announcements.models import Announcement

_WHITESPACE_RUN = re.compile(r"\s+")


def _normalize_title(title: str) -> str:
    """Trim an announcement title and collapse internal whitespace runs.

    Duplicated (rather than imported) from
    ``app.modules.academics.normalization.normalize_name`` — same
    cross-module-import-avoidance rationale documented in
    ``app.modules.academics.models``'s ``_enum_values`` helper.
    """
    return _WHITESPACE_RUN.sub(" ", title.strip())


class AnnouncementCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    author_user_id: uuid.UUID
    audience: AnnouncementAudience
    classroom_ids: list[uuid.UUID] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def _normalize_title_field(cls, value: str) -> str:
        normalized = _normalize_title(value)
        if not normalized:
            raise ValueError("title must not be blank")
        return normalized

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("content must not be blank")
        return stripped

    @field_validator("classroom_ids")
    @classmethod
    def _dedupe_classroom_ids(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        # Order-preserving de-duplication: a caller listing the same
        # classroom twice is almost certainly a client-side mistake, not
        # a meaningful "twice as targeted" signal, so it is silently
        # collapsed rather than rejected outright.
        seen: set[uuid.UUID] = set()
        deduped: list[uuid.UUID] = []
        for classroom_id in value:
            if classroom_id not in seen:
                seen.add(classroom_id)
                deduped.append(classroom_id)
        return deduped

    @model_validator(mode="after")
    def _audience_matches_classroom_ids(self) -> AnnouncementCreate:
        # Re-checked at the repository layer too
        # (InvalidAnnouncementAudienceError) — belt-and-suspenders, same
        # pattern as TimetableEntryCreate's start/end validation.
        if self.audience is not AnnouncementAudience.CLASSROOM and self.classroom_ids:
            raise ValueError("only audience 'classroom' may include classroom_ids")
        if self.audience is AnnouncementAudience.CLASSROOM and not self.classroom_ids:
            raise ValueError("audience 'classroom' requires at least one classroom id")
        return self


class AnnouncementCreateRequest(BaseModel):
    """Public create body; the author is always the authenticated admin."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    audience: AnnouncementAudience
    classroom_ids: list[uuid.UUID] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def _normalize_title_field(cls, value: str) -> str:
        normalized = _normalize_title(value)
        if not normalized:
            raise ValueError("title must not be blank")
        return normalized

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("content must not be blank")
        return stripped

    @field_validator("classroom_ids")
    @classmethod
    def _dedupe_classroom_ids(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def _audience_matches_classroom_ids(self) -> AnnouncementCreateRequest:
        if self.audience is not AnnouncementAudience.CLASSROOM and self.classroom_ids:
            raise ValueError("only audience 'classroom' may include classroom_ids")
        if self.audience is AnnouncementAudience.CLASSROOM and not self.classroom_ids:
            raise ValueError("audience 'classroom' requires at least one classroom id")
        return self


class AnnouncementUpdate(BaseModel):
    """Update title/content/active state; audience is immutable.

    Changing ``audience``/``classroom_ids`` would require reconciling
    association rows. The current model policy uses deactivate-and-create
    for an audience replacement instead.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = Field(default=None, min_length=1)
    is_active: bool | None = Field(default=None)

    @field_validator("title")
    @classmethod
    def _normalize_title_field(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_title(value)
        if not normalized:
            raise ValueError("title must not be blank")
        return normalized

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("content must not be blank")
        return stripped

    @model_validator(mode="after")
    def _provided_fields_cannot_be_null(self) -> AnnouncementUpdate:
        for field_name in self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} must not be null")
        return self


class AnnouncementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    content: str
    author_user_id: uuid.UUID
    audience: AnnouncementAudience
    classroom_ids: list[uuid.UUID]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(
        cls, announcement: Announcement, classroom_ids: list[uuid.UUID]
    ) -> AnnouncementRead:
        """Combine an ``Announcement`` row with its separately-queried audience."""
        return cls(
            id=announcement.id,
            title=announcement.title,
            content=announcement.content,
            author_user_id=announcement.author_user_id,
            audience=announcement.audience,
            classroom_ids=classroom_ids,
            is_active=announcement.is_active,
            created_at=announcement.created_at,
            updated_at=announcement.updated_at,
        )
