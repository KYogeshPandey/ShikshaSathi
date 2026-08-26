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
from app.modules.auth.email import OtpEmailSender
from app.modules.auth.errors import (
    DemoStudentLoginUnavailableError,
    ExpiredOtpChallengeError,
    InvalidCredentialsError,
    InvalidNewPasswordError,
    InvalidOtpChallengeError,
    InvalidPasswordResetGrantError,
    InvalidRefreshTokenError,
    OtpAttemptsExceededError,
    OtpDeliveryUnavailableError,
    OtpLoginNotEnabledError,
    OtpResendCooldownError,
)
from app.modules.auth.models import OtpChallenge, OtpPurpose
from app.modules.auth.repository import OtpChallengeRepository, RefreshSessionRepository
from app.modules.auth.security import (
    create_access_token,
    generate_login_otp,
    generate_password_reset_grant,
    generate_refresh_token,
    hash_login_otp,
    hash_password,
    hash_password_reset_grant,
    hash_password_reset_otp,
    hash_refresh_token,
    validate_password_strength,
    verify_login_otp,
    verify_password,
    verify_password_reset_grant,
    verify_password_reset_otp,
    verify_password_timing_safe_dummy,
)
from app.modules.profiles.repository import StudentProfileRepository
from app.modules.users.models import User, UserRole
from app.modules.users.normalization import normalize_email
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


@dataclass(frozen=True)
class OtpChallengeResult:
    challenge_id: uuid.UUID
    expires_in_seconds: int
    resend_available_in_seconds: int


@dataclass(frozen=True)
class PasswordResetRequestResult:
    expires_in_seconds: int
    resend_available_in_seconds: int


@dataclass(frozen=True)
class PasswordResetGrantResult:
    reset_id: uuid.UUID
    reset_token: str
    expires_in_seconds: int


