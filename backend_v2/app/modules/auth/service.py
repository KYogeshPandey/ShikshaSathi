"""Login / refresh / logout orchestration.

Owns the transaction boundary for these operations (docs/ARCHITECTURE.md
§6): app/db/session.py's ``get_db_session`` guarantees rollback-on-error
and always closes the session, but deliberately never commits — that is
this service's job, at the end of each method, only once every step has
succeeded.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.auth.errors import InvalidCredentialsError, InvalidRefreshTokenError
from app.modules.auth.repository import RefreshSessionRepository
from app.modules.auth.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    verify_password,
    verify_password_timing_safe_dummy,
)
from app.modules.users.models import User
from app.modules.users.repository import UserRepository

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class AuthResult:
    """Everything a router needs to build a login/refresh response.

    ``refresh_token`` is the raw opaque token — present here only
    transiently, on its way into the HttpOnly cookie the router sets;
    it is never itself stored (only its hash is, in ``refresh_sessions``).
    ``session_id`` is that new session row's primary key, needed only
    internally by ``refresh()`` to record rotation lineage on the old
    session (``replaced_by_id``) — routers do not use it.
    """

    user: User
    access_token: str
    access_expires_in_seconds: int
    refresh_token: str
    refresh_expires_in_seconds: int
    session_id: uuid.UUID


class AuthService:
    def __init__(self, *, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._users = UserRepository(session)
        self._refresh_sessions = RefreshSessionRepository(session)

    async def login(self, *, email: str, password: str) -> AuthResult:
        """Authenticate by email/password and issue a new token pair.

        ``email`` must already be normalized by the caller (see
        app/modules/auth/schemas.py's ``LoginRequest``). Every failure
        mode — unknown email, wrong password, deactivated account —
        raises the same ``InvalidCredentialsError`` (see that class's
        docstring for why).
        """
        user = await self._users.get_by_email(email)
        if user is None:
            # Burn roughly the same amount of time a real verification
            # would take, so response timing does not disclose whether
            # the email exists (app/modules/auth/security.py).
            verify_password_timing_safe_dummy(password)
            raise InvalidCredentialsError()

        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsError()

        if not user.is_active:
            raise InvalidCredentialsError()

        result = await self._issue_token_pair(user)
        await self._session.commit()
        logger.info("login_succeeded", user_id=str(user.id))
        return result

    async def refresh(self, *, raw_refresh_token: str) -> AuthResult:
        """Validate, rotate, and exchange a refresh token for a new pair.

        Every failure mode raises ``InvalidRefreshTokenError``: unknown
        token, expired, already revoked (via logout), or reuse of an
        already-rotated token. Reuse of an already-rotated token is
        additionally treated as a possible compromise: every active
        session for that user is revoked, forcing a fresh login
        everywhere (instruction D: "reuse detection").
        """
        token_hash = hash_refresh_token(raw_refresh_token)
        existing = await self._refresh_sessions.get_by_token_hash(token_hash, for_update=True)
        if existing is None:
            raise InvalidRefreshTokenError()

        now = datetime.now(UTC)

        if existing.revoked_at is not None:
            if existing.replaced_by_id is not None:
                logger.warning(
                    "refresh_token_reuse_detected",
                    user_id=str(existing.user_id),
                    session_id=str(existing.id),
                )
                await self._refresh_sessions.revoke_all_for_user(existing.user_id, now=now)
                await self._session.commit()
            raise InvalidRefreshTokenError()

        if _as_aware_utc(existing.expires_at) <= now:
            raise InvalidRefreshTokenError()

        user = await self._users.get_by_id(existing.user_id)
        if user is None or not user.is_active:
            raise InvalidRefreshTokenError()

        result = await self._issue_token_pair(user)
        await self._refresh_sessions.revoke(existing, now=now, replaced_by_id=result.session_id)
        await self._session.commit()
        logger.info("refresh_succeeded", user_id=str(user.id))
        return result

    async def logout(self, *, raw_refresh_token: str | None) -> None:
        """Revoke the session for ``raw_refresh_token``, if any.

        Idempotent by design (instruction E/K: "repeated logout handled
        safely"): a missing, already-revoked, or unknown token is a
        silent no-op rather than an error — the caller's goal (no
        longer being logged in) is already satisfied either way.
        """
        if not raw_refresh_token:
            return
        token_hash = hash_refresh_token(raw_refresh_token)
        existing = await self._refresh_sessions.get_by_token_hash(token_hash)
        if existing is not None and existing.revoked_at is None:
            await self._refresh_sessions.revoke(existing, now=datetime.now(UTC))
            await self._session.commit()
            logger.info("logout_succeeded", user_id=str(existing.user_id))

    async def _issue_token_pair(self, user: User) -> AuthResult:
        access_token = create_access_token(user_id=user.id, settings=self._settings)
        raw_refresh = generate_refresh_token()
        expires_at = datetime.now(UTC) + timedelta(days=self._settings.REFRESH_TOKEN_EXPIRE_DAYS)
        session_row = await self._refresh_sessions.create(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=expires_at,
        )
        return AuthResult(
            user=user,
            access_token=access_token,
            access_expires_in_seconds=self._settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            refresh_token=raw_refresh,
            refresh_expires_in_seconds=self._settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
            session_id=session_row.id,
        )


def _as_aware_utc(value: datetime) -> datetime:
    """Defensively normalize a possibly-naive DB timestamp to aware UTC.

    ``DateTime(timezone=True)`` columns round-trip as aware datetimes
    through asyncpg in normal operation; this guards the comparison in
    ``refresh`` above against ever raising ``TypeError`` if a value
    somehow comes back naive (e.g. a differently-configured test
    fixture) instead of silently miscomparing.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
