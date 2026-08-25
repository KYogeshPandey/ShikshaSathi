"""Tests for app.core.config.Settings.

Every test constructs ``Settings`` directly (not via the cached
``get_settings()`` provider) with explicit keyword arguments and
``_env_file=None``, so each test is fully isolated from both the real
developer environment and from the dummy values conftest.py bootstraps
for the rest of the suite — explicit constructor kwargs take precedence
over environment/dotenv sources in pydantic-settings.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Environment, FaceRecognitionProvider, Settings

_VALID_SECRET = "a" * 40
_BASE_KWARGS: dict[str, Any] = {
    "_env_file": None,
    "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/shikshasathi",
    "POSTGRES_DB": "shikshasathi",
    "POSTGRES_USER": "user",
    "POSTGRES_PASSWORD": "pass",
    "SECRET_KEY": _VALID_SECRET,
    "REFRESH_TOKEN_COOKIE_SECURE": True,
}


def test_valid_development_settings_load() -> None:
    settings = Settings(**_BASE_KWARGS, APP_ENV=Environment.DEVELOPMENT, DEBUG=True)
    assert settings.APP_ENV is Environment.DEVELOPMENT
    assert settings.DEBUG is True
    assert settings.DATABASE_URL.startswith("postgresql+asyncpg://")


def test_valid_testing_settings_load() -> None:
    settings = Settings(**_BASE_KWARGS, APP_ENV=Environment.TESTING)
    assert settings.APP_ENV is Environment.TESTING


def test_missing_secret_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECRET_KEY", raising=False)
    kwargs = {k: v for k, v in _BASE_KWARGS.items() if k != "SECRET_KEY"}
    with pytest.raises(ValidationError):
        Settings(**kwargs)


def test_short_secret_key_rejected() -> None:
    kwargs = {**_BASE_KWARGS, "SECRET_KEY": "too-short"}
    with pytest.raises(ValidationError):
        Settings(**kwargs)


def test_known_placeholder_secret_rejected_despite_sufficient_length() -> None:
    # Exactly 32 characters — long enough to pass the length check alone,
    # so this isolates the placeholder-detection logic specifically. This
    # is the literal example value from the legacy backend/.env.example.
    placeholder = "replace_with_a_long_random_value"
    assert len(placeholder) == 32
    kwargs = {**_BASE_KWARGS, "SECRET_KEY": placeholder}
    with pytest.raises(ValidationError):
        Settings(**kwargs)


def test_production_debug_mode_rejected() -> None:
    kwargs = {
        **_BASE_KWARGS,
        "APP_ENV": Environment.PRODUCTION,
        "DEBUG": True,
        "CORS_ALLOWED_ORIGINS": "https://app.example.com",
    }
    with pytest.raises(ValidationError):
        Settings(**kwargs)


def test_production_wildcard_cors_rejected() -> None:
    kwargs = {
        **_BASE_KWARGS,
        "APP_ENV": Environment.PRODUCTION,
        "DEBUG": False,
        "CORS_ALLOWED_ORIGINS": "*",
    }
    with pytest.raises(ValidationError):
        Settings(**kwargs)


def test_production_requires_explicit_cors_origins() -> None:
    kwargs = {
        **_BASE_KWARGS,
        "APP_ENV": Environment.PRODUCTION,
        "DEBUG": False,
        "CORS_ALLOWED_ORIGINS": "",
    }
    with pytest.raises(ValidationError):
        Settings(**kwargs)


def test_production_settings_load_with_safe_values() -> None:
    kwargs = {
        **_BASE_KWARGS,
        "APP_ENV": Environment.PRODUCTION,
        "DEBUG": False,
        "CORS_ALLOWED_ORIGINS": "https://app.example.com,https://admin.example.com",
        "TRUSTED_HOSTS": "app.example.com,admin.example.com",
    }
    settings = Settings(**kwargs)
    assert settings.CORS_ALLOWED_ORIGINS == [
        "https://app.example.com",
        "https://admin.example.com",
    ]
    assert settings.TRUSTED_HOSTS == ["app.example.com", "admin.example.com"]


@pytest.mark.parametrize("trusted_hosts", ["", "*"])
def test_production_rejects_empty_or_wildcard_trusted_hosts(trusted_hosts: str) -> None:
    kwargs = {
        **_BASE_KWARGS,
        "APP_ENV": Environment.PRODUCTION,
        "DEBUG": False,
        "CORS_ALLOWED_ORIGINS": "https://app.example.com",
        "TRUSTED_HOSTS": trusted_hosts,
    }
    with pytest.raises(ValidationError):
        Settings(**kwargs)


def test_trusted_hosts_parse_json_environment_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRUSTED_HOSTS", '["app.example.com","127.0.0.1"]')
    settings = Settings(**_BASE_KWARGS)
    assert settings.TRUSTED_HOSTS == ["app.example.com", "127.0.0.1"]


@pytest.mark.parametrize("trusted_hosts", ["https://app.example.com", "app.example.com/path"])
def test_trusted_hosts_reject_urls_and_paths(trusted_hosts: str) -> None:
    with pytest.raises(ValidationError):
        Settings(**_BASE_KWARGS, TRUSTED_HOSTS=trusted_hosts)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("LOGIN_RATE_LIMIT_ATTEMPTS", 0),
        ("LOGIN_RATE_LIMIT_ATTEMPTS", 1001),
        ("LOGIN_RATE_LIMIT_WINDOW_SECONDS", 0),
        ("LOGIN_RATE_LIMIT_WINDOW_SECONDS", 3601),
    ],
)
def test_login_rate_limit_settings_are_bounded(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(**_BASE_KWARGS, **{field: value})


def test_cors_origins_parsed_from_comma_separated_string() -> None:
    settings = Settings(**_BASE_KWARGS, CORS_ALLOWED_ORIGINS=" http://a.test , http://b.test ")
    assert settings.CORS_ALLOWED_ORIGINS == ["http://a.test", "http://b.test"]


def test_cors_origins_parsed_from_json_environment_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["http://a.test","http://b.test"]')
    settings = Settings(**_BASE_KWARGS)
    assert settings.CORS_ALLOWED_ORIGINS == ["http://a.test", "http://b.test"]


def test_cors_origins_parsed_from_comma_separated_environment_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://a.test,http://b.test")
    settings = Settings(**_BASE_KWARGS)
    assert settings.CORS_ALLOWED_ORIGINS == ["http://a.test", "http://b.test"]


def test_cors_origins_empty_string_parses_to_empty_list() -> None:
    settings = Settings(**_BASE_KWARGS, CORS_ALLOWED_ORIGINS="")
    assert settings.CORS_ALLOWED_ORIGINS == []


def test_database_url_rejects_sqlite() -> None:
    kwargs = {**_BASE_KWARGS, "DATABASE_URL": "sqlite+aiosqlite:///./test.db"}
    with pytest.raises(ValidationError):
        Settings(**kwargs)


def test_database_url_requires_asyncpg_driver() -> None:
    kwargs = {**_BASE_KWARGS, "DATABASE_URL": "postgresql://user:pass@localhost/db"}
    with pytest.raises(ValidationError):
        Settings(**kwargs)


def test_log_level_is_normalized_to_uppercase() -> None:
    settings = Settings(**_BASE_KWARGS, LOG_LEVEL="debug")
    assert settings.LOG_LEVEL == "DEBUG"


def test_invalid_log_level_rejected() -> None:
    kwargs = {**_BASE_KWARGS, "LOG_LEVEL": "NOT_A_LEVEL"}
    with pytest.raises(ValidationError):
        Settings(**kwargs)


def test_production_rejects_insecure_refresh_cookie() -> None:
    kwargs = {
        **_BASE_KWARGS,
        "APP_ENV": Environment.PRODUCTION,
        "DEBUG": False,
        "CORS_ALLOWED_ORIGINS": "https://app.example.com",
        "REFRESH_TOKEN_COOKIE_SECURE": False,
    }
    with pytest.raises(ValidationError):
        Settings(**kwargs)


@pytest.mark.parametrize("minutes", [0, 1441])
def test_access_token_lifetime_outside_safe_range_is_rejected(minutes: int) -> None:
    with pytest.raises(ValidationError):
        Settings(**_BASE_KWARGS, ACCESS_TOKEN_EXPIRE_MINUTES=minutes)


@pytest.mark.parametrize("days", [0, 91])
def test_refresh_token_lifetime_outside_safe_range_is_rejected(days: int) -> None:
    with pytest.raises(ValidationError):
        Settings(**_BASE_KWARGS, REFRESH_TOKEN_EXPIRE_DAYS=days)


def test_invalid_jwt_algorithm_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(**_BASE_KWARGS, JWT_ALGORITHM="none")


def test_committed_example_secret_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(
            **{
                **_BASE_KWARGS,
                "SECRET_KEY": "CHANGE_ME_generate_your_own_32_plus_char_random_secret_value",
            }
        )


def test_samesite_none_requires_secure_cookie_in_every_environment() -> None:
    with pytest.raises(ValidationError):
        Settings(
            **{
                **_BASE_KWARGS,
                "APP_ENV": Environment.DEVELOPMENT,
                "REFRESH_TOKEN_COOKIE_SAMESITE": "none",
                "REFRESH_TOKEN_COOKIE_SECURE": False,
            }
        )


def test_otp_enabled_requires_an_explicit_delivery_provider() -> None:
    with pytest.raises(ValidationError):
        Settings(**_BASE_KWARGS, LOGIN_OTP_ENABLED=True, OTP_EMAIL_PROVIDER="none")


def test_development_otp_log_adapter_is_allowed_only_outside_production() -> None:
    development = Settings(
        **_BASE_KWARGS,
        APP_ENV=Environment.DEVELOPMENT,
        LOGIN_OTP_ENABLED=True,
        OTP_EMAIL_PROVIDER="development_log",
    )
    assert development.LOGIN_OTP_ENABLED is True

    with pytest.raises(ValidationError):
        Settings(
            **_BASE_KWARGS,
            APP_ENV=Environment.PRODUCTION,
            DEBUG=False,
            CORS_ALLOWED_ORIGINS="https://app.example.com",
            TRUSTED_HOSTS="api.example.com",
            LOGIN_OTP_ENABLED=True,
            OTP_EMAIL_PROVIDER="development_log",
        )


def test_otp_smtp_requires_host_from_address_and_complete_credentials() -> None:
    with pytest.raises(ValidationError):
        Settings(
            **_BASE_KWARGS,
            LOGIN_OTP_ENABLED=True,
            OTP_EMAIL_PROVIDER="smtp",
        )
    with pytest.raises(ValidationError):
        Settings(
            **_BASE_KWARGS,
            LOGIN_OTP_ENABLED=True,
            OTP_EMAIL_PROVIDER="smtp",
            SMTP_HOST="smtp.example.com",
            SMTP_FROM_EMAIL="no-reply@example.com",
            SMTP_USERNAME="user",
        )


def test_otp_smtp_transport_modes_are_mutually_exclusive() -> None:
    with pytest.raises(ValidationError):
        Settings(
            **_BASE_KWARGS,
            LOGIN_OTP_ENABLED=True,
            OTP_EMAIL_PROVIDER="smtp",
            SMTP_HOST="smtp.example.com",
            SMTP_FROM_EMAIL="no-reply@example.com",
            SMTP_STARTTLS=True,
            SMTP_USE_SSL=True,
        )


def test_otp_brevo_api_accepts_required_configuration_and_hides_key() -> None:
    api_key = "brevo-test-key-not-a-real-secret"
    settings = Settings(
        **_BASE_KWARGS,
        LOGIN_OTP_ENABLED=True,
        OTP_EMAIL_PROVIDER="brevo_api",
        BREVO_API_KEY=api_key,
        SMTP_FROM_EMAIL="verified-sender@example.com",
    )

    assert settings.OTP_EMAIL_PROVIDER == "brevo_api"
    assert settings.BREVO_API_TIMEOUT_SECONDS == 20
    assert api_key not in repr(settings)


def test_otp_brevo_api_requires_api_key() -> None:
    with pytest.raises(ValidationError, match="BREVO_API_KEY"):
        Settings(
            **_BASE_KWARGS,
            LOGIN_OTP_ENABLED=True,
            OTP_EMAIL_PROVIDER="brevo_api",
            SMTP_FROM_EMAIL="verified-sender@example.com",
        )


def test_otp_brevo_api_requires_sender_email() -> None:
    with pytest.raises(ValidationError, match="SMTP_FROM_EMAIL"):
        Settings(
            **_BASE_KWARGS,
            LOGIN_OTP_ENABLED=True,
            OTP_EMAIL_PROVIDER="brevo_api",
            BREVO_API_KEY="brevo-test-key-not-a-real-secret",
        )


def test_production_otp_smtp_rejects_plaintext_transport() -> None:
    with pytest.raises(ValidationError):
        Settings(
            **_BASE_KWARGS,
            APP_ENV=Environment.PRODUCTION,
            DEBUG=False,
            CORS_ALLOWED_ORIGINS="https://app.example.com",
            TRUSTED_HOSTS="api.example.com",
            LOGIN_OTP_ENABLED=True,
            OTP_EMAIL_PROVIDER="smtp",
            SMTP_HOST="smtp.example.com",
            SMTP_FROM_EMAIL="no-reply@example.com",
            SMTP_STARTTLS=False,
            SMTP_USE_SSL=False,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("LOGIN_OTP_TTL_SECONDS", 299),
        ("LOGIN_OTP_TTL_SECONDS", 901),
        ("LOGIN_OTP_MAX_ATTEMPTS", 0),
        ("LOGIN_OTP_RESEND_COOLDOWN_SECONDS", 29),
        ("BREVO_API_TIMEOUT_SECONDS", 61),
        ("SMTP_TIMEOUT_SECONDS", 61),
    ],
)
def test_otp_security_settings_are_bounded(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(**_BASE_KWARGS, **{field: value})


# ---------------------------------------------------------------------------
# Phase 5 Stage 1 — face-recognition provider-neutral configuration
#
# No detector/embedder/matcher exists yet (see
# app/modules/face_recognition/); these tests only cover the config
# surface itself — that it is safe-by-default, fails fast on nonsensical
# values, and enforces the one cross-field rule (a non-"none" provider
# requires both model identifiers to be set).
# ---------------------------------------------------------------------------


def test_face_recognition_defaults_are_safe_and_inert() -> None:
    settings = Settings(**_BASE_KWARGS)
    assert settings.FACE_RECOGNITION_PROVIDER is FaceRecognitionProvider.NONE
    assert settings.FACE_DETECTION_MODEL_IDENTIFIER is None
    assert settings.FACE_EMBEDDING_MODEL_IDENTIFIER is None
    assert settings.FACE_INFERENCE_DEVICE == "cpu"
    assert 0.0 < settings.FACE_MATCH_THRESHOLD <= 1.0
    assert 0.0 <= settings.FACE_MATCH_AMBIGUOUS_MARGIN < 1.0
    assert settings.FACE_EMBEDDING_DIMENSION > 0
    assert settings.MAX_ENROLLMENT_IMAGE_BYTES > 0


@pytest.mark.parametrize("size_px", [0, 31, 4097, -10])
def test_face_detector_input_size_outside_safe_range_is_rejected(size_px: int) -> None:
    with pytest.raises(ValidationError):
        Settings(**_BASE_KWARGS, FACE_DETECTOR_INPUT_SIZE_PX=size_px)


@pytest.mark.parametrize("dimension", [0, 7, 4097, -128])
def test_face_embedding_dimension_outside_safe_range_is_rejected(dimension: int) -> None:
    with pytest.raises(ValidationError):
        Settings(**_BASE_KWARGS, FACE_EMBEDDING_DIMENSION=dimension)


@pytest.mark.parametrize("threshold", [0.0, -0.1, 1.1, 2.0])
def test_face_match_threshold_outside_safe_range_is_rejected(threshold: float) -> None:
    with pytest.raises(ValidationError):
        Settings(**_BASE_KWARGS, FACE_MATCH_THRESHOLD=threshold)


@pytest.mark.parametrize("margin", [-0.01, 1.0, 1.5])
def test_face_match_ambiguous_margin_outside_safe_range_is_rejected(margin: float) -> None:
    with pytest.raises(ValidationError):
        Settings(**_BASE_KWARGS, FACE_MATCH_AMBIGUOUS_MARGIN=margin)


@pytest.mark.parametrize("num_bytes", [0, 1023, 20 * 1024 * 1024 + 1])
def test_max_enrollment_image_bytes_outside_safe_range_is_rejected(num_bytes: int) -> None:
    with pytest.raises(ValidationError):
        Settings(**_BASE_KWARGS, MAX_ENROLLMENT_IMAGE_BYTES=num_bytes)


def test_face_inference_device_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError):
        Settings(**_BASE_KWARGS, FACE_INFERENCE_DEVICE="tpu")


def test_biometric_storage_root_rejects_blank_value() -> None:
    with pytest.raises(ValidationError):
        Settings(**_BASE_KWARGS, BIOMETRIC_STORAGE_ROOT="   ")


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "static/biometric",
        "frontend/public/biometric",
        "var/www/biometric",
        "public",
    ],
)
def test_biometric_storage_root_rejects_public_web_root_style_paths(unsafe_path: str) -> None:
    with pytest.raises(ValidationError):
        Settings(**_BASE_KWARGS, BIOMETRIC_STORAGE_ROOT=unsafe_path)


def test_biometric_storage_root_accepts_a_private_path_outside_the_web_root() -> None:
    settings = Settings(**_BASE_KWARGS, BIOMETRIC_STORAGE_ROOT="var/biometric_data")
    assert settings.BIOMETRIC_STORAGE_ROOT == "var/biometric_data"


def test_enabling_a_provider_without_model_identifiers_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(
            **_BASE_KWARGS,
            FACE_RECOGNITION_PROVIDER=FaceRecognitionProvider.SERVER_SIDE_LOCAL,
        )


def test_enabling_a_provider_with_a_blank_model_identifier_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(
            **_BASE_KWARGS,
            FACE_RECOGNITION_PROVIDER=FaceRecognitionProvider.SERVER_SIDE_LOCAL,
            FACE_DETECTION_MODEL_IDENTIFIER="   ",
            FACE_EMBEDDING_MODEL_IDENTIFIER="some-embedder",
        )


def test_enabling_a_provider_with_identifiers_but_no_detector_model_path_is_rejected() -> None:
    """Stage 3: identifiers alone are opaque labels, not enough to load a model.

    ``FACE_DETECTOR_MODEL_PATH``/``FACE_EMBEDDER_MODEL_PATH`` are the actual
    file paths the provider adapters read (see
    ``app/modules/face_recognition/model_artifacts.py``) and are required
    once a provider is enabled, independently of the identifier fields.
    """
    with pytest.raises(ValidationError):
        Settings(
            **_BASE_KWARGS,
            FACE_RECOGNITION_PROVIDER=FaceRecognitionProvider.SERVER_SIDE_LOCAL,
            FACE_DETECTION_MODEL_IDENTIFIER="face_detection_yunet_2023mar.onnx",
            FACE_EMBEDDING_MODEL_IDENTIFIER="dlib_face_recognition_resnet_model_v1",
            FACE_EMBEDDER_MODEL_PATH="/var/models/dlib_face_recognition_resnet_model_v1.dat",
            # FACE_DETECTOR_MODEL_PATH intentionally omitted.
        )


def test_enabling_a_provider_with_identifiers_but_no_embedder_model_path_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(
            **_BASE_KWARGS,
            FACE_RECOGNITION_PROVIDER=FaceRecognitionProvider.SERVER_SIDE_LOCAL,
            FACE_DETECTION_MODEL_IDENTIFIER="face_detection_yunet_2023mar.onnx",
            FACE_EMBEDDING_MODEL_IDENTIFIER="dlib_face_recognition_resnet_model_v1",
            FACE_DETECTOR_MODEL_PATH="/var/models/face_detection_yunet_2023mar.onnx",
            # FACE_EMBEDDER_MODEL_PATH intentionally omitted.
        )


def test_enabling_a_provider_with_a_blank_detector_model_path_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(
            **_BASE_KWARGS,
            FACE_RECOGNITION_PROVIDER=FaceRecognitionProvider.SERVER_SIDE_LOCAL,
            FACE_DETECTION_MODEL_IDENTIFIER="face_detection_yunet_2023mar.onnx",
            FACE_EMBEDDING_MODEL_IDENTIFIER="dlib_face_recognition_resnet_model_v1",
            FACE_DETECTOR_MODEL_PATH="   ",
            FACE_EMBEDDER_MODEL_PATH="/var/models/dlib_face_recognition_resnet_model_v1.dat",
        )


def test_enabling_a_provider_with_identifiers_and_model_paths_set_succeeds() -> None:
    """Stage 3's actual success contract: two identifiers *and* two model paths.

    Renamed from the Stage 2-era
    ``test_enabling_a_provider_with_both_model_identifiers_set_succeeds``,
    which only supplied the two identifiers and was stale against the
    Stage 3 validator above (``_enforce_face_recognition_provider_consistency``)
    that also requires ``FACE_DETECTOR_MODEL_PATH``/``FACE_EMBEDDER_MODEL_PATH``.
    The paths below are safe, obviously-fake placeholders — this test never
    touches the filesystem or loads a real model.
    """
    settings = Settings(
        **_BASE_KWARGS,
        FACE_RECOGNITION_PROVIDER=FaceRecognitionProvider.SERVER_SIDE_LOCAL,
        FACE_DETECTION_MODEL_IDENTIFIER="face_detection_yunet_2023mar.onnx",
        FACE_EMBEDDING_MODEL_IDENTIFIER="dlib_face_recognition_resnet_model_v1",
        FACE_DETECTOR_MODEL_PATH="/var/models/face_detection_yunet_2023mar.onnx",
        FACE_EMBEDDER_MODEL_PATH="/var/models/dlib_face_recognition_resnet_model_v1.dat",
    )
    assert settings.FACE_RECOGNITION_PROVIDER is FaceRecognitionProvider.SERVER_SIDE_LOCAL
    assert settings.FACE_DETECTOR_MODEL_PATH == "/var/models/face_detection_yunet_2023mar.onnx"
    assert (
        settings.FACE_EMBEDDER_MODEL_PATH == "/var/models/dlib_face_recognition_resnet_model_v1.dat"
    )
