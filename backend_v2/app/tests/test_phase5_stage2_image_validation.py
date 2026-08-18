"""Unit tests for ``app.modules.biometric_enrollment.image_validation``.

Pure Pillow + stdlib content, no database. Every test writes bytes to a
``tmp_path`` file first (matching how the service always validates an
already-staged file, never in-memory bytes directly).
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from app.core.config import Settings
from app.modules.biometric_enrollment.errors import (
    EnrollmentImageAnimatedNotAllowedError,
    EnrollmentImageDecodeError,
    EnrollmentImageEmptyError,
    EnrollmentImageFormatNotAllowedError,
    EnrollmentImageMimeMismatchError,
    EnrollmentImageTooLargeDimensionsError,
)
from app.modules.biometric_enrollment.image_validation import validate_image_file

_VALID_SECRET = "a" * 40


def _settings(**overrides: Any) -> Settings:
    base_kwargs: dict[str, Any] = {
        "_env_file": None,
        "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/shikshasathi",
        "POSTGRES_DB": "shikshasathi",
        "POSTGRES_USER": "user",
        "POSTGRES_PASSWORD": "pass",
        "SECRET_KEY": _VALID_SECRET,
        "REFRESH_TOKEN_COOKIE_SECURE": True,
    }
    base_kwargs.update(overrides)
    return Settings(**base_kwargs)


def _write_jpeg(path: Path, *, size: tuple[int, int] = (200, 150)) -> None:
    Image.new("RGB", size, color=(10, 20, 30)).save(path, format="JPEG")


def _write_png(path: Path, *, size: tuple[int, int] = (100, 100)) -> None:
    Image.new("RGB", size, color=(40, 50, 60)).save(path, format="PNG")


def _write_animated_webp(path: Path) -> None:
    frames = [Image.new("RGB", (40, 40), color=(i * 20, i * 20, i * 20)) for i in range(4)]
    frames[0].save(
        path, format="WEBP", save_all=True, append_images=frames[1:], duration=100, loop=0
    )


def test_valid_jpeg_passes_and_returns_expected_metadata(tmp_path: Path) -> None:
    path = tmp_path / "photo.jpg"
    _write_jpeg(path, size=(200, 150))

    result = validate_image_file(path, settings=_settings())

    assert result.content_type == "image/jpeg"
    assert result.width_px == 200
    assert result.height_px == 150
    assert result.size_bytes == path.stat().st_size
    assert len(result.sha256_hash) == 64
    assert all(c in "0123456789abcdef" for c in result.sha256_hash)


def test_valid_png_passes(tmp_path: Path) -> None:
    path = tmp_path / "photo.png"
    _write_png(path)
    result = validate_image_file(path, settings=_settings())
    assert result.content_type == "image/png"


def test_empty_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "empty.jpg"
    path.write_bytes(b"")
    with pytest.raises(EnrollmentImageEmptyError):
        validate_image_file(path, settings=_settings())


def test_truncated_image_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "truncated.jpg"
    buffer = io.BytesIO()
    Image.new("RGB", (200, 150)).save(buffer, format="JPEG")
    full_bytes = buffer.getvalue()
    path.write_bytes(full_bytes[: len(full_bytes) // 2])
    with pytest.raises(EnrollmentImageDecodeError):
        validate_image_file(path, settings=_settings())


def test_non_image_content_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "not-an-image.jpg"
    path.write_bytes(b"this is definitely not an image file" * 5)
    with pytest.raises(EnrollmentImageDecodeError):
        validate_image_file(path, settings=_settings())


def test_unsupported_format_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "photo.bmp"
    Image.new("RGB", (50, 50)).save(path, format="BMP")
    with pytest.raises(EnrollmentImageFormatNotAllowedError):
        validate_image_file(path, settings=_settings())


def test_animated_image_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "animated.webp"
    _write_animated_webp(path)
    with pytest.raises(EnrollmentImageAnimatedNotAllowedError):
        validate_image_file(path, settings=_settings())


def test_dimension_over_configured_max_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "wide.jpg"
    _write_jpeg(path, size=(700, 100))
    settings = _settings(MAX_ENROLLMENT_IMAGE_DIMENSION_PX=500)
    with pytest.raises(EnrollmentImageTooLargeDimensionsError):
        validate_image_file(path, settings=settings)


def test_pixel_count_over_configured_max_is_rejected_even_within_per_side_limit(
    tmp_path: Path,
) -> None:
    """1100x1000 = 1_100_000px must be rejected when the pixel cap is lower.

    Lower than that, even though each side (1100, 1000) is individually
    well under the per-dimension cap — this is the decompression-bomb-
    style guard, not just a single-axis check.

    ``MAX_ENROLLMENT_IMAGE_PIXELS`` must stay >= 1_000_000 (see
    ``Settings``'s own field validator in app/core/config.py, which
    rejects anything lower at construction time) — 1_000_000 is the
    lowest legal configured cap, with the fixture image sized just over
    it so the guard is actually exercised.
    """
    path = tmp_path / "wide_square.jpg"
    _write_jpeg(path, size=(1100, 1000))
    settings = _settings(
        MAX_ENROLLMENT_IMAGE_DIMENSION_PX=6000, MAX_ENROLLMENT_IMAGE_PIXELS=1_000_000
    )
    with pytest.raises(EnrollmentImageTooLargeDimensionsError):
        validate_image_file(path, settings=settings)


def test_declared_mime_mismatch_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "actually-jpeg.jpg"
    _write_jpeg(path)
    with pytest.raises(EnrollmentImageMimeMismatchError):
        validate_image_file(path, settings=_settings(), declared_content_type="image/png")


def test_declared_mime_matching_actual_format_is_accepted(tmp_path: Path) -> None:
    path = tmp_path / "actually-jpeg-2.jpg"
    _write_jpeg(path)
    result = validate_image_file(path, settings=_settings(), declared_content_type="image/jpeg")
    assert result.content_type == "image/jpeg"


def test_unrecognized_declared_content_type_is_not_compared(tmp_path: Path) -> None:
    """A generic/unknown Content-Type header is not treated as an assertion."""
    path = tmp_path / "actually-jpeg-3.jpg"
    _write_jpeg(path)
    result = validate_image_file(
        path, settings=_settings(), declared_content_type="application/octet-stream"
    )
    assert result.content_type == "image/jpeg"


def test_sha256_is_deterministic_for_identical_bytes(tmp_path: Path) -> None:
    path_a = tmp_path / "a.jpg"
    path_b = tmp_path / "b.jpg"
    _write_jpeg(path_a, size=(123, 456))
    path_b.write_bytes(path_a.read_bytes())

    result_a = validate_image_file(path_a, settings=_settings())
    result_b = validate_image_file(path_b, settings=_settings())
    assert result_a.sha256_hash == result_b.sha256_hash
