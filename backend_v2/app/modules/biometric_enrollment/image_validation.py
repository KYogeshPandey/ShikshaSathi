"""Decoded-content image validation for biometric enrollment uploads.

Stage 2 adds exactly one new runtime dependency for this: **Pillow**
(``PIL``), a maintained, widely-used image-decoding library — already
listed as justified in docs/HANDOVER_PHASE_5_STAGE_2.md. Nothing here
detects a face, aligns anything, or produces an embedding; every check
below answers only "is this a safe, decodable, reasonably-sized still
image of an allowed format", never "does this image contain a face".

Every validation decision is made from the **decoded** image content —
Pillow's own format sniffing — never from the client-declared
``Content-Type`` header or the original filename's extension. Both of
those are read only as optional secondary signals for the mismatch
check at the end, which is intentionally the last check (every
content-derived fact is already known and safe by that point).

**Stage 3 correction note:** the actual decode/bomb/format/dimension/
animated checks below (``_validate_decoded_bytes``) are shared with
``app.modules.face_recognition.match_probe_validation``, which applies
the same protection class to in-memory match-probe uploads (there is
no staged file on disk for a probe — it is never persisted). That
sharing is why the core check is factored out as a private,
error-taxonomy-neutral function raising ``_ImageContentRejected``:
Stage 2's ``Enrollment*`` errors must not leak into Stage 3's
match-probe API, and vice versa, so each public entry point in its own
module translates the same private signal into its own domain errors.
Nothing about Stage 2's own public behavior below (``validate_image_file``,
``ValidatedImage``, the ``Enrollment*`` errors raised) has changed.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.core.config import Settings
from app.modules.biometric_enrollment.errors import (
    EnrollmentImageAnimatedNotAllowedError,
    EnrollmentImageDecodeError,
    EnrollmentImageDimensionsInvalidError,
    EnrollmentImageEmptyError,
    EnrollmentImageFormatNotAllowedError,
    EnrollmentImageMimeMismatchError,
    EnrollmentImageTooLargeDimensionsError,
)

# Pillow format name -> canonical MIME type. Deliberately small: only
# formats this application is prepared to store and, later, hand to a
# Stage 3 detector are accepted.
_ALLOWED_FORMATS: dict[str, str] = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}

# Content-Type header values we recognize as *claiming* to be one of the
# formats above. Anything else in the header (or a missing/blank header)
# is treated as "no assertion" and is not compared — this method never
# trusts the header as the source of truth, only as an optional
# consistency check against it.
_RECOGNIZED_DECLARED_TYPES: dict[str, str] = {
    "image/jpeg": "JPEG",
    "image/jpg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}


@dataclass(frozen=True)
class ValidatedImage:
    """Safe, decoded-content metadata about one accepted image.

    Never carries pixel data — only what is safe to persist as
    ``BiometricSample`` metadata.
    """

    content_type: str
    width_px: int
    height_px: int
    size_bytes: int
    sha256_hash: str


@dataclass(frozen=True)
class ValidatedImageContent:
    """Safe, decoded-content metadata shared by every caller of
    ``_validate_decoded_bytes`` — a strict subset of ``ValidatedImage``
    that omits ``size_bytes``/``sha256_hash`` (file-specific concerns
    that only ``validate_image_file`` has a file to compute)."""

    content_type: str
    image_format: str
    width_px: int
    height_px: int


class _ImageContentRejected(Exception):
    """Module-private, taxonomy-neutral rejection signal.

    Raised only by ``_validate_decoded_bytes`` and caught only by the
    public wrappers in this module and in
    ``app.modules.face_recognition.match_probe_validation`` — never
    propagated past either module's own boundary. Carries just enough
    structure (``kind``, and ``allowed_formats`` for the one kind that
    needs it) for each wrapper to raise its own domain-specific error
    type with its own message/status code.
    """

    def __init__(self, kind: str, *, allowed_formats: frozenset[str] | None = None) -> None:
        self.kind = kind
        self.allowed_formats = allowed_formats
        super().__init__(kind)


# Stage 3 v4 correction: image validation must not mutate Pillow process-global
# state.  Stage 2 and Stage 3 callers can run concurrently (Stage 3 uses
# ``asyncio.to_thread``), while ``Image.MAX_IMAGE_PIXELS`` is shared by the
# entire process and is consulted by *every* ``Image.open`` call.  Earlier
# implementations temporarily replaced that global with each request's local
# ``max_pixels`` value, which allowed one request to change another request's
# validation semantics.  Application-specific limits are therefore enforced
# exclusively from the decoded header dimensions below; Pillow's own global
# bomb guard remains untouched as an independent, process-wide safety net.


def sha256_of_file(path: Path) -> str:
    """Chunked SHA-256 over a file already written to disk.

    Reads in bounded chunks (never the whole file into one ``bytes``
    object at once) — the file's size is already bounded by the staging
    write's byte cap by the time this runs, but this keeps the pattern
    consistent for any future caller with a larger cap.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_decoded_bytes(
    data: bytes,
    *,
    max_pixels: int,
    max_dimension: int,
    declared_content_type: str | None,
) -> ValidatedImageContent:
    """The actual decode/bomb/format/dimension/animated/mime checks.

    Shared, byte-buffer-only core used by both ``validate_image_file``
    below (Stage 2, file-on-disk) and
    ``app.modules.face_recognition.match_probe_validation.validate_probe_image_bytes``
    (Stage 3, in-memory only, never staged to disk). Raises
    ``_ImageContentRejected`` — never a Stage 2 ``Enrollment*`` error and
    never a bare Pillow/stdlib exception — so this function has no
    opinion about which domain is calling it.
    """
    if not data:
        raise _ImageContentRejected("empty")

    # Parse only the image header first.  ``Image.open`` may apply Pillow's
    # own process-wide decompression-bomb policy; we never replace that global
    # threshold.  The application's request-specific limits are enforced from
    # the declared dimensions before any full pixel-plane decode occurs.
    try:
        with Image.open(BytesIO(data)) as header_probe:
            declared_width, declared_height = header_probe.size
    except Image.DecompressionBombError as exc:
        raise _ImageContentRejected("too_large") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise _ImageContentRejected("decode") from exc

    if declared_width <= 0 or declared_height <= 0:
        raise _ImageContentRejected("dimensions_invalid")
    if declared_width > max_dimension or declared_height > max_dimension:
        raise _ImageContentRejected("too_large")
    if declared_width * declared_height > max_pixels:
        raise _ImageContentRejected("too_large")

    # Verify the encoded stream, then reopen and force a complete decode.
    # Pillow's own global bomb guard remains active and unchanged throughout;
    # application-specific limits are rechecked below against the decoded
    # image metadata so each concurrent request is governed only by its own
    # ``max_pixels``/``max_dimension`` values.
    try:
        with Image.open(BytesIO(data)) as probe:
            probe.verify()
    except Image.DecompressionBombError as exc:
        raise _ImageContentRejected("too_large") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise _ImageContentRejected("decode") from exc

    # ``verify()`` leaves the Image object unusable for further reads
    # (Pillow's documented contract), so a fresh open is required.
    try:
        with Image.open(BytesIO(data)) as image:
            image_format = image.format
            width, height = image.size
            is_animated = bool(getattr(image, "is_animated", False)) or (
                getattr(image, "n_frames", 1) > 1
            )
            # Force full pixel-plane decode now (not just header parsing) so a
            # truncated body fails here rather than on first later use.
            image.load()
    except Image.DecompressionBombError as exc:
        raise _ImageContentRejected("too_large") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise _ImageContentRejected("decode") from exc

    if image_format not in _ALLOWED_FORMATS:
        raise _ImageContentRejected("format", allowed_formats=frozenset(_ALLOWED_FORMATS.values()))

    if width <= 0 or height <= 0:
        raise _ImageContentRejected("dimensions_invalid")

    if width > max_dimension or height > max_dimension:
        raise _ImageContentRejected("too_large")
    if width * height > max_pixels:
        raise _ImageContentRejected("too_large")

    if is_animated:
        raise _ImageContentRejected("animated")

    content_type = _ALLOWED_FORMATS[image_format]

    normalized_declared = (declared_content_type or "").split(";", 1)[0].strip().lower()
    if (
        normalized_declared
        and normalized_declared in _RECOGNIZED_DECLARED_TYPES
        and _RECOGNIZED_DECLARED_TYPES[normalized_declared] != image_format
    ):
        raise _ImageContentRejected("mime_mismatch")

    return ValidatedImageContent(
        content_type=content_type,
        image_format=image_format,
        width_px=width,
        height_px=height,
    )


