"""Repository for the ``refresh_sessions`` table.

Same conventions as app/modules/users/repository.py: thin, single-
aggregate data access, no ``commit()`` calls — the caller
(app/modules/auth/service.py) owns the transaction boundary.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import OtpChallenge, OtpPurpose, RefreshSession
from app.modules.users.models import User


class RefreshSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_token_hash(
        self, token_hash: str, *, for_update: bool = False
    ) -> RefreshSession | None:
        """Return a refresh session, optionally locking it for atomic rotation.

        ``for_update=True`` emits ``SELECT ... FOR UPDATE``. The refresh
        service uses this inside its transaction so two concurrent requests
        cannot both consume the same active token.
        """
        stmt = select(RefreshSession).where(RefreshSession.token_hash == token_hash)
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self, *, user_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> RefreshSession:
        session_row = RefreshSession(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self._session.add(session_row)
        await self._session.flush()
        return session_row

    async def revoke(
        self,
        session_row: RefreshSession,
        *,
        now: datetime,
        replaced_by_id: uuid.UUID | None = None,
    ) -> None:
        """Mark ``session_row`` revoked, optionally recording its replacement.

        ``replaced_by_id`` set means "revoked because rotated" (a
        subsequent presentation of this session's raw token is reuse of
        an already-exchanged token); left ``None`` means "revoked
        directly" (logout, or a defensive mass-revocation — see
        ``revoke_all_for_user``). This distinction is what lets
        app/modules/auth/service.py tell the two cases apart.
        """
        session_row.revoked_at = now
        session_row.replaced_by_id = replaced_by_id
        await self._session.flush()

    async def revoke_all_for_user(self, user_id: uuid.UUID, *, now: datetime) -> None:
        """Revoke every currently-active session for ``user_id``.

        Used defensively when refresh-token reuse is detected
        (app/modules/auth/service.py) — the whole session family for
        that user is invalidated, not just the one reused token, since
        reuse of a rotated token is treated as a signal the token may
        have been stolen.
        """
        stmt = (
            update(RefreshSession)
            .where(RefreshSession.user_id == user_id, RefreshSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await self._session.execute(stmt)
        await self._session.flush()


class OtpChallengeRepository:
    """Persistence boundary for expiring, one-time OTP challenges."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(
        self,
        challenge_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> OtpChallenge | None:
        stmt = select(OtpChallenge).where(OtpChallenge.id == challenge_id)
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def lock_user(self, user_id: uuid.UUID) -> None:
        """Serialize challenge replacement for one user."""
        await self._session.execute(select(User.id).where(User.id == user_id).with_for_update())

    async def invalidate_active_for_user(
        self,
        *,
        user_id: uuid.UUID,
        purpose: OtpPurpose,
        now: datetime,
    ) -> None:
        await self._session.execute(
            update(OtpChallenge)
            .where(
                OtpChallenge.user_id == user_id,
                OtpChallenge.purpose == purpose,
                OtpChallenge.consumed_at.is_(None),
                OtpChallenge.invalidated_at.is_(None),
            )
            .values(invalidated_at=now)
        )
        await self._session.flush()

    async def create(
        self,
        *,
        challenge_id: uuid.UUID,
        user_id: uuid.UUID,
        otp_hash: str,
        expires_at: datetime,
        max_attempts: int,
        last_sent_at: datetime,
    ) -> OtpChallenge:
        challenge = OtpChallenge(
            id=challenge_id,
            user_id=user_id,
            purpose=OtpPurpose.LOGIN,
            otp_hash=otp_hash,
            expires_at=expires_at,
            max_attempts=max_attempts,
            last_sent_at=last_sent_at,
        )
        self._session.add(challenge)
        await self._session.flush()
        return challenge

    async def record_failed_attempt(
        self,
        challenge: OtpChallenge,
        *,
        now: datetime,
    ) -> bool:
        challenge.attempt_count += 1
        exhausted = challenge.attempt_count >= challenge.max_attempts
        if exhausted:
            challenge.invalidated_at = now
        await self._session.flush()
        return exhausted

    async def consume(self, challenge: OtpChallenge, *, now: datetime) -> None:
        challenge.consumed_at = now
        await self._session.flush()

    async def invalidate(self, challenge: OtpChallenge, *, now: datetime) -> None:
        challenge.invalidated_at = now
        await self._session.flush()


__all__ = ["OtpChallengeRepository", "RefreshSessionRepository"]
