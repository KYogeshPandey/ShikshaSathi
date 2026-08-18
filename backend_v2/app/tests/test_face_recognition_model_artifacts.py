"""Tests for ``app.modules.face_recognition.model_artifacts``."""

from __future__ import annotations

import hashlib

import pytest

from app.modules.face_recognition.errors import (
    ModelArtifactChecksumMismatchError,
    ModelArtifactMissingError,
)
from app.modules.face_recognition.model_artifacts import compute_sha256, verify_model_artifact


def test_verify_model_artifact_raises_missing_for_nonexistent_path(tmp_path) -> None:
    with pytest.raises(ModelArtifactMissingError):
        verify_model_artifact(tmp_path / "does-not-exist.bin", expected_sha256=None)


def test_verify_model_artifact_raises_missing_for_directory(tmp_path) -> None:
    directory = tmp_path / "a-directory"
    directory.mkdir()
    with pytest.raises(ModelArtifactMissingError):
        verify_model_artifact(directory, expected_sha256=None)


def test_verify_model_artifact_succeeds_with_no_checksum_configured(tmp_path) -> None:
    path = tmp_path / "model.bin"
    path.write_bytes(b"anything")
    verify_model_artifact(path, expected_sha256=None)  # must not raise


def test_verify_model_artifact_succeeds_with_matching_checksum(tmp_path) -> None:
    content = b"a model artifact's bytes"
    path = tmp_path / "model.bin"
    path.write_bytes(content)
    expected = hashlib.sha256(content).hexdigest()
    verify_model_artifact(path, expected_sha256=expected)  # must not raise


def test_verify_model_artifact_raises_on_checksum_mismatch(tmp_path) -> None:
    path = tmp_path / "model.bin"
    path.write_bytes(b"real content")
    with pytest.raises(ModelArtifactChecksumMismatchError):
        verify_model_artifact(path, expected_sha256="0" * 64)


def test_verify_model_artifact_checksum_comparison_is_case_insensitive(tmp_path) -> None:
    content = b"case insensitivity check"
    path = tmp_path / "model.bin"
    path.write_bytes(content)
    expected_upper = hashlib.sha256(content).hexdigest().upper()
    verify_model_artifact(path, expected_sha256=expected_upper)  # must not raise


def test_compute_sha256_matches_hashlib_reference(tmp_path) -> None:
    content = b"some bytes to hash" * 1000
    path = tmp_path / "big.bin"
    path.write_bytes(content)

    assert compute_sha256(path) == hashlib.sha256(content).hexdigest()


def test_verify_model_artifact_error_messages_never_contain_the_path(tmp_path) -> None:
    path = tmp_path / "super-secret-directory-name" / "model.bin"
    try:
        verify_model_artifact(path, expected_sha256=None)
    except ModelArtifactMissingError as exc:
        assert "super-secret-directory-name" not in str(exc)
        assert str(path) not in str(exc)
    else:
        pytest.fail("expected ModelArtifactMissingError")