def validate_image_file(
    path: Path,
    *,
    settings: Settings,
    declared_content_type: str | None = None,
) -> ValidatedImage:
    """Validate an already-staged file's content and return safe metadata.

    Raises one of the ``Enrollment*`` errors in
    app.modules.biometric_enrollment.errors on any problem. Never raises
    a bare Pillow/stdlib exception to a caller outside this module.
    """
    size_bytes = path.stat().st_size
    if size_bytes == 0:
        raise EnrollmentImageEmptyError()

    data = path.read_bytes()

    try:
        content = _validate_decoded_bytes(
            data,
            max_pixels=settings.MAX_ENROLLMENT_IMAGE_PIXELS,
            max_dimension=settings.MAX_ENROLLMENT_IMAGE_DIMENSION_PX,
            declared_content_type=declared_content_type,
        )
    except _ImageContentRejected as exc:
        raise _translate_enrollment_rejection(exc) from exc

    return ValidatedImage(
        content_type=content.content_type,
        width_px=content.width_px,
        height_px=content.height_px,
        size_bytes=size_bytes,
        sha256_hash=sha256_of_file(path),
    )


def _translate_enrollment_rejection(exc: _ImageContentRejected) -> Exception:
    """Stage 2's translation of the shared, taxonomy-neutral signal.

    Kept as a small mapping (not a giant if/elif chain) so this stays a
    one-line addition if a new ``kind`` is ever introduced.
    """
    if exc.kind == "empty":
        return EnrollmentImageEmptyError()
    if exc.kind == "decode":
        return EnrollmentImageDecodeError()
    if exc.kind == "format":
        assert exc.allowed_formats is not None
        return EnrollmentImageFormatNotAllowedError(exc.allowed_formats)
    if exc.kind == "dimensions_invalid":
        return EnrollmentImageDimensionsInvalidError()
    if exc.kind == "too_large":
        return EnrollmentImageTooLargeDimensionsError()
    if exc.kind == "animated":
        return EnrollmentImageAnimatedNotAllowedError()
    if exc.kind == "mime_mismatch":
        return EnrollmentImageMimeMismatchError()
    raise AssertionError(f"unhandled image rejection kind: {exc.kind!r}")  # pragma: no cover
