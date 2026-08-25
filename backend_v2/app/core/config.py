"""Centralized application settings.

All runtime configuration is defined here, as a single Pydantic Settings
model. Nothing else in the application should call ``os.getenv`` directly
— this replaces the legacy app's pattern of two scattered ``os.getenv``
calls, one of which had an insecure inline fallback for the JWT secret
(see docs/AUDIT.md §1.8 / §2.3, Critical finding C2).

Design notes:

- Secrets (``SECRET_KEY``, ``DATABASE_URL``, ``POSTGRES_PASSWORD``) have
  no fallback defaults. Missing or invalid values fail loudly at startup
  rather than silently falling back to something insecure.
- ``SECRET_KEY`` is validated for minimum length and rejected outright if
  it matches a known placeholder (including the legacy app's own
  ``"change_this_in_env"`` fallback).
- ``APP_ENV=production`` enables additional checks (no DEBUG, no
  wildcard/empty CORS) that do not apply to development or testing.
- Sensitive fields are marked ``repr=False`` so a stray ``print(settings)``
  or an unguarded log call can never dump a secret. Application code must
  still never log a whole ``Settings`` instance — see app/core/logging.py.
- ``get_settings()`` is a cached provider used as a FastAPI dependency.
  Tests construct ``Settings(...)`` directly with explicit keyword
  arguments (which take precedence over both the real process
  environment and any ``.env`` file — pydantic-settings' documented
  source-priority order), so the test suite never depends on the
  developer's real environment. See app/tests/conftest.py.
"""

from __future__ import annotations

import json
from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import EmailStr, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Known-bad SECRET_KEY values that must never be accepted, regardless of
# environment. Includes the legacy app's own insecure fallback (AUDIT.md
# §2.3 / Critical C2: "change_this_in_env") and the placeholder shipped in
# the legacy backend/.env.example ("replace_with_a_long_random_value").
_PLACEHOLDER_SECRETS = frozenset(
    {
        "change_this_in_env",
        "changeme",
        "change-me",
        "change_me",
        "change_me_generate_your_own_32_plus_char_random_secret_value",
        "secret",
        "secretkey",
        "your-secret-key",
        "your-secret-key-here",
        "replace_with_a_long_random_value",
        "supersecret",
        "insecure",
        "please-change-me",
        "development",
        "test",
        "testing",
    }
)

_MIN_SECRET_LENGTH = 32


