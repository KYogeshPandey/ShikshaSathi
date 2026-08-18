"""Model artifact existence/integrity validation — Phase 5 Stage 3.

Shared by both provider adapters
(``app.modules.face_recognition.providers.yunet_detector``,
``app.modules.face_recognition.providers.dlib_embedder``) and
``app.modules.face_recognition.health`` so "does this configured model
file actually exist, and does it match the expected checksum if one is
configured" is checked exactly one way, everywhere.

**No model weight of any kind is downloaded, vendored, or committed by
this module or anywhere else in this checkpoint** (Stage 3 brief,
instruction 11/18). ``Settings.FACE_DETECTOR_MODEL_PATH`` /
``FACE_EMBEDDER_MODEL_PATH`` are deployer-supplied paths to files the
deployer has obtained and placed outside this repository — see
``docs/HANDOVER_PHASE_5_STAGE_3.md``, "Model distribution strategy".

Checksum verification is optional (``expected_sha256`` may be ``None``)
— a deployer who has not yet pinned a checksum still gets the
existence check, but not tamper/corruption detection. This mirrors
this project's existing pattern of layering "does this pass a basic
sanity check" ahead of "does this pass a stronger, opt-in check" rather
than making the stronger check mandatory before any deployment can run
at all.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.modules.face_recognition.errors import (
    ModelArtifactChecksumMismatchError,
    ModelArtifactMissingError,
)

_HASH_CHUNK_SIZE = 1024 * 1024


def compute_sha256(path: Path) -> str:
    """Chunked SHA-256 over a model file (never loads the whole file into memory)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model_artifact(path: Path, *, expected_sha256: str | None) -> None:
    """Raise a typed error if ``path`` is missing, unreadable, or checksum-mismatched.

    Returns ``None`` (no value) on success. Never raises a bare
    ``OSError``/``FileNotFoundError`` — always one of this module's two
    provider-neutral errors, and never includes the actual path or
    actual/expected checksum in the raised error's client-facing
    message (both are already the case for
    ``ModelArtifactMissingError``/``ModelArtifactChecksumMismatchError``
    themselves — see ``app.modules.face_recognition.errors``).
    """
    try:
        if not path.is_file():
            raise ModelArtifactMissingError()
    except OSError as exc:
        raise ModelArtifactMissingError() from exc

    if expected_sha256:
        normalized_expected = expected_sha256.strip().lower()
        try:
            actual = compute_sha256(path)
        except OSError as exc:
            raise ModelArtifactMissingError() from exc
        if actual != normalized_expected:
            raise ModelArtifactChecksumMismatchError()
