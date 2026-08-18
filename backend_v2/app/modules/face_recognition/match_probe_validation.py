"""Decoded-content image validation for the ``/match-probe`` endpoint.

Stage 3 correction (finding 5): the probe upload previously only enforced
an encoded-byte-count cap (``router._MAX_PROBE_IMAGE_BYTES``) before handing
the bytes straight to ``PIL.Image.open(...).convert("RGB")`` — none of
Stage 2's decoded-content protections (decompression-bomb guard, max pixel
count, max width/height, format allowlist, animated-image rejection, full
decode verification) applied to a probe image.

This module brings probe images up to the same protection class by
reusing — not duplicating — the actual check logic in
``app.modules.biometric_enrollment.image_validation._validate_decoded_bytes``.
A probe image is never staged to disk and never persisted (see
``app.modules.face_recognition.router``'s match-probe docstring: it is a
diagnostic/matching operation only), so this module has no file-based
entry point, only a bytes-based one, and never touches Stage 2's
``ValidatedImage``/``Enrollment*`` types or errors — see
``app.modules.face_recognition.errors``'s "match-probe image validation"
section for why a separate, provider-neutral error vocabulary is used here.

Reuses the same configured limits Stage 2 enrollment uses
(``Settings.MAX_ENROLLMENT_IMAGE_PIXELS`` /
``Settings.MAX_ENROLLMENT_IMAGE_DIMENSION_PX``) — these are general
"safe decoded image for this application's face pipeline" limits, not an
enrollment-specific business rule, so introducing a parallel
``MAX_MATCH_PROBE_IMAGE_*`` settings surface for the same protection class
would be duplication without a behavioral reason.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.modules.biometric_enrollment.image_validation import (
    ValidatedImageContent,
    _ImageContentRejected,
    _validate_decoded_bytes,
)
from app.modules.face_recognition.errors import (
    MatchProbeImageAnimatedNotAllowedError,
    MatchProbeImageDecodeError,
    MatchProbeImageDimensionsInvalidError,
    MatchProbeImageDimensionsTooLargeError,
    MatchProbeImageEmptyError,
    MatchProbeImageFormatNotAllowedError,
    MatchProbeImageMimeMismatchError,
)


@dataclass(frozen=True)
class ValidatedProbeImage:
    """Safe, decoded-content metadata about one accepted probe image.

    Never carries pixel data. Deliberately has no ``sha256_hash`` field
    (unlike Stage 2's ``ValidatedImage``) — a probe image is never
    persisted, so there is nothing meaningful to hash for storage
    deduplication; callers that want an opaque identifier for audit
    logging should hash the *embedding*, not this transient upload.
    """

    content_type: str
    width_px: int
    height_px: int


def validate_probe_image_bytes(
    data: bytes,
    *,
    settings: Settings,
    declared_content_type: str | None = None,
) -> ValidatedProbeImage:
    """Validate in-memory match-probe bytes and return safe metadata.

    Raises one of the ``MatchProbeImage*`` errors in
    ``app.modules.face_recognition.errors`` on any problem. Never raises a
    bare Pillow/stdlib exception, and never raises a Stage 2 ``Enrollment*``
    error even though the underlying check logic is shared with Stage 2.

    This is a pure, synchronous, CPU/IO-bound function (full Pillow decode
    of an arbitrary-sized buffer) — callers on the FastAPI request path
    must run it via ``asyncio.to_thread`` rather than call it directly on
    the event loop (see Stage 3 correction finding 3, enforced in
    ``app.modules.face_recognition.router.match_probe``).
    """
    try:
        content: ValidatedImageContent = _validate_decoded_bytes(
            data,
            max_pixels=settings.MAX_ENROLLMENT_IMAGE_PIXELS,
            max_dimension=settings.MAX_ENROLLMENT_IMAGE_DIMENSION_PX,
            declared_content_type=declared_content_type,
        )
    except _ImageContentRejected as exc:
        raise _translate_match_probe_rejection(exc) from exc

    return ValidatedProbeImage(
        content_type=content.content_type,
        width_px=content.width_px,
        height_px=content.height_px,
    )


def _translate_match_probe_rejection(exc: _ImageContentRejected) -> Exception:
    """Stage 3's translation of the shared, taxonomy-neutral signal.

    Mirrors ``image_validation._translate_enrollment_rejection`` exactly,
    one-to-one by ``kind`` — only the resulting error *type* differs.
    """
    if exc.kind == "empty":
        return MatchProbeImageEmptyError()
    if exc.kind == "decode":
        return MatchProbeImageDecodeError()
    if exc.kind == "format":
        assert exc.allowed_formats is not None
        return MatchProbeImageFormatNotAllowedError(exc.allowed_formats)
    if exc.kind == "dimensions_invalid":
        return MatchProbeImageDimensionsInvalidError()
    if exc.kind == "too_large":
        return MatchProbeImageDimensionsTooLargeError()
    if exc.kind == "animated":
        return MatchProbeImageAnimatedNotAllowedError()
    if exc.kind == "mime_mismatch":
        return MatchProbeImageMimeMismatchError()
    raise AssertionError(f"unhandled image rejection kind: {exc.kind!r}")  # pragma: no cover
