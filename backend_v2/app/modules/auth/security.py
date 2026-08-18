"""Password hashing, JWT access tokens, and opaque refresh-token helpers.

Design decisions (full rationale in
docs/adr/0006-identity-and-auth-foundations.md):

- **Password hashing: Argon2id** via ``argon2-cffi``'s high-level
  ``PasswordHasher``, OWASP's current first recommendation for new
  applications and a strict improvement over the legacy app's
  Werkzeug/scrypt hashing (docs/AUDIT.md §2.3's one positive finding —
  kept in spirit, upgraded in algorithm, per
  docs/LEGACY_MIGRATION_MAP.md's "Refactor" decision for
  Authentication).
- **Access tokens are JWTs** — short-lived, stateless, verified without
  a database round trip for signature/expiry/claims, but the resolved
  user is still always re-loaded from PostgreSQL by the auth dependency
  (app/modules/auth/dependencies.py) before any authorization decision
  is made, so role/active-state changes take effect immediately
  (instruction C/F) rather than waiting for token expiry.
- **Refresh tokens are opaque random strings, not JWTs.** Only a
  SHA-256 digest of the raw token is ever persisted (see
  app/modules/auth/repository.py) — a stolen database dump cannot be
  used to derive a working refresh token. Session metadata (owner,
  expiry, revocation, rotation lineage) lives entirely in the
  ``refresh_sessions`` table (app/modules/auth/models.py), which is
  what makes real revocation possible; a self-contained JWT refresh
  token would need its own server-side blacklist to be revocable at
  all, which is strictly more moving parts for no benefit here.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError

from app.core.config import Settings

# ---------------------------------------------------------------------------
# Password hashing (Argon2id, library defaults — instruction B: "password
# hashing configuration only where genuinely required"; argon2-cffi's
# out-of-the-box PasswordHasher() defaults are the library-recommended,
# actively-maintained values and are not overridden here).
# ---------------------------------------------------------------------------

_password_hasher = PasswordHasher()

_MIN_PASSWORD_LENGTH = 10
_MAX_PASSWORD_LENGTH = 128

# A password hash computed once, over a fixed non-secret string, and
# verified against on every login attempt for an email that does not
# exist. This keeps the login endpoint's response time for "unknown
# email" roughly the same shape as "wrong password" — Argon2id
# verification is the dominant cost in either path — so response
# timing does not become a side channel for account enumeration
# (instruction B: "Avoid account-enumeration details in login errors").
_TIMING_SAFETY_DUMMY_HASH = _password_hasher.hash("not-a-real-password-used-only-for-timing-safety")


def hash_password(raw_password: str) -> str:
    """Hash ``raw_password`` with Argon2id. Never call this on already-hashed input."""
    return _password_hasher.hash(raw_password)


def verify_password(raw_password: str, password_hash: str) -> bool:
    """Return True iff ``raw_password`` matches ``password_hash``. Never raises."""
    try:
        return _password_hasher.verify(password_hash, raw_password)
    except (VerifyMismatchError, InvalidHash, ValueError):
        return False


def verify_password_timing_safe_dummy(raw_password: str) -> None:
    """Burn roughly one Argon2id verification's worth of time, result discarded.

    Called by the login flow when the submitted email does not match
    any user, instead of returning immediately — see
    ``_TIMING_SAFETY_DUMMY_HASH`` above.
    """
    verify_password(raw_password, _TIMING_SAFETY_DUMMY_HASH)


def validate_password_strength(password: str) -> None:
    """Raise ``ValueError`` if ``password`` does not meet the account-creation policy.

    Applied only where an account's password is being *set* (the admin
    bootstrap script today; any future admin/self-registration flow) —
    never applied to a *login* attempt, which must still be checked
    against whatever hash already exists even if that password would
    no longer satisfy today's policy.
    """
    if len(password) < _MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {_MIN_PASSWORD_LENGTH} characters.")
    if len(password) > _MAX_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at most {_MAX_PASSWORD_LENGTH} characters.")
    if not any(character.isalpha() for character in password):
        raise ValueError("Password must contain at least one letter.")
    if not any(character.isdigit() for character in password):
        raise ValueError("Password must contain at least one digit.")


# ---------------------------------------------------------------------------
# Access tokens (JWT)
# ---------------------------------------------------------------------------


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


class TokenError(Exception):
    """Raised for any malformed/expired/mis-signed/wrong-type access token.

    Deliberately the *only* exception type this module raises for
    token problems — app/modules/auth/dependencies.py maps it to a
    single sanitized 401 without ever surfacing the underlying PyJWT
    exception class or message to the client (instruction C: "Do not
    expose raw JWT-library exceptions to clients.").
    """


def create_access_token(
    *,
    user_id: uuid.UUID,
    settings: Settings,
    now: datetime | None = None,
) -> str:
    """Issue a signed access token for ``user_id``.

    Deliberately carries no ``role`` claim: authorization always reads
    the role fresh from PostgreSQL (instruction F), so there is no
    stale-role claim for any future code path to be tempted to trust
    instead.

    ``now`` is accepted explicitly (defaulting to the real current
    time) purely so tests can mint an already-expired token
    deterministically, without sleeping or monkeypatching the clock.
    """
    issued_at = now or datetime.now(UTC)
    expires_at = issued_at + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": TokenType.ACCESS.value,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": uuid.uuid4().hex,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str, *, settings: Settings) -> dict[str, Any]:
    """Decode and fully validate ``token``.

    Rejects malformed, expired, incorrectly-signed, wrong-audience,
    wrong-issuer, and wrong-token-type tokens — every case raises the
    single ``TokenError`` above, never a raw ``jwt.PyJWTError``.
    """
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
            options={"require": ["exp", "iat", "sub", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError("Invalid or expired access token.") from exc

    if payload.get("type") != TokenType.ACCESS.value:
        raise TokenError("Token is not an access token.")
    return payload


# ---------------------------------------------------------------------------
# Refresh tokens (opaque, not JWT — see module docstring)
# ---------------------------------------------------------------------------

_REFRESH_TOKEN_BYTES = 48  # ~64 URL-safe characters; comfortably high entropy


def generate_refresh_token() -> str:
    """Return a new, high-entropy, URL-safe opaque refresh token."""
    return secrets.token_urlsafe(_REFRESH_TOKEN_BYTES)


def hash_refresh_token(raw_token: str) -> str:
    """Return the SHA-256 hex digest stored in place of the raw refresh token.

    A keyed HMAC was considered and rejected for Phase 2: the raw
    token already has 48 bytes of ``secrets``-sourced entropy, so an
    attacker who has *only* the stored digest cannot feasibly recover
    it either way, and a plain digest avoids introducing a second
    secret-bearing setting (instruction I).
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
