"""Repository for the ``users`` table.

Thin, single-aggregate data access (docs/ARCHITECTURE.md §6:
"Repository-per-aggregate over raw SQLAlchemy sessions; no direct ORM
queries inside routers"). Callers (app/modules/auth/service.py,
scripts/bootstrap_admin.py) own the session's transaction boundary —
this class never calls ``commit()`` itself, only ``flush()`` where a
generated primary key or constraint violation needs to surface before
the caller decides to commit or roll back.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.errors import EmailAlreadyExistsError
from app.modules.users.models import User, UserRole

_EMAIL_UNIQUE_CONSTRAINT = "uq_users_email"


def _is_email_unique_violation(exc: IntegrityError) -> bool:
    """Return whether ``exc`` is specifically the users-email conflict.

    SQLAlchemy's asyncpg adapter exposes the PostgreSQL constraint name
    on the wrapped driver exception. The message fallback keeps this
    stable across adapter patch versions without mapping unrelated
    integrity failures to an email-conflict response.
    """
    candidates = (
        exc.orig,
        getattr(exc.orig, "__cause__", None),
        getattr(exc.orig, "__context__", None),
    )
    for candidate in candidates:
        if getattr(candidate, "constraint_name", None) == _EMAIL_UNIQUE_CONSTRAINT:
            return True
    return _EMAIL_UNIQUE_CONSTRAINT in str(exc.orig)


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        """Look up by email. ``email`` must already be normalized by the caller."""
        stmt = select(User).where(User.email == email)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_role(
        self,
        role: UserRole,
        *,
        include_inactive: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[User]:
        stmt = (
            select(User)
            .where(User.role == role)
            .order_by(User.full_name, User.email, User.id)
            .limit(limit)
            .offset(offset)
        )
        if not include_inactive:
            stmt = stmt.where(User.is_active.is_(True))
        return list((await self._session.execute(stmt)).scalars().all())

    async def count_by_role(self, role: UserRole, *, include_inactive: bool = False) -> int:
        stmt = select(func.count()).select_from(User).where(User.role == role)
        if not include_inactive:
            stmt = stmt.where(User.is_active.is_(True))
        return int((await self._session.execute(stmt)).scalar_one())

    async def create(
        self,
        *,
        email: str,
        password_hash: str,
        full_name: str,
        role: UserRole,
        is_active: bool = True,
    ) -> User:
        """Create a new user. ``email`` must already be normalized.

        Raises ``EmailAlreadyExistsError`` (rolling back first) on a
        unique-constraint conflict, instead of letting the raw
        ``IntegrityError`` propagate — see instruction G.
        """
        user = User(
            email=email,
            password_hash=password_hash,
            full_name=full_name,
            role=role,
            is_active=is_active,
        )
        self._session.add(user)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            if _is_email_unique_violation(exc):
                raise EmailAlreadyExistsError() from exc
            raise
        return user

    async def update_password(self, user: User, *, password_hash: str) -> None:
        """Replace a user's password digest inside the caller-owned transaction."""
        user.password_hash = password_hash
        await self._session.flush()