class Environment(StrEnum):
    """Deployment environment. Controls production-only safety checks."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class FaceRecognitionProvider(StrEnum):
    """Which face-recognition provider implementation is active, if any.

    Rebuild Phase 5 Stage 1 (docs/adr/0005-face-recognition-provider-pending.md,
    Accepted) selected server-side local Python inference as the MVP
    architecture. Phase 5 Stage 3 is what actually implements it — see
    ``app/modules/face_recognition/provider_factory.py``. ``NONE`` keeps
    the feature structurally inert (no provider is loaded, no model file
    is read) — the only value a deployment that has not yet obtained
    model artifacts should use. ``SERVER_SIDE_LOCAL`` is the real,
    Stage-3-backed value: YuNet (OpenCV) detection + dlib ResNet
    embedding + local cosine-similarity matching, all in-process, no
    hosted API call ever made.
    """

    NONE = "none"
    SERVER_SIDE_LOCAL = "server_side_local"


class Settings(BaseSettings):
    """Single source of truth for backend_v2 configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- Application metadata ------------------------------------------------
    APP_NAME: str = "ShikshaSathi API"
    APP_ENV: Environment = Environment.DEVELOPMENT
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # --- Database --------------------------------------------------------------
    DATABASE_URL: str = Field(repr=False)
    DATABASE_ECHO: bool = False

    # --- Logging -----------------------------------------------------------------
    LOG_LEVEL: str = "INFO"

    # --- Security ----------------------------------------------------------------
    SECRET_KEY: str = Field(repr=False)

    # --- CORS and request-boundary security ----------------------------------------
    CORS_ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # Host-header allow-list enforced by Starlette's TrustedHostMiddleware.
    # Local/test names are safe defaults; a real deployment adds its public
    # hostname explicitly. Wildcards are rejected in production below.
    TRUSTED_HOSTS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "testserver"]
    )

    # Only POST /auth/login is counted. The production image runs one Uvicorn
    # worker, so this process-local fixed-window limiter is authoritative for
    # the shipped Compose topology.
    LOGIN_RATE_LIMIT_ATTEMPTS: int = Field(default=5, ge=1, le=1000)
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, ge=1, le=3600)

    # --- Request correlation ---------------------------------------------------
    REQUEST_ID_HEADER: str = "X-Request-ID"

    # --- Authentication (Phase 2) ------------------------------------------------
    # JWT access tokens are signed with the same validated SECRET_KEY above
    # rather than a second, competing secret setting (instruction I: "Do
    # not duplicate competing secret settings without a documented
    # reason") — see docs/adr/0006-identity-and-auth-foundations.md.
    # Refresh tokens are NOT JWTs (see app/modules/auth/security.py) and so
    # have no signing algorithm of their own.
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "shikshasathi-v2"
    JWT_AUDIENCE: str = "shikshasathi-v2-clients"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Refresh token transport: an HttpOnly cookie, scoped to the auth
    # router's path only (see app/modules/auth/router.py), never
    # exposed to client-side JavaScript. `REFRESH_TOKEN_COOKIE_SECURE`
    # defaults to True; it must remain True whenever APP_ENV=production
    # (enforced below) and is explicitly relaxed to False only in
    # development/testing `.env` files, since browsers may decline to
    # persist a `Secure` cookie over a plain `http://localhost` origin.
    REFRESH_TOKEN_COOKIE_NAME: str = "refresh_token"
    REFRESH_TOKEN_COOKIE_SECURE: bool = True
    REFRESH_TOKEN_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    REFRESH_TOKEN_COOKIE_DOMAIN: str | None = None

    # --- Optional email OTP login (Milestone 4C) -----------------------------
    # Disabled by default, preserving the current production login until an
    # operator deliberately configures a delivery adapter.
    LOGIN_OTP_ENABLED: bool = False
    LOGIN_OTP_TTL_SECONDS: int = Field(default=600, ge=300, le=900)
    LOGIN_OTP_MAX_ATTEMPTS: int = Field(default=5, ge=1, le=10)
    LOGIN_OTP_RESEND_COOLDOWN_SECONDS: int = Field(default=60, ge=30, le=300)
    OTP_VERIFY_RATE_LIMIT_ATTEMPTS: int = Field(default=10, ge=1, le=100)
    OTP_VERIFY_RATE_LIMIT_WINDOW_SECONDS: int = Field(default=300, ge=30, le=3600)
    OTP_RESEND_RATE_LIMIT_ATTEMPTS: int = Field(default=5, ge=1, le=50)
    OTP_RESEND_RATE_LIMIT_WINDOW_SECONDS: int = Field(default=300, ge=30, le=3600)
    PASSWORD_RESET_GRANT_TTL_SECONDS: int = Field(default=300, ge=60, le=900)
    PASSWORD_RESET_REQUEST_RATE_LIMIT_ATTEMPTS: int = Field(default=5, ge=1, le=50)
    PASSWORD_RESET_REQUEST_RATE_LIMIT_WINDOW_SECONDS: int = Field(default=300, ge=30, le=3600)
    PASSWORD_RESET_CONFIRM_RATE_LIMIT_ATTEMPTS: int = Field(default=5, ge=1, le=50)
    PASSWORD_RESET_CONFIRM_RATE_LIMIT_WINDOW_SECONDS: int = Field(default=300, ge=30, le=3600)
    OTP_EMAIL_PROVIDER: Literal["none", "smtp", "brevo_api", "development_log"] = "none"
    BREVO_API_KEY: str | None = Field(default=None, repr=False)
    BREVO_API_TIMEOUT_SECONDS: int = Field(default=20, ge=1, le=60)
    SMTP_HOST: str | None = None
    SMTP_PORT: int = Field(default=587, ge=1, le=65535)
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = Field(default=None, repr=False)
    SMTP_FROM_EMAIL: EmailStr | None = None
    SMTP_STARTTLS: bool = True
    SMTP_USE_SSL: bool = False
    SMTP_TIMEOUT_SECONDS: int = Field(default=10, ge=1, le=60)

    # --- Admin bootstrap (Phase 2) -----------------------------------------------
    # Consumed ONLY by scripts/bootstrap_admin.py — never read by the
    # running API itself, and never given a real value here or in any
    # committed .env.example. Leave unset to be prompted interactively
    # (email via input(), password via getpass — never echoed or logged).
    ADMIN_BOOTSTRAP_EMAIL: str | None = None
    ADMIN_BOOTSTRAP_PASSWORD: str | None = Field(default=None, repr=False)

    # --- Reproducible demo dataset (Milestone 4A) -----------------------------
    # Consumed only by scripts/seed_demo_data.py. Demo identities default to
    # non-deliverable `.example` addresses in the seed manifest; these narrow
    # overrides make selected accounts usable with a real OTP inbox without
    # committing personal addresses. Production writes require an explicit,
    # operator-controlled opt-in and are never triggered at application startup.
    DEMO_SEED_PASSWORD: str | None = Field(default=None, repr=False)
    DEMO_SEED_ALLOW_PRODUCTION: bool = False
    DEMO_ADMIN_EMAIL: str = "admin@demo.shikshasathi.example"
    DEMO_TEACHER_ONE_EMAIL: str = "teacher.one@demo.shikshasathi.example"
    DEMO_TEACHER_TWO_EMAIL: str = "teacher.two@demo.shikshasathi.example"
    DEMO_STUDENT_ONE_EMAIL: str = "student.01@demo.shikshasathi.example"

    # --- Postgres ------------------------------------------------------------------
    # Consumed directly by the `postgres` Compose service; DATABASE_URL
    # above is what this application actually connects with (see
    # docs/ARCHITECTURE.md and docker-compose.yml).
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str = Field(repr=False)

    # --- Face recognition (Phase 5 Stage 1: provider-neutral foundation) -------
    # No detector/embedder/matcher is implemented yet — see
    # app/modules/face_recognition/ and
    # docs/adr/0005-face-recognition-provider-pending.md (Accepted in Stage
    # 1, selecting server-side local Python inference as the target MVP
    # architecture). Every field below is read only by Stage 3+ code that
    # does not exist yet; defaults keep the feature inert
    # (``FACE_RECOGNITION_PROVIDER=none``) until deliberately enabled, and
    # no value here names a specific vendored model file — Stage 1 does
    # not download or commit any model weights.
    FACE_RECOGNITION_PROVIDER: FaceRecognitionProvider = FaceRecognitionProvider.NONE
    # Opaque identifiers (e.g. a filename or registry key) for the future
    # detector/embedder models. Deliberately unset by default — required
    # only once FACE_RECOGNITION_PROVIDER is no longer "none" (enforced
    # below), so a real deployment cannot silently "half-enable" the
    # feature with a provider chosen but no model identified.
    FACE_DETECTION_MODEL_IDENTIFIER: str | None = None
    FACE_EMBEDDING_MODEL_IDENTIFIER: str | None = None
    # YuNet's own published default input size (docs/adr/0005); conservative
    # and swappable per-model in Stage 3.
    FACE_DETECTOR_INPUT_SIZE_PX: int = 320
    # Placeholder pending the Stage 2/3 embedding-model decision (ADR 0005
    # explicitly defers the exact embedder pending an unresolved upstream
    # licensing question) — MUST be overridden to match whatever model is
    # actually vendored later; validated as a structural sanity bound only.
    FACE_EMBEDDING_DIMENSION: int = 128
    # Cosine-similarity semantics only (higher = more similar), never a
    # distance metric — see app/modules/face_recognition/domain.py.
    #
    # Phase 5 Stage 3 note — PROVISIONAL / STRUCTURAL DEFAULT, NOT A
    # VALIDATED PRODUCTION THRESHOLD:
    #
    # 0.82 is derived, not guessed, and not calibrated. dlib's own
    # official guidance for its ResNet embedding model (the model this
    # project selected, see
    # app/modules/face_recognition/providers/dlib_embedder.py) is
    # "same person if Euclidean distance < ~0.6" on raw 128-D
    # descriptors — dlib's conventional distance reference point, not
    # this project's own finding. This project's embedder L2-normalizes
    # every embedding to a unit vector specifically so the whole
    # pipeline can use a single cosine-similarity metric; the
    # conversion below is only mathematically valid *because* of that
    # explicit L2-normalization step — for two unit vectors,
    #     cosine_similarity = 1 - (euclidean_distance^2 / 2)
    # so dlib's 0.6 distance reference maps to
    #     1 - (0.6^2 / 2) = 1 - 0.18 = 0.82.
    # Explicitly, in plain terms:
    #   - real classroom calibration against this project's own data is
    #     still PENDING — nothing has run yet;
    #   - a real FAR/FRR evaluation (see
    #     app/modules/face_recognition/evaluation.py) must be what
    #     actually determines the production threshold, not this
    #     translated reference value;
    #   - 0.82 is a reasonable, math-checked starting point for manual
    #     testing/Stage 5 verification, and nothing more — it must not
    #     be read as an accuracy claim about this deployment.
    # See docs/HANDOVER_PHASE_5_STAGE_3.md, "Calibration status:
    # pending" for the full writeup.
    FACE_MATCH_THRESHOLD: float = 0.82
    # Minimum required gap between the best and second-best candidate's
    # similarity before a match is treated as confident rather than
    # AMBIGUOUS — see app/modules/face_recognition/domain.py. Also a
    # PROVISIONAL structural default (Stage 3), not a calibrated value —
    # see the FACE_MATCH_THRESHOLD note directly above.
    FACE_MATCH_AMBIGUOUS_MARGIN: float = 0.05
    FACE_INFERENCE_DEVICE: Literal["cpu", "cuda"] = "cpu"
    # Deliberately a relative, non-web-root path by default (validated
    # below); a real deployment should override this to an absolute path
    # outside anything served statically. See docs/BIOMETRIC_DATA_POLICY.md.
    BIOMETRIC_STORAGE_ROOT: str = "var/biometric_data"
    MAX_ENROLLMENT_IMAGE_BYTES: int = 5 * 1024 * 1024
    MAX_ATTENDANCE_IMAGE_BYTES: int = Field(default=8 * 1024 * 1024, ge=1024, le=20 * 1024 * 1024)
    MAX_ATTENDANCE_FACES_PER_IMAGE: int = Field(default=40, ge=1, le=200)

    # --- Face recognition (Phase 5 Stage 3: model artifacts + processing) ------
    # Deployer-supplied filesystem paths to model files obtained OUTSIDE
    # this repository/ZIP (never downloaded or committed by this
    # application — see app/modules/face_recognition/model_artifacts.py
    # and docs/HANDOVER_PHASE_5_STAGE_3.md, "Model distribution
    # strategy"). Both are None by default so a deployment that leaves
    # FACE_RECOGNITION_PROVIDER=none never needs either set (enforced
    # together, below).
    FACE_DETECTOR_MODEL_PATH: str | None = None
    FACE_EMBEDDER_MODEL_PATH: str | None = None
    # Optional expected SHA-256 for each model file. When set, a
    # mismatch fails predictably (ModelArtifactChecksumMismatchError)
    # instead of silently running against a substituted/corrupted file.
    # Optional because a deployer may not have pinned a checksum yet —
    # see app/modules/face_recognition/model_artifacts.py's docstring.
    FACE_DETECTOR_MODEL_SHA256: str | None = None
    FACE_EMBEDDER_MODEL_SHA256: str | None = None
    # Ceiling on how many pending samples one
    # SampleProcessingService.process_pending_batch(...) call will
    # process — a bounded, on-demand batch, never an always-running
    # worker (Stage 3 brief §8).
    FACE_PROCESSING_BATCH_LIMIT: int = 20

    # --- Face recognition (Phase 5 Stage 2: enrollment/ingestion bounds) -------
    # Still provider-neutral: nothing below names, loads, or downloads a
    # detector/embedder model. These bound *ingestion* only (decoded pixel
    # dimensions and archive shape), enforced in
    # app/modules/biometric_enrollment/ before Stage 3 ever sees a sample.
    MAX_ENROLLMENT_IMAGE_PIXELS: int = 30_000_000
    MAX_ENROLLMENT_IMAGE_DIMENSION_PX: int = 6000
    MAX_BULK_ENROLLMENT_ZIP_BYTES: int = 50 * 1024 * 1024
    MAX_BULK_ENROLLMENT_FILES: int = 200
    MAX_BULK_ENROLLMENT_TOTAL_UNCOMPRESSED_BYTES: int = 250 * 1024 * 1024
    MAX_BULK_ENROLLMENT_COMPRESSION_RATIO: float = 100.0
    # A PENDING (staged-but-not-promoted) enrollment sample older than this
    # is treated as stale/abandoned by the reconciliation report in
    # app/modules/biometric_enrollment/reconciliation.py — never acted on
    # automatically, only reported (see docs/BIOMETRIC_DATA_POLICY.md).
    ENROLLMENT_STAGING_TIMEOUT_MINUTES: int = 60

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("CORS_ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> list[str]:
        """Accept JSON-array or comma-separated environment values.

        ``NoDecode`` prevents pydantic-settings from trying to JSON-decode the
        environment value before this validator runs. That keeps both the
        documented JSON form and the convenient comma-separated form valid.
        """
        if value is None or value == "":
            return []
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return []
            if normalized.startswith("["):
                try:
                    decoded = json.loads(normalized)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        "CORS_ALLOWED_ORIGINS must be a valid JSON array or "
                        "a comma-separated string."
                    ) from exc
                if not isinstance(decoded, list):
                    raise ValueError("CORS_ALLOWED_ORIGINS JSON value must be an array.")
                value = decoded
            else:
                return [origin.strip() for origin in normalized.split(",") if origin.strip()]
        if isinstance(value, list):
            return [str(origin).strip() for origin in value if str(origin).strip()]
        raise ValueError(
            "CORS_ALLOWED_ORIGINS must be a JSON array, comma-separated string, or list."
        )

    @field_validator("TRUSTED_HOSTS", mode="before")
    @classmethod
    def _parse_trusted_hosts(cls, value: object) -> list[str]:
        """Accept a JSON array or comma-separated host-name allow-list."""
        if value is None or value == "":
            return []
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return []
            if normalized.startswith("["):
                try:
                    decoded = json.loads(normalized)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        "TRUSTED_HOSTS must be a valid JSON array or comma-separated string."
                    ) from exc
                if not isinstance(decoded, list):
                    raise ValueError("TRUSTED_HOSTS JSON value must be an array.")
                value = decoded
            else:
                value = [host.strip() for host in normalized.split(",") if host.strip()]
        if not isinstance(value, list):
            raise ValueError("TRUSTED_HOSTS must be a JSON array, comma-separated string, or list.")

        hosts = [str(host).strip() for host in value if str(host).strip()]
        for host in hosts:
            if "://" in host or "/" in host or any(character.isspace() for character in host):
                raise ValueError(
                    "TRUSTED_HOSTS entries must be host names or IP addresses without a URL scheme."
                )
        return hosts

    @field_validator("LOG_LEVEL")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        normalized = value.upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}.")
        return normalized

    @field_validator("DATABASE_URL")
    @classmethod
    def _validate_database_url(cls, value: str) -> str:
        # Never echo `value` itself in an error message: it may contain
        # credentials (see docs/AUDIT.md §1.4 / Critical C1 — this is
        # exactly the class of accidental-disclosure bug that finding
        # was about).
        if value.startswith("sqlite"):
            raise ValueError(
                "DATABASE_URL must not use SQLite; PostgreSQL is the only "
                "supported v2 application database."
            )
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "DATABASE_URL must use the 'postgresql+asyncpg://' driver "
                "for the async SQLAlchemy engine."
            )
        return value

    @field_validator("SECRET_KEY")
    @classmethod
    def _validate_secret_key_strength(cls, value: str) -> str:
        if len(value) < _MIN_SECRET_LENGTH:
            raise ValueError(f"SECRET_KEY must be at least {_MIN_SECRET_LENGTH} characters.")
        if value.strip().lower() in _PLACEHOLDER_SECRETS:
            raise ValueError(
                "SECRET_KEY must not be a known placeholder value. Generate "
                "a real random secret, e.g. `openssl rand -hex 32`."
            )
        return value

    @field_validator("JWT_ALGORITHM")
    @classmethod
    def _validate_jwt_algorithm(cls, value: str) -> str:
        allowed = {"HS256", "HS384", "HS512"}
        normalized = value.upper()
        if normalized not in allowed:
            raise ValueError(f"JWT_ALGORITHM must be one of {sorted(allowed)}.")
        return normalized

    @field_validator("ACCESS_TOKEN_EXPIRE_MINUTES")
    @classmethod
    def _validate_access_token_lifetime(cls, value: int) -> int:
        if not (1 <= value <= 1440):
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be between 1 and 1440 (24 hours).")
        return value

    @field_validator("REFRESH_TOKEN_EXPIRE_DAYS")
    @classmethod
    def _validate_refresh_token_lifetime(cls, value: int) -> int:
        if not (1 <= value <= 90):
            raise ValueError("REFRESH_TOKEN_EXPIRE_DAYS must be between 1 and 90.")
        return value

    @field_validator("FACE_DETECTOR_INPUT_SIZE_PX")
    @classmethod
    def _validate_face_detector_input_size(cls, value: int) -> int:
        if not (32 <= value <= 4096):
            raise ValueError("FACE_DETECTOR_INPUT_SIZE_PX must be between 32 and 4096 pixels.")
        return value

    @field_validator("FACE_EMBEDDING_DIMENSION")
    @classmethod
    def _validate_face_embedding_dimension(cls, value: int) -> int:
        if not (8 <= value <= 4096):
            raise ValueError("FACE_EMBEDDING_DIMENSION must be between 8 and 4096.")
        return value

    @field_validator("FACE_MATCH_THRESHOLD")
    @classmethod
    def _validate_face_match_threshold(cls, value: float) -> float:
        if not (0.0 < value <= 1.0):
            raise ValueError(
                "FACE_MATCH_THRESHOLD must be greater than 0 and at most 1 "
                "(cosine-similarity semantics — see app/modules/face_recognition/domain.py)."
            )
        return value

    @field_validator("FACE_MATCH_AMBIGUOUS_MARGIN")
    @classmethod
    def _validate_face_match_ambiguous_margin(cls, value: float) -> float:
        if not (0.0 <= value < 1.0):
            raise ValueError(
                "FACE_MATCH_AMBIGUOUS_MARGIN must be between 0 (inclusive) and 1 (exclusive)."
            )
        return value

    @field_validator("FACE_DETECTOR_MODEL_SHA256", "FACE_EMBEDDER_MODEL_SHA256")
    @classmethod
    def _validate_face_model_sha256(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().lower()
        if not normalized:
            return None
        if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
            raise ValueError(
                "A configured model SHA-256 must be exactly 64 hexadecimal characters."
            )
        return normalized

    @field_validator("FACE_PROCESSING_BATCH_LIMIT")
    @classmethod
    def _validate_face_processing_batch_limit(cls, value: int) -> int:
        if not (1 <= value <= 500):
            raise ValueError("FACE_PROCESSING_BATCH_LIMIT must be between 1 and 500.")
        return value

    @field_validator("MAX_ENROLLMENT_IMAGE_BYTES")
    @classmethod
    def _validate_max_enrollment_image_bytes(cls, value: int) -> int:
        if not (1024 <= value <= 20 * 1024 * 1024):
            raise ValueError("MAX_ENROLLMENT_IMAGE_BYTES must be between 1 KiB and 20 MiB.")
        return value

    @field_validator("MAX_ENROLLMENT_IMAGE_PIXELS")
    @classmethod
    def _validate_max_enrollment_image_pixels(cls, value: int) -> int:
        if not (1_000_000 <= value <= 200_000_000):
            raise ValueError("MAX_ENROLLMENT_IMAGE_PIXELS must be between 1e6 and 2e8.")
        return value

    @field_validator("MAX_ENROLLMENT_IMAGE_DIMENSION_PX")
    @classmethod
    def _validate_max_enrollment_image_dimension_px(cls, value: int) -> int:
        if not (256 <= value <= 20_000):
            raise ValueError("MAX_ENROLLMENT_IMAGE_DIMENSION_PX must be between 256 and 20000.")
        return value

    @field_validator("MAX_BULK_ENROLLMENT_ZIP_BYTES")
    @classmethod
    def _validate_max_bulk_enrollment_zip_bytes(cls, value: int) -> int:
        if not (1024 <= value <= 500 * 1024 * 1024):
            raise ValueError("MAX_BULK_ENROLLMENT_ZIP_BYTES must be between 1 KiB and 500 MiB.")
        return value

    @field_validator("MAX_BULK_ENROLLMENT_FILES")
    @classmethod
    def _validate_max_bulk_enrollment_files(cls, value: int) -> int:
        if not (1 <= value <= 5000):
            raise ValueError("MAX_BULK_ENROLLMENT_FILES must be between 1 and 5000.")
        return value

    @field_validator("MAX_BULK_ENROLLMENT_TOTAL_UNCOMPRESSED_BYTES")
    @classmethod
    def _validate_max_bulk_enrollment_total_uncompressed_bytes(cls, value: int) -> int:
        if not (1024 <= value <= 5 * 1024 * 1024 * 1024):
            raise ValueError(
                "MAX_BULK_ENROLLMENT_TOTAL_UNCOMPRESSED_BYTES must be between 1 KiB and 5 GiB."
            )
        return value

    @field_validator("MAX_BULK_ENROLLMENT_COMPRESSION_RATIO")
    @classmethod
    def _validate_max_bulk_enrollment_compression_ratio(cls, value: float) -> float:
        if not (1.0 <= value <= 10_000.0):
            raise ValueError("MAX_BULK_ENROLLMENT_COMPRESSION_RATIO must be between 1 and 10000.")
        return value

    @field_validator("ENROLLMENT_STAGING_TIMEOUT_MINUTES")
    @classmethod
    def _validate_enrollment_staging_timeout_minutes(cls, value: int) -> int:
        if not (1 <= value <= 10_080):
            raise ValueError(
                "ENROLLMENT_STAGING_TIMEOUT_MINUTES must be between 1 and 10080 (one week)."
            )
        return value

    @field_validator("BIOMETRIC_STORAGE_ROOT")
    @classmethod
    def _validate_biometric_storage_root(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("BIOMETRIC_STORAGE_ROOT must not be blank.")
        # A narrow, named-segment check — not a substitute for a real
        # deployment review, but enough to fail fast on the obvious
        # mistake of pointing this at a directory served statically (the
        # exact class of exposure docs/BIOMETRIC_DATA_POLICY.md forbids).
        lowered = normalized.replace("\\", "/").strip("/").lower()
        segments = set(lowered.split("/"))
        forbidden_segments = {"static", "public", "www", "wwwroot", "frontend", "node_modules"}
        if segments & forbidden_segments:
            raise ValueError(
                "BIOMETRIC_STORAGE_ROOT must not sit under a public/static "
                "web-root-style directory (docs/BIOMETRIC_DATA_POLICY.md)."
            )
        return normalized

    @model_validator(mode="after")
    def _enforce_face_recognition_provider_consistency(self) -> Settings:
        """Fail fast on a half-configured provider.

        A deployer who sets ``FACE_RECOGNITION_PROVIDER`` to anything other
        than ``none`` has declared intent to actually run a provider (Stage
        3+); this rejects that configuration at startup rather than later,
        silently, at first request, if the paired model identifiers were
        never set. This mirrors the existing ``SECRET_KEY``/``DATABASE_URL``
        fail-fast philosophy elsewhere in this class.
        """
        if self.FACE_RECOGNITION_PROVIDER is not FaceRecognitionProvider.NONE:
            if not (self.FACE_DETECTION_MODEL_IDENTIFIER or "").strip():
                raise ValueError(
                    "FACE_DETECTION_MODEL_IDENTIFIER must be set when "
                    "FACE_RECOGNITION_PROVIDER is not 'none'."
                )
            if not (self.FACE_EMBEDDING_MODEL_IDENTIFIER or "").strip():
                raise ValueError(
                    "FACE_EMBEDDING_MODEL_IDENTIFIER must be set when "
                    "FACE_RECOGNITION_PROVIDER is not 'none'."
                )
            # Phase 5 Stage 3: an enabled provider must also name the
            # actual model *file* paths — see
            # app/modules/face_recognition/model_artifacts.py. The
            # identifiers above are opaque labels; these are what the
            # provider adapters actually load. Checksums remain
            # optional (see FACE_DETECTOR_MODEL_SHA256's own docstring).
            if not (self.FACE_DETECTOR_MODEL_PATH or "").strip():
                raise ValueError(
                    "FACE_DETECTOR_MODEL_PATH must be set when "
                    "FACE_RECOGNITION_PROVIDER is not 'none'."
                )
            if not (self.FACE_EMBEDDER_MODEL_PATH or "").strip():
                raise ValueError(
                    "FACE_EMBEDDER_MODEL_PATH must be set when "
                    "FACE_RECOGNITION_PROVIDER is not 'none'."
                )
        return self

    @model_validator(mode="after")
    def _enforce_production_safety(self) -> Settings:
        if self.REFRESH_TOKEN_COOKIE_SAMESITE == "none" and not self.REFRESH_TOKEN_COOKIE_SECURE:
            raise ValueError("REFRESH_TOKEN_COOKIE_SAMESITE='none' requires Secure=true.")

        if self.APP_ENV is Environment.PRODUCTION:
            if self.DEBUG:
                raise ValueError("DEBUG must be false when APP_ENV=production.")
            if "*" in self.CORS_ALLOWED_ORIGINS:
                raise ValueError(
                    "CORS_ALLOWED_ORIGINS must not be '*' when APP_ENV=production "
                    "(docs/AUDIT.md §2.5 / High finding H5 — this is the exact "
                    "legacy misconfiguration Phase 1 must not repeat)."
                )
            if not self.CORS_ALLOWED_ORIGINS:
                raise ValueError(
                    "CORS_ALLOWED_ORIGINS must be explicitly set when APP_ENV=production."
                )
            if "*" in self.TRUSTED_HOSTS:
                raise ValueError("TRUSTED_HOSTS must not contain '*' when APP_ENV=production.")
            if not self.TRUSTED_HOSTS:
                raise ValueError("TRUSTED_HOSTS must be explicitly set when APP_ENV=production.")
            if not self.REFRESH_TOKEN_COOKIE_SECURE:
                raise ValueError(
                    "REFRESH_TOKEN_COOKIE_SECURE must be true when APP_ENV=production "
                    "— the refresh-token cookie must never be sent over plain HTTP."
                )
            if self.OTP_EMAIL_PROVIDER == "development_log":
                raise ValueError("OTP_EMAIL_PROVIDER=development_log is forbidden in production.")

        if self.LOGIN_OTP_ENABLED and self.OTP_EMAIL_PROVIDER == "none":
            raise ValueError(
                "LOGIN_OTP_ENABLED=true requires an explicitly configured email provider."
            )
        if self.OTP_EMAIL_PROVIDER == "smtp":
            if not self.SMTP_HOST or self.SMTP_FROM_EMAIL is None:
                raise ValueError(
                    "SMTP_HOST and SMTP_FROM_EMAIL are required when OTP SMTP delivery is enabled."
                )
            if bool(self.SMTP_USERNAME) != bool(self.SMTP_PASSWORD):
                raise ValueError(
                    "SMTP_USERNAME and SMTP_PASSWORD must either both be set or both be unset."
                )
            if self.SMTP_STARTTLS and self.SMTP_USE_SSL:
                raise ValueError("SMTP_STARTTLS and SMTP_USE_SSL cannot both be enabled.")
            if self.APP_ENV is Environment.PRODUCTION and not (
                self.SMTP_STARTTLS or self.SMTP_USE_SSL
            ):
                raise ValueError("Production OTP SMTP delivery requires TLS.")
        if self.OTP_EMAIL_PROVIDER == "brevo_api":
            if not self.BREVO_API_KEY or not self.BREVO_API_KEY.strip():
                raise ValueError(
                    "BREVO_API_KEY is required when OTP Brevo API delivery is enabled."
                )
            if self.SMTP_FROM_EMAIL is None:
                raise ValueError(
                    "SMTP_FROM_EMAIL is required when OTP Brevo API delivery is enabled."
                )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings provider.

    Routes should depend on this via ``Depends(get_settings)`` rather than
    importing a module-level instance, so tests can override it per-app
    via ``app.dependency_overrides``. The ``type: ignore`` below is
    intentional and narrow: pydantic-settings supplies these "required"
    values from the environment/.env at runtime, which mypy cannot see
    through even with the pydantic plugin enabled.
    """

    return Settings()