class AuthService:
    def __init__(self, *, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._users = UserRepository(session)
        self._student_profiles = StudentProfileRepository(session)
        self._refresh_sessions = RefreshSessionRepository(session)
        self._otp_challenges = OtpChallengeRepository(session)

    async def login_demo_student(self) -> AuthResult:
        """Issue the normal session pair for one configured, valid Student account."""
        configured_email = self._settings.DEMO_STUDENT_LOGIN_EMAIL
        if not self._settings.DEMO_STUDENT_LOGIN_ENABLED or configured_email is None:
            raise DemoStudentLoginUnavailableError()

        user = await self._users.get_by_email(normalize_email(str(configured_email)))
        if user is None or not user.is_active or user.role is not UserRole.STUDENT:
            raise DemoStudentLoginUnavailableError()

        profile = await self._student_profiles.get_by_user_id(user.id)
        if profile is None or not profile.is_active:
            raise DemoStudentLoginUnavailableError()

        result = await self._issue_token_pair(user)
        await self._session.commit()
        logger.info("demo_student_login_succeeded", user_id=str(user.id))
        return result

    async def login(self, *, email: str, password: str) -> AuthResult:
        """Authenticate by email/password and issue a new token pair.

        ``email`` must already be normalized by the caller (see
        app/modules/auth/schemas.py's ``LoginRequest``). Every failure
        mode — unknown email, wrong password, deactivated account —
        raises the same ``InvalidCredentialsError`` (see that class's
        docstring for why).
        """
        user = await self._validate_credentials(email=email, password=password)
        result = await self._issue_token_pair(user)
        await self._session.commit()
        logger.info("login_succeeded", user_id=str(user.id))
        return result

    async def begin_otp_login(
        self,
        *,
        email: str,
        password: str,
        email_sender: OtpEmailSender,
    ) -> OtpChallengeResult:
        """Validate credentials, replace any active challenge, and send a code."""
        if not self._settings.LOGIN_OTP_ENABLED:
            raise OtpLoginNotEnabledError()
        user = await self._validate_credentials(email=email, password=password)
        now = datetime.now(UTC)
        await self._otp_challenges.lock_user(user.id)
        await self._otp_challenges.invalidate_active_for_user(
            user_id=user.id,
            purpose=OtpPurpose.LOGIN,
            now=now,
        )
        challenge, raw_otp = await self._create_otp_challenge(
            user=user,
            purpose=OtpPurpose.LOGIN,
            now=now,
        )
        await self._session.commit()
        await self._deliver_otp(
            challenge=challenge,
            recipient=user.email,
            raw_otp=raw_otp,
            email_sender=email_sender,
        )
        logger.info("otp_challenge_created", user_id=str(user.id), challenge_id=str(challenge.id))
        return self._otp_result(challenge, now=now)

    async def verify_otp(
        self,
        *,
        challenge_id: uuid.UUID,
        otp: str,
    ) -> AuthResult:
        """Consume a correct active OTP and only then issue the normal session pair."""
        self._require_otp_enabled()
        challenge = await self._otp_challenges.get_by_id(challenge_id, for_update=True)
        now = datetime.now(UTC)
        self._require_usable_challenge(challenge)
        assert challenge is not None
        if _as_aware_utc(challenge.expires_at) <= now:
            # Keep the expired row replaceable by the resend endpoint. Its
            # timestamp already makes it unusable for verification.
            raise ExpiredOtpChallengeError()

        if not verify_login_otp(
            challenge_id=challenge.id,
            otp=otp,
            expected_hash=challenge.otp_hash,
            settings=self._settings,
        ):
            exhausted = await self._otp_challenges.record_failed_attempt(challenge, now=now)
            await self._session.commit()
            if exhausted:
                raise OtpAttemptsExceededError()
            raise InvalidOtpChallengeError()

        user = await self._users.get_by_id(challenge.user_id)
        if user is None or not user.is_active:
            await self._otp_challenges.invalidate(challenge, now=now)
            await self._session.commit()
            raise InvalidOtpChallengeError()

        await self._otp_challenges.consume(challenge, now=now)
        result = await self._issue_token_pair(user)
        await self._session.commit()
        logger.info(
            "otp_login_succeeded",
            user_id=str(user.id),
            challenge_id=str(challenge.id),
        )
        return result

    async def resend_otp(
        self,
        *,
        challenge_id: uuid.UUID,
        email_sender: OtpEmailSender,
    ) -> OtpChallengeResult:
        """Replace an active challenge after its resend cooldown."""
        self._require_otp_enabled()
        existing = await self._otp_challenges.get_by_id(challenge_id)
        if existing is None:
            raise InvalidOtpChallengeError()
        await self._otp_challenges.lock_user(existing.user_id)
        existing = await self._otp_challenges.get_by_id(challenge_id, for_update=True)
        now = datetime.now(UTC)
        # An expired code may still be replaced; consumed/invalidated codes
        # may not. The cooldown remains authoritative in either case.
        self._require_usable_challenge(existing)
        assert existing is not None

        last_sent_at = _as_aware_utc(existing.last_sent_at)
        cooldown_ends = last_sent_at + timedelta(
            seconds=self._settings.LOGIN_OTP_RESEND_COOLDOWN_SECONDS
        )
        if cooldown_ends > now:
            remaining = max(1, int((cooldown_ends - now).total_seconds() + 0.999))
            raise OtpResendCooldownError(remaining)

        user = await self._users.get_by_id(existing.user_id)
        if user is None or not user.is_active:
            await self._otp_challenges.invalidate(existing, now=now)
            await self._session.commit()
            raise InvalidOtpChallengeError()

        await self._otp_challenges.invalidate(existing, now=now)
        challenge, raw_otp = await self._create_otp_challenge(
            user=user,
            purpose=OtpPurpose.LOGIN,
            now=now,
        )
        await self._session.commit()
        await self._deliver_otp(
            challenge=challenge,
            recipient=user.email,
            raw_otp=raw_otp,
            email_sender=email_sender,
        )
        logger.info(
            "otp_challenge_resent",
            user_id=str(user.id),
            challenge_id=str(challenge.id),
        )
        return self._otp_result(challenge, now=now)

    async def request_password_reset(
        self,
        *,
        email: str,
        email_sender: OtpEmailSender,
    ) -> PasswordResetRequestResult:
        """Create and deliver a reset challenge without disclosing account state."""
        user = await self._users.get_by_email(email)
        if user is None or not user.is_active:
            return self._password_reset_request_result()

        now = datetime.now(UTC)
        await self._otp_challenges.lock_user(user.id)
        await self._otp_challenges.invalidate_active_for_user(
            user_id=user.id,
            purpose=OtpPurpose.PASSWORD_RESET,
            now=now,
        )
        challenge, raw_otp = await self._create_otp_challenge(
            user=user,
            purpose=OtpPurpose.PASSWORD_RESET,
            now=now,
        )
        await self._session.commit()
        delivered = await self._deliver_password_reset_otp(
            challenge=challenge,
            recipient=user.email,
            raw_otp=raw_otp,
            email_sender=email_sender,
        )
        if delivered:
            logger.info(
                "password_reset_challenge_created",
                user_id=str(user.id),
                challenge_id=str(challenge.id),
            )
        return self._password_reset_request_result()

    async def resend_password_reset_otp(
        self,
        *,
        email: str,
        email_sender: OtpEmailSender,
    ) -> PasswordResetRequestResult:
        """Replace a reset OTP when allowed while keeping every response generic."""
        user = await self._users.get_by_email(email)
        if user is None or not user.is_active:
            return self._password_reset_request_result()

        now = datetime.now(UTC)
        await self._otp_challenges.lock_user(user.id)
        existing = await self._otp_challenges.get_active_for_user(
            user_id=user.id,
            purpose=OtpPurpose.PASSWORD_RESET,
            for_update=True,
        )
        if existing is not None:
            cooldown_ends = _as_aware_utc(existing.last_sent_at) + timedelta(
                seconds=self._settings.LOGIN_OTP_RESEND_COOLDOWN_SECONDS
            )
            if cooldown_ends > now:
                return self._password_reset_request_result()
            await self._otp_challenges.invalidate(existing, now=now)

        challenge, raw_otp = await self._create_otp_challenge(
            user=user,
            purpose=OtpPurpose.PASSWORD_RESET,
            now=now,
        )
        await self._session.commit()
        await self._deliver_password_reset_otp(
            challenge=challenge,
            recipient=user.email,
            raw_otp=raw_otp,
            email_sender=email_sender,
        )
        return self._password_reset_request_result()

    async def verify_password_reset_otp(
        self,
        *,
        email: str,
        otp: str,
    ) -> PasswordResetGrantResult:
        """Exchange a correct reset OTP for a short-lived, server-backed grant."""
        user = await self._users.get_by_email(email)
        if user is None or not user.is_active:
            raise InvalidOtpChallengeError()

        await self._otp_challenges.lock_user(user.id)
        challenge = await self._otp_challenges.get_active_for_user(
            user_id=user.id,
            purpose=OtpPurpose.PASSWORD_RESET,
            for_update=True,
        )
        now = datetime.now(UTC)
        self._require_usable_challenge(challenge, purpose=OtpPurpose.PASSWORD_RESET)
        assert challenge is not None
        if _as_aware_utc(challenge.expires_at) <= now:
            raise ExpiredOtpChallengeError()

        if not verify_password_reset_otp(
            challenge_id=challenge.id,
            otp=otp,
            expected_hash=challenge.otp_hash,
            settings=self._settings,
        ):
            exhausted = await self._otp_challenges.record_failed_attempt(challenge, now=now)
            await self._session.commit()
            if exhausted:
                raise OtpAttemptsExceededError()
            raise InvalidOtpChallengeError()

        raw_grant = generate_password_reset_grant()
        grant_expires_at = now + timedelta(seconds=self._settings.PASSWORD_RESET_GRANT_TTL_SECONDS)
        await self._otp_challenges.consume_for_password_reset(
            challenge,
            grant_hash=hash_password_reset_grant(
                challenge_id=challenge.id,
                grant=raw_grant,
                settings=self._settings,
            ),
            grant_expires_at=grant_expires_at,
            now=now,
        )
        await self._session.commit()
        return PasswordResetGrantResult(
            reset_id=challenge.id,
            reset_token=raw_grant,
            expires_in_seconds=self._settings.PASSWORD_RESET_GRANT_TTL_SECONDS,
        )

    async def confirm_password_reset(
        self,
        *,
        reset_id: uuid.UUID,
        reset_token: str,
        new_password: str,
    ) -> None:
        """Use a verified grant once, update the password, and revoke refresh sessions."""
        challenge = await self._otp_challenges.get_by_id(reset_id, for_update=True)
        now = datetime.now(UTC)
        if (
            challenge is None
            or challenge.purpose is not OtpPurpose.PASSWORD_RESET
            or challenge.consumed_at is None
            or challenge.invalidated_at is not None
            or _as_aware_utc(challenge.expires_at) <= now
            or not verify_password_reset_grant(
                challenge_id=challenge.id,
                grant=reset_token,
                expected_hash=challenge.otp_hash,
                settings=self._settings,
            )
        ):
            raise InvalidPasswordResetGrantError()

        user = await self._users.get_by_id(challenge.user_id)
        if user is None or not user.is_active:
            await self._otp_challenges.invalidate(challenge, now=now)
            await self._session.commit()
            raise InvalidPasswordResetGrantError()

        try:
            validate_password_strength(new_password)
        except ValueError as exc:
            raise InvalidNewPasswordError(str(exc)) from exc

        await self._users.update_password(user, password_hash=hash_password(new_password))
        await self._refresh_sessions.revoke_all_for_user(user.id, now=now)
        await self._otp_challenges.invalidate(challenge, now=now)
        await self._session.commit()
        logger.info(
            "password_reset_completed",
            user_id=str(user.id),
            challenge_id=str(challenge.id),
        )

    async def _validate_credentials(self, *, email: str, password: str) -> User:
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
        return user

    async def _create_otp_challenge(
        self,
        *,
        user: User,
        purpose: OtpPurpose,
        now: datetime,
    ) -> tuple[OtpChallenge, str]:
        challenge_id = uuid.uuid4()
        raw_otp = generate_login_otp()
        challenge = await self._otp_challenges.create(
            challenge_id=challenge_id,
            user_id=user.id,
            purpose=purpose,
            otp_hash=(
                hash_login_otp(
                    challenge_id=challenge_id,
                    otp=raw_otp,
                    settings=self._settings,
                )
                if purpose is OtpPurpose.LOGIN
                else hash_password_reset_otp(
                    challenge_id=challenge_id,
                    otp=raw_otp,
                    settings=self._settings,
                )
            ),
            expires_at=now + timedelta(seconds=self._settings.LOGIN_OTP_TTL_SECONDS),
            max_attempts=self._settings.LOGIN_OTP_MAX_ATTEMPTS,
            last_sent_at=now,
        )
        return challenge, raw_otp

    async def _deliver_otp(
        self,
        *,
        challenge: OtpChallenge,
        recipient: str,
        raw_otp: str,
        email_sender: OtpEmailSender,
    ) -> None:
        try:
            await email_sender.send_login_otp(
                recipient=recipient,
                otp=raw_otp,
                expires_in_minutes=self._settings.LOGIN_OTP_TTL_SECONDS // 60,
            )
        except Exception as exc:
            persisted = await self._otp_challenges.get_by_id(challenge.id, for_update=True)
            if persisted is not None and persisted.invalidated_at is None:
                await self._otp_challenges.invalidate(persisted, now=datetime.now(UTC))
                await self._session.commit()
            logger.error(
                "otp_delivery_failed",
                challenge_id=str(challenge.id),
                exc_type=type(exc).__name__,
            )
            raise OtpDeliveryUnavailableError() from exc

    async def _deliver_password_reset_otp(
        self,
        *,
        challenge: OtpChallenge,
        recipient: str,
        raw_otp: str,
        email_sender: OtpEmailSender,
    ) -> bool:
        try:
            await email_sender.send_password_reset_otp(
                recipient=recipient,
                otp=raw_otp,
                expires_in_minutes=self._settings.LOGIN_OTP_TTL_SECONDS // 60,
            )
            return True
        except Exception as exc:
            persisted = await self._otp_challenges.get_by_id(challenge.id, for_update=True)
            if persisted is not None and persisted.invalidated_at is None:
                await self._otp_challenges.invalidate(persisted, now=datetime.now(UTC))
                await self._session.commit()
            logger.error(
                "password_reset_delivery_failed",
                challenge_id=str(challenge.id),
                exc_type=type(exc).__name__,
            )
            return False

    def _require_otp_enabled(self) -> None:
        if not self._settings.LOGIN_OTP_ENABLED:
            raise OtpLoginNotEnabledError()

    def _require_usable_challenge(
        self,
        challenge: OtpChallenge | None,
        *,
        purpose: OtpPurpose = OtpPurpose.LOGIN,
    ) -> None:
        if (
            challenge is None
            or challenge.purpose is not purpose
            or challenge.consumed_at is not None
            or challenge.invalidated_at is not None
        ):
            raise InvalidOtpChallengeError()
        if challenge.attempt_count >= challenge.max_attempts:
            raise OtpAttemptsExceededError()

    def _password_reset_request_result(self) -> PasswordResetRequestResult:
        return PasswordResetRequestResult(
            expires_in_seconds=self._settings.LOGIN_OTP_TTL_SECONDS,
            resend_available_in_seconds=self._settings.LOGIN_OTP_RESEND_COOLDOWN_SECONDS,
        )

    def _otp_result(self, challenge: OtpChallenge, *, now: datetime) -> OtpChallengeResult:
        expires_in = max(1, int((_as_aware_utc(challenge.expires_at) - now).total_seconds()))
        return OtpChallengeResult(
            challenge_id=challenge.id,
            expires_in_seconds=expires_in,
            resend_available_in_seconds=self._settings.LOGIN_OTP_RESEND_COOLDOWN_SECONDS,
        )

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
