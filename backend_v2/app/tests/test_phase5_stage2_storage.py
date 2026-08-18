"""Unit tests for ``app.modules.biometric_enrollment.storage``.

No database or network needed — every test uses a ``tmp_path``-backed
``PrivateBiometricStorage`` and a directly-constructed ``Settings``
instance, matching ``app.tests.test_config``'s pattern for isolated
``Settings`` construction.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from app.core.config import Settings
from app.modules.biometric_enrollment.storage import (
    BiometricStorageInvariantError,
    PrivateBiometricStorage,
    StorageCapExceededError,
)

_VALID_SECRET = "a" * 40


def _settings(tmp_path: Path, **overrides: Any) -> Settings:
    base_kwargs: dict[str, Any] = {
        "_env_file": None,
        "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/shikshasathi",
        "POSTGRES_DB": "shikshasathi",
        "POSTGRES_USER": "user",
        "POSTGRES_PASSWORD": "pass",
        "SECRET_KEY": _VALID_SECRET,
        "REFRESH_TOKEN_COOKIE_SECURE": True,
        "BIOMETRIC_STORAGE_ROOT": str(tmp_path / "biometric_data"),
    }
    base_kwargs.update(overrides)
    return Settings(**base_kwargs)


async def _chunks(*payloads: bytes) -> AsyncIterator[bytes]:
    for payload in payloads:
        yield payload


def test_storage_creates_private_zone_directories(tmp_path: Path) -> None:
    storage = PrivateBiometricStorage(_settings(tmp_path))
    root = Path(_settings(tmp_path).BIOMETRIC_STORAGE_ROOT)
    for zone in ("staging", "active", "quarantine", "bulk_staging"):
        assert (root / zone).is_dir()
    assert storage.list_active_keys() == set()


def test_new_key_is_32_char_hex(tmp_path: Path) -> None:
    key_pattern = re.compile(r"^[0-9a-f]{32}$")
    storage = PrivateBiometricStorage(_settings(tmp_path))
    assert key_pattern.match(storage.new_key())


async def test_write_staged_then_promote_then_active(tmp_path: Path) -> None:
    storage = PrivateBiometricStorage(_settings(tmp_path))
    key = storage.new_key()

    staged = await storage.write_staged(key, _chunks(b"hello ", b"world"), max_bytes=1024)
    assert staged.size_bytes == 11
    assert storage.exists_staged(key) is True
    assert storage.exists_active(key) is False

    storage.promote(key)
    assert storage.exists_staged(key) is False
    assert storage.exists_active(key) is True
    assert storage.active_path(key).read_bytes() == b"hello world"


async def test_write_staged_enforces_byte_cap_and_cleans_up(tmp_path: Path) -> None:
    storage = PrivateBiometricStorage(_settings(tmp_path))
    key = storage.new_key()

    with pytest.raises(StorageCapExceededError):
        await storage.write_staged(key, _chunks(b"a" * 10, b"b" * 10), max_bytes=15)

    # Failed validation must leave no file behind at all.
    assert storage.exists_staged(key) is False


async def test_full_lifecycle_promote_quarantine_purge(tmp_path: Path) -> None:
    storage = PrivateBiometricStorage(_settings(tmp_path))
    key = storage.new_key()
    await storage.write_staged(key, _chunks(b"sample-bytes"), max_bytes=1024)
    storage.promote(key)

    storage.quarantine(key)
    assert storage.exists_active(key) is False
    assert storage.exists_quarantined(key) is True

    storage.purge_quarantined(key)
    assert storage.exists_quarantined(key) is False

    # Purging an already-purged key is a retryable no-op, not an error.
    storage.purge_quarantined(key)


def test_discard_staged_is_idempotent_on_missing_file(tmp_path: Path) -> None:
    storage = PrivateBiometricStorage(_settings(tmp_path))
    key = storage.new_key()
    storage.discard_staged(key)  # never written — must not raise
    storage.discard_staged(key)  # calling twice must also not raise


def test_list_keys_reflect_actual_files_per_zone(tmp_path: Path) -> None:
    storage = PrivateBiometricStorage(_settings(tmp_path))
    key_a = storage.new_key()
    key_b = storage.new_key()
    storage.active_path(key_a).write_bytes(b"a")
    storage.active_path(key_b).write_bytes(b"b")
    assert storage.list_active_keys() == {key_a, key_b}


def test_internal_key_validation_rejects_non_server_generated_keys(tmp_path: Path) -> None:
    """Defense in depth: even an internal-only malformed key must not build a path.

    No external input ever reaches ``key`` (see this module's docstring)
    — this asserts the *invariant*, not a reachable attacker path.
    """
    storage = PrivateBiometricStorage(_settings(tmp_path))
    with pytest.raises(BiometricStorageInvariantError):
        storage.staging_path("../../etc/passwd")
    with pytest.raises(BiometricStorageInvariantError):
        storage.active_path("not-hex!!")


async def test_write_bulk_zip_staged_uses_its_own_zone(tmp_path: Path) -> None:
    storage = PrivateBiometricStorage(_settings(tmp_path))
    key = storage.new_key()
    await storage.write_bulk_zip_staged(key, _chunks(b"PK\x03\x04fake-zip"), max_bytes=1024)
    assert storage.bulk_zip_staging_path(key).is_file()
    storage.discard_bulk_zip_staged(key)
    assert storage.bulk_zip_staging_path(key).is_file() is False
