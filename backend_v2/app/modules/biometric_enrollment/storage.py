"""Private, server-controlled biometric file storage.

Everything in this module is deliberately narrow: create a staging file,
write bytes to it under a byte cap, generate an opaque final key,
atomically promote a staged file, move a file to quarantine, purge it,
check existence, and list keys per zone (for reconciliation). No route,
service, or repository anywhere in this application builds a filesystem
path from a client-supplied value directly — every path here is built
from ``settings.BIOMETRIC_STORAGE_ROOT`` (validated at startup, see
app/core/config.py) plus a *server-generated* opaque key.

Directory layout under ``BIOMETRIC_STORAGE_ROOT``::

    staging/<key>.tmp      transient — not yet validated/committed
    active/<key>.bin       the current, promoted sample for a student
    quarantine/<key>.bin   marked for deletion; retryable purge target

A ``key`` is always ``uuid.uuid4().hex`` (32 lowercase hex characters),
generated in this module — never accepted as a parameter from a router
or derived from a client filename. ``_validate_key`` defends that
invariant even against a hypothetical future internal caller bug (it is
not a defense against an external attacker, since no external input ever
reaches these methods as a ``key``).

Atomicity note (see docs/BIOMETRIC_DATA_POLICY.md and
docs/HANDOVER_PHASE_5_STAGE_2.md): ``os.replace`` is atomic *within the
same filesystem*, which is why staging/active/quarantine are all
subdirectories of one ``BIOMETRIC_STORAGE_ROOT`` rather than separate
mounts. This module does not and cannot make a filesystem rename atomic
*with* a database commit — that compensating-cleanup responsibility
belongs to the service layer (app/modules/biometric_enrollment/service.py),
which this module's docstring and every method below calls out
explicitly wherever it matters.
"""

from __future__ import annotations

import os
import re
import stat
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import structlog

from app.core.config import Settings

logger = structlog.get_logger(__name__)

STAGING_ZONE = "staging"
ACTIVE_ZONE = "active"
QUARANTINE_ZONE = "quarantine"
BULK_STAGING_ZONE = "bulk_staging"

_KEY_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_STAGING_SUFFIX = ".tmp"
_STORED_SUFFIX = ".bin"
_BULK_ZIP_SUFFIX = ".zip"


class BiometricStorageInvariantError(RuntimeError):
    """Raised only on a violated internal invariant (never client-triggered).

    E.g. a ``key`` that does not match the server-generated format, or a
    resolved path that escapes the storage root. Every call site that can
    reach this has a comment explaining why it is unreachable from any
    external input.
    """


def _validate_key(key: str) -> None:
    if not _KEY_PATTERN.match(key):
        raise BiometricStorageInvariantError(f"invalid internal storage key format: {key!r}")


@dataclass(frozen=True)
class StagedFile:
    key: str
    size_bytes: int


@dataclass(frozen=True)
class DriftReport:
    """One reconciliation finding — see ``PrivateBiometricStorage.list_keys``.

    Never includes an absolute path or any biometric content — only the
    opaque key and the zone(s) involved.
    """

    key: str
    finding: str


class StorageCapExceededError(Exception):
    """Internal-only signal used to unwind ``write_staged``'s loop.

    Deliberately not an ``AppError`` — this module has no FastAPI/HTTP
    awareness. The service layer catches this exact type and raises the
    public ``EnrollmentImageTooLargeError``/``BulkEnrollmentZipTooLargeError``.
    """

    def __init__(self, written: int) -> None:
        super().__init__(f"staged write exceeded cap at {written} bytes")
        self.written = written


