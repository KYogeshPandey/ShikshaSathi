"""Pure unit tests for app/modules/auth/security.py and normalization.py.

None of these need a real database or HTTP client — they exercise
password hashing, the password-strength policy, email normalization,
and JWT access-token creation/validation directly, so this file always
runs (unlike the database-backed suites, which skip gracefully without
a reachable PostgreSQL test instance — see app/tests/conftest.py).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import Settings
from app.modules.auth.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    validate_password_strength,
    verify_password,
)
from app.modules.users.normalization import normalize_email

_SETTINGS_KWARGS: dict[str, object] = {
    "_env_file": None,
    "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
    "POSTGRES_DB": "db",
    "POSTGRES_USER": "user",
    "POSTGRES_PASSWORD": "pass",
    "SECRET_KEY": "a" * 40,
}


def _settings(**overrides: object) -> Settings:
    return Settings(**{**_SETTINGS_KWARGS, **overrides})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Email normalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Admin@Example.com", "admin@example.com"),
        ("  spaced@example.com  ", "spaced@example.com"),
        ("MIXED.Case@Example.COM", "mixed.case@example.com"),
        ("already@lower.com", "already@lower.com"),
    ],
)
def test_normalize_email(raw: str, expected: str) -> None:
    assert normalize_email(raw) == expected


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def test_hash_password_is_salted_and_not_plaintext() -> None:
    hash_one = hash_password("a-real-password-1")
    hash_two = hash_password("a-real-password-1")
    assert hash_one != hash_two  # Argon2 salts each hash independently
    assert "a-real-password-1" not in hash_one


def test_verify_password_round_trip() -> None:
    password_hash = hash_password("correct-horse-battery-1")
    assert verify_password("correct-horse-battery-1", password_hash) is True


def test_verify_password_rejects_wrong_password() -> None:
    password_hash = hash_password("correct-horse-battery-1")
    assert verify_password("wrong-password-1", password_hash) is False


def test_verify_password_never_raises_on_garbage_hash() -> None:
    assert verify_password("anything", "not-a-real-argon2-hash") is False


# ---------------------------------------------------------------------------
# Password strength policy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "password",
    ["short1", "12345678901", "nodigitshere", "x" * 129 + "1"],
)
def test_validate_password_strength_rejects_weak_passwords(password: str) -> None:
    with pytest.raises(ValueError):
        validate_password_strength(password)


def test_validate_password_strength_accepts_reasonable_password() -> None:
    validate_password_strength("a-strong-real-password-1")  # must not raise


# ---------------------------------------------------------------------------
# Access tokens (JWT)
# ---------------------------------------------------------------------------


def test_create_and_decode_access_token_round_trip() -> None:
    settings = _settings()
    user_id = uuid.uuid4()
    token = create_access_token(user_id=user_id, settings=settings)
    payload = decode_access_token(token, settings=settings)
    assert payload["sub"] == str(user_id)
    assert payload["type"] == "access"
    assert "role" not in payload  # never trust a token-carried role


def test_access_token_has_no_role_claim() -> None:
    settings = _settings()
    token = create_access_token(user_id=uuid.uuid4(), settings=settings)
    # Decode without verification just to inspect claims directly.
    unverified = jwt.decode(token, options={"verify_signature": False})
    assert "role" not in unverified


def test_decode_access_token_rejects_expired_token() -> None:
    settings = _settings()
    expired_issued_at = datetime.now(UTC) - timedelta(hours=1)
    token = create_access_token(user_id=uuid.uuid4(), settings=settings, now=expired_issued_at)
    with pytest.raises(TokenError):
        decode_access_token(token, settings=settings)


def test_decode_access_token_rejects_malformed_token() -> None:
    settings = _settings()
    with pytest.raises(TokenError):
        decode_access_token("this-is-not-a-jwt", settings=settings)


def test_decode_access_token_rejects_wrong_signature() -> None:
    settings = _settings()
    token = create_access_token(user_id=uuid.uuid4(), settings=settings)
    other_settings = _settings(SECRET_KEY="b" * 40)
    with pytest.raises(TokenError):
        decode_access_token(token, settings=other_settings)


def test_decode_access_token_rejects_wrong_audience() -> None:
    settings = _settings()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "type": "access",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "jti": uuid.uuid4().hex,
            "iss": settings.JWT_ISSUER,
            "aud": "some-other-audience",
        },
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(TokenError):
        decode_access_token(token, settings=settings)


def test_decode_access_token_rejects_wrong_issuer() -> None:
    settings = _settings()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "type": "access",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "jti": uuid.uuid4().hex,
            "iss": "some-other-issuer",
            "aud": settings.JWT_AUDIENCE,
        },
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(TokenError):
        decode_access_token(token, settings=settings)


def test_decode_access_token_rejects_wrong_token_type() -> None:
    settings = _settings()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "type": "refresh",  # not "access"
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "jti": uuid.uuid4().hex,
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
        },
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(TokenError):
        decode_access_token(token, settings=settings)


def test_decode_access_token_rejects_missing_required_claims() -> None:
    settings = _settings()
    token = jwt.encode({"sub": str(uuid.uuid4())}, settings.SECRET_KEY, algorithm="HS256")
    with pytest.raises(TokenError):
        decode_access_token(token, settings=settings)


# ---------------------------------------------------------------------------
# Refresh tokens (opaque)
# ---------------------------------------------------------------------------


def test_generate_refresh_token_is_unique_and_high_entropy() -> None:
    first = generate_refresh_token()
    second = generate_refresh_token()
    assert first != second
    assert len(first) > 32


def test_hash_refresh_token_is_deterministic_and_one_way() -> None:
    raw = generate_refresh_token()
    assert hash_refresh_token(raw) == hash_refresh_token(raw)
    assert hash_refresh_token(raw) != raw


def test_hash_refresh_token_differs_for_different_inputs() -> None:
    assert hash_refresh_token(generate_refresh_token()) != hash_refresh_token(
        generate_refresh_token()
    )
