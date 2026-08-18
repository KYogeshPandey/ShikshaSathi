"""Tests for ``app.modules.face_recognition.match_probe_validation`` — Stage 3
correction, finding 5 ("match-probe image safety").

Deliberately mirrors ``test_phase5_stage2_image_validation.py`` test-for-test
(same fixture builders, same coverage shape) since this module exists
specifically to bring probe images up to that same protection class by
reusing its actual check logic (``image_validation._validate_decoded_bytes``)
— see ``match_probe_validation.py``'s module docstring. Pure Pillow + stdlib
content, no database, no staged file (probe bytes are validated in memory,
matching how ``/match-probe`` actually receives them).
"""

from __future__ import annotations

import io
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from PIL import Image

from app.core.config import Settings
from app.modules.face_recognition.errors import (
    MatchProbeImageAnimatedNotAllowedError,
    MatchProbeImageDecodeError,
    MatchProbeImageDimensionsTooLargeError,
    MatchProbeImageEmptyError,
    MatchProbeImageFormatNotAllowedError,
    MatchProbeImageMimeMismatchError,
)
from app.modules.face_recognition.match_probe_validation import validate_probe_image_bytes

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


def _jpeg_bytes(*, size: tuple[int, int] = (200, 150)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color=(10, 20, 30)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _png_bytes(*, size: tuple[int, int] = (100, 100)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color=(40, 50, 60)).save(buffer, format="PNG")
    return buffer.getvalue()


def _animated_webp_bytes() -> bytes:
    frames = [Image.new("RGB", (40, 40), color=(i * 20, i * 20, i * 20)) for i in range(4)]
    buffer = io.BytesIO()
    frames[0].save(
        buffer, format="WEBP", save_all=True, append_images=frames[1:], duration=100, loop=0
    )
    return buffer.getvalue()


def test_valid_jpeg_probe_is_accepted_and_returns_expected_metadata() -> None:
    result = validate_probe_image_bytes(_jpeg_bytes(size=(200, 150)), settings=_settings())
    assert result.content_type == "image/jpeg"
    assert result.width_px == 200
    assert result.height_px == 150


def test_valid_png_probe_is_accepted() -> None:
    result = validate_probe_image_bytes(_png_bytes(), settings=_settings())
    assert result.content_type == "image/png"


def test_empty_probe_is_rejected() -> None:
    with pytest.raises(MatchProbeImageEmptyError):
        validate_probe_image_bytes(b"", settings=_settings())


def test_truncated_probe_is_rejected_as_malformed() -> None:
    full_bytes = _jpeg_bytes(size=(200, 150))
    with pytest.raises(MatchProbeImageDecodeError):
        validate_probe_image_bytes(full_bytes[: len(full_bytes) // 2], settings=_settings())


def test_non_image_content_is_rejected_as_malformed() -> None:
    with pytest.raises(MatchProbeImageDecodeError):
        validate_probe_image_bytes(
            b"this is definitely not an image file" * 5, settings=_settings()
        )


def test_unsupported_format_is_rejected() -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (50, 50)).save(buffer, format="BMP")
    with pytest.raises(MatchProbeImageFormatNotAllowedError) as exc_info:
        validate_probe_image_bytes(buffer.getvalue(), settings=_settings())
    # Sanitized: only the allowed-format list, never anything about the
    # actual (rejected) format or any file/path detail.
    assert exc_info.value.details == {"allowed_formats": ["image/jpeg", "image/png", "image/webp"]}


def test_animated_probe_is_rejected() -> None:
    with pytest.raises(MatchProbeImageAnimatedNotAllowedError):
        validate_probe_image_bytes(_animated_webp_bytes(), settings=_settings())


def test_probe_dimension_over_configured_max_is_rejected() -> None:
    settings = _settings(MAX_ENROLLMENT_IMAGE_DIMENSION_PX=500)
    with pytest.raises(MatchProbeImageDimensionsTooLargeError):
        validate_probe_image_bytes(_jpeg_bytes(size=(700, 100)), settings=settings)


def test_probe_pixel_count_over_configured_max_is_rejected_decompression_bomb_style() -> None:
    """Decompression-bomb-style guard: 1100x1000 = 1_100_000px rejected by the
    pixel cap even though each side is individually within the per-dimension
    cap — this is the same protection Pillow's own ``DecompressionBombError``/
    ``MAX_IMAGE_PIXELS`` guard provides against a "small file, huge claimed
    resolution" upload, not just an oversized-single-axis check. Mirrors
    ``test_phase5_stage2_image_validation.py``'s equivalent test exactly."""
    settings = _settings(
        MAX_ENROLLMENT_IMAGE_DIMENSION_PX=6000, MAX_ENROLLMENT_IMAGE_PIXELS=1_000_000
    )
    with pytest.raises(MatchProbeImageDimensionsTooLargeError):
        validate_probe_image_bytes(_jpeg_bytes(size=(1100, 1000)), settings=settings)


def test_probe_declared_mime_mismatch_is_rejected() -> None:
    with pytest.raises(MatchProbeImageMimeMismatchError):
        validate_probe_image_bytes(
            _jpeg_bytes(), settings=_settings(), declared_content_type="image/png"
        )


def test_probe_declared_mime_matching_actual_format_is_accepted() -> None:
    result = validate_probe_image_bytes(
        _jpeg_bytes(), settings=_settings(), declared_content_type="image/jpeg"
    )
    assert result.content_type == "image/jpeg"


def test_probe_unrecognized_declared_content_type_is_not_compared() -> None:
    result = validate_probe_image_bytes(
        _jpeg_bytes(), settings=_settings(), declared_content_type="application/octet-stream"
    )
    assert result.content_type == "image/jpeg"


def test_probe_errors_never_carry_a_filesystem_path_or_raw_exception_text() -> None:
    """Sanitization guard for every ``MatchProbeImage*`` error this module raises:
    none of them are constructed with a path, filename, or interpolated
    exception message — every message is a short, fixed string with no
    absolute-path-shaped substring (``/some/dir/...`` or ``C:\\...``)."""
    errors = [
        MatchProbeImageEmptyError(),
        MatchProbeImageDecodeError(),
        MatchProbeImageFormatNotAllowedError(frozenset({"image/jpeg"})),
        MatchProbeImageDimensionsTooLargeError(),
        MatchProbeImageAnimatedNotAllowedError(),
        MatchProbeImageMimeMismatchError(),
    ]
    for error in errors:
        assert not re.search(r"(/[\w.-]+){2,}|[A-Za-z]:\\", error.message)
        assert "Traceback" not in error.message
        assert error.status_code in (400, 413, 422)


def test_concurrent_probe_validation_does_not_corrupt_image_max_image_pixels() -> None:
    """Stage 3 v3 correction regression test.

    Independently reproduced before this fix: ``_validate_decoded_bytes``
    temporarily mutated the process-global ``Image.MAX_IMAGE_PIXELS`` to
    match each call's configured pixel cap, then restored it — but with no
    synchronization. Once match-probe validation started running via
    ``asyncio.to_thread`` (a real OS thread pool), two concurrent probe
    validations could interleave that mutate/restore pair on two different
    threads. Observed failure mode: Pillow's real default (89478485) ended
    up permanently stuck at a smaller configured value (30000000) after
    concurrent validations.

    This test drives many concurrent validations, each configured with a
    *different* pixel cap (so the global is actually being set to differing
    values, not the same one repeatedly — a same-value repeat would
    trivially "pass" even without the fix and prove nothing), using a tiny,
    cheap-to-decode fixture (no giant in-memory image). It asserts both that
    every validation still produced the correct result (the fix must not
    have broken correctness) and, more importantly, that
    ``Image.MAX_IMAGE_PIXELS`` is back to its true original value afterward
    — the exact symptom that was independently reproduced.
    """
    true_original_max_image_pixels = Image.MAX_IMAGE_PIXELS

    # Five distinct configured caps, all comfortably above the tiny 50x50
    # fixture's 2500 pixels, so every single validation call is expected to
    # succeed — any unexpected rejection below is itself a correctness bug,
    # not an intentional part of this test.
    pixel_cap_variants = [1_000_000, 2_000_000, 5_000_000, 10_000_000, 20_000_000]
    settings_variants = [_settings(MAX_ENROLLMENT_IMAGE_PIXELS=cap) for cap in pixel_cap_variants]
    payload = _jpeg_bytes(size=(50, 50))

    errors: list[BaseException] = []
    results: list[Any] = []
    results_lock = threading.Lock()

    def worker(settings: Settings) -> None:
        try:
            result = validate_probe_image_bytes(payload, settings=settings)
        except BaseException as exc:
            with results_lock:
                errors.append(exc)
        else:
            with results_lock:
                results.append(result)

    thread_count = 60
    threads = [
        threading.Thread(target=worker, args=(settings_variants[i % len(settings_variants)],))
        for i in range(thread_count)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == [], f"unexpected validation errors under concurrency: {errors!r}"
    assert len(results) == thread_count
    assert all(result.content_type == "image/jpeg" for result in results)
    assert all(result.width_px == 50 and result.height_px == 50 for result in results)

    # The actual regression this test guards against: the global must be
    # restored to its true original value, not left stuck at one of the
    # five configured caps above (or any other value).
    assert true_original_max_image_pixels == Image.MAX_IMAGE_PIXELS


def test_concurrent_probe_validation_uses_request_local_limits_without_global_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stage 3 v4 regression: one request must never change another request's Pillow policy.

    The v3 lock serialized the temporary ``Image.MAX_IMAGE_PIXELS`` mutation,
    but a different thread could still execute its *header* ``Image.open``
    while that global held another request's smaller cap.  A 2.5M-pixel image
    that is valid for a 3M-cap request could therefore be falsely rejected
    while a concurrent 1M-cap request was inside its critical section.

    V4 removes request-specific mutation of Pillow's process-global setting
    entirely.  This test checks both semantics at once: the 1M request rejects
    the image, the 3M request accepts it, and every ``Image.open`` observes the
    same untouched global Pillow threshold.
    """
    payload = _jpeg_bytes(size=(2500, 1000))  # 2_500_000 pixels
    small_settings = _settings(
        MAX_ENROLLMENT_IMAGE_PIXELS=1_000_000,
        MAX_ENROLLMENT_IMAGE_DIMENSION_PX=6000,
    )
    large_settings = _settings(
        MAX_ENROLLMENT_IMAGE_PIXELS=3_000_000,
        MAX_ENROLLMENT_IMAGE_DIMENSION_PX=6000,
    )

    original_open = Image.open
    original_max_image_pixels = Image.MAX_IMAGE_PIXELS
    observed_globals: list[int | None] = []
    observed_lock = threading.Lock()

    def observing_open(*args: Any, **kwargs: Any) -> Any:
        with observed_lock:
            observed_globals.append(Image.MAX_IMAGE_PIXELS)
        return original_open(*args, **kwargs)

    monkeypatch.setattr(Image, "open", observing_open)

    def validate_small() -> str:
        with pytest.raises(MatchProbeImageDimensionsTooLargeError):
            validate_probe_image_bytes(payload, settings=small_settings)
        return "small-rejected"

    def validate_large() -> str:
        result = validate_probe_image_bytes(payload, settings=large_settings)
        assert result.width_px == 2500
        assert result.height_px == 1000
        return "large-accepted"

    jobs = [validate_small, validate_large] * 6
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda job: job(), jobs))

    assert results.count("small-rejected") == 6
    assert results.count("large-accepted") == 6
    assert observed_globals
    assert all(value == original_max_image_pixels for value in observed_globals)
    assert original_max_image_pixels == Image.MAX_IMAGE_PIXELS