class PrivateBiometricStorage:
    """Filesystem-backed private storage for biometric sample files."""

    def __init__(self, settings: Settings) -> None:
        root = Path(settings.BIOMETRIC_STORAGE_ROOT).resolve()
        self._root = root
        for zone in (STAGING_ZONE, ACTIVE_ZONE, QUARANTINE_ZONE, BULK_STAGING_ZONE):
            zone_dir = root / zone
            zone_dir.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(zone_dir, 0o700)
            except OSError:  # pragma: no cover - platform-dependent, best-effort
                logger.warning("biometric_storage_chmod_failed", zone=zone)

    # --- path resolution (never accepts a client-supplied path) --------

    def _zone_dir(self, zone: str) -> Path:
        return self._root / zone

    def _resolve_in_zone(self, zone: str, key: str, suffix: str) -> Path:
        _validate_key(key)
        candidate = (self._zone_dir(zone) / f"{key}{suffix}").resolve()
        # Defense in depth: `key` is always our own uuid4().hex (validated
        # above), so this can only fire on an internal invariant break,
        # never on external input.
        if self._root not in candidate.parents:
            raise BiometricStorageInvariantError(
                f"resolved biometric storage path escaped the storage root: zone={zone}"
            )
        return candidate

    def staging_path(self, key: str) -> Path:
        return self._resolve_in_zone(STAGING_ZONE, key, _STAGING_SUFFIX)

    def active_path(self, key: str) -> Path:
        return self._resolve_in_zone(ACTIVE_ZONE, key, _STORED_SUFFIX)

    def quarantine_path(self, key: str) -> Path:
        return self._resolve_in_zone(QUARANTINE_ZONE, key, _STORED_SUFFIX)

    def bulk_zip_staging_path(self, key: str) -> Path:
        return self._resolve_in_zone(BULK_STAGING_ZONE, key, _BULK_ZIP_SUFFIX)

    # --- key generation ---------------------------------------------------

    def new_key(self) -> str:
        return uuid.uuid4().hex

    # --- staging (streamed, byte-capped) -----------------------------------

    async def write_staged(
        self, key: str, chunks: AsyncIterator[bytes], *, max_bytes: int
    ) -> StagedFile:
        """Stream ``chunks`` to the staging path, enforcing ``max_bytes``.

        Raises ``BiometricStorageInvariantError`` never (the byte-cap
        failure is the caller's ``EnrollmentImageTooLargeError`` /
        ``BulkEnrollmentZipTooLargeError`` — this module stays
        provider/error-shape neutral and just stops writing and cleans
        up). On any exception (cap exceeded or an I/O error), the partial
        staged file is removed before re-raising, so a failed validation
        never leaves a final (or even partial) file behind.
        """
        path = self.staging_path(key)
        written = 0
        try:
            with path.open("wb") as handle:
                async for chunk in chunks:
                    written += len(chunk)
                    if written > max_bytes:
                        raise StorageCapExceededError(written)
                    handle.write(chunk)
        except BaseException:
            self.discard_staged(key)
            raise
        return StagedFile(key=key, size_bytes=written)

    def discard_staged(self, key: str) -> None:
        """Best-effort removal of a staged file. Never raises."""
        try:
            self.staging_path(key).unlink(missing_ok=True)
        except OSError:  # pragma: no cover - best-effort cleanup
            logger.warning("biometric_staged_discard_failed", key=key)

    async def write_bulk_zip_staged(
        self, key: str, chunks: AsyncIterator[bytes], *, max_bytes: int
    ) -> StagedFile:
        """Same contract as ``write_staged``, targeting the bulk-ZIP staging zone.

        A whole uploaded archive is not itself a ``BiometricSample`` (only
        the individual images later extracted from it become samples) but
        still must never touch a world-readable temp directory — this
        keeps it under the same private ``BIOMETRIC_STORAGE_ROOT``.
        """
        path = self.bulk_zip_staging_path(key)
        written = 0
        try:
            with path.open("wb") as handle:
                async for chunk in chunks:
                    written += len(chunk)
                    if written > max_bytes:
                        raise StorageCapExceededError(written)
                    handle.write(chunk)
        except BaseException:
            self.discard_bulk_zip_staged(key)
            raise
        return StagedFile(key=key, size_bytes=written)

    def discard_bulk_zip_staged(self, key: str) -> None:
        """Best-effort removal of a staged bulk-ZIP upload. Never raises."""
        try:
            self.bulk_zip_staging_path(key).unlink(missing_ok=True)
        except OSError:  # pragma: no cover - best-effort cleanup
            logger.warning("biometric_bulk_zip_staged_discard_failed", key=key)

    # --- promotion / quarantine / purge (atomic renames) -------------------

    def promote(self, key: str) -> None:
        """Atomically move a staged file to the active zone.

        Rejects (refuses to promote) a symlink staged path — biometric
        storage never follows a symlink it did not itself create, and
        this module never creates one.
        """
        staged = self.staging_path(key)
        if staged.is_symlink():  # pragma: no cover - defensive, not reachable via any API
            raise BiometricStorageInvariantError("refusing to promote a symlinked staged file")
        os.replace(staged, self.active_path(key))

    def quarantine(self, key: str) -> None:
        """Atomically move an active file to the quarantine zone."""
        active = self.active_path(key)
        if active.is_symlink():  # pragma: no cover - defensive, not reachable via any API
            raise BiometricStorageInvariantError("refusing to quarantine a symlinked active file")
        os.replace(active, self.quarantine_path(key))

    def purge_quarantined(self, key: str) -> None:
        """Permanently delete a quarantined file. Retryable: missing is not an error."""
        self.quarantine_path(key).unlink(missing_ok=True)

    def restore_from_quarantine(self, key: str) -> None:
        """Move a quarantined file back to active.

        Used only to unwind a failed deletion-finalization step (see
        app/modules/biometric_enrollment/service.py's delete flow).
        """
        os.replace(self.quarantine_path(key), self.active_path(key))

    # --- existence checks (used by the service layer and reconciliation) --

    def exists_staged(self, key: str) -> bool:
        return self.staging_path(key).is_file()

    def exists_active(self, key: str) -> bool:
        return self.active_path(key).is_file()

    def exists_quarantined(self, key: str) -> bool:
        return self.quarantine_path(key).is_file()

    # --- reconciliation support --------------------------------------------

    def _list_zone_keys(self, zone: str, suffix: str) -> set[str]:
        zone_dir = self._zone_dir(zone)
        keys: set[str] = set()
        for entry in zone_dir.iterdir():
            if entry.is_symlink() or not entry.is_file():
                continue
            name = entry.name
            if name.endswith(suffix) and _KEY_PATTERN.match(name[: -len(suffix)]):
                keys.add(name[: -len(suffix)])
        return keys

    def list_staged_keys(self) -> set[str]:
        return self._list_zone_keys(STAGING_ZONE, _STAGING_SUFFIX)

    def list_active_keys(self) -> set[str]:
        return self._list_zone_keys(ACTIVE_ZONE, _STORED_SUFFIX)

    def list_quarantined_keys(self) -> set[str]:
        return self._list_zone_keys(QUARANTINE_ZONE, _STORED_SUFFIX)


def is_symlink_member(mode: int) -> bool:
    """Shared helper: does a POSIX ``st_mode``-shaped value denote a symlink?

    Used both here conceptually and by
    app/modules/biometric_enrollment/zip_security.py (zip entries encode
    the same POSIX mode bits in their external_attr field) — kept here
    since it is a storage/filesystem-shaped concern, not a zip-format one.
    """
    return stat.S_ISLNK(mode)
