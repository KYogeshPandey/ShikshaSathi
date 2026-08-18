"""Pre-extraction security validation for bulk ZIP biometric enrollment.

Every function here operates on **archive metadata** (``zipfile.ZipInfo``)
and a bounded manifest read — never on ``ZipFile.extractall()`` or
``ZipFile.extract()`` (neither is used anywhere in this application; see
``stream_member_to_path`` below for the one safe, bounded way any member's
bytes are ever read). ``validate_archive`` is a pure pre-flight check: it
opens the archive read-only, inspects metadata, and parses the manifest
CSV — it never writes a file anywhere and never touches the database.

Manifest format (documented here as the single source of truth — also
repeated in docs/HANDOVER_PHASE_5_STAGE_2.md and
backend_v2/README.md): a root-level file named exactly ``manifest.csv``
(case-sensitive, no directory prefix), UTF-8, with a header row
containing at least the columns ``student_profile_id`` and ``filename``.
Each data row maps one archive member (referenced by its exact,
case-sensitive path inside the archive) to the student it should be
enrolled against. Every non-manifest member in the archive must be
referenced by exactly one manifest row, and every manifest row must
reference exactly one present, valid member — an archive with an
unreferenced file, or a manifest row pointing at a missing file, is
rejected in full (see ``BulkEnrollmentValidationError``).
"""

from __future__ import annotations

import csv
import io
import re
import stat
import uuid
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings
from app.modules.biometric_enrollment.errors import (
    BulkEnrollmentValidationError,
    BulkEnrollmentZipInvalidError,
)

MANIFEST_FILENAME = "manifest.csv"
_MANIFEST_MAX_BYTES = 2 * 1024 * 1024
_REQUIRED_MANIFEST_COLUMNS = {"student_profile_id", "filename"}
_ALLOWED_MEMBER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
_NESTED_ARCHIVE_EXTENSIONS = {
    ".zip",
    ".tar",
    ".gz",
    ".tgz",
    ".bz2",
    ".xz",
    ".rar",
    ".7z",
    ".tar.gz",
}
_DRIVE_LETTER_PATTERN = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True)
class ManifestRow:
    row_number: int
    student_profile_id: uuid.UUID
    filename: str
    zip_info: zipfile.ZipInfo


def _error(errors: list[dict[str, object]], *, code: str, message: str, **extra: object) -> None:
    errors.append({"code": code, "message": message, **extra})


def _is_symlink_entry(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return stat.S_ISLNK(mode) if mode else False


def _is_directory_entry(info: zipfile.ZipInfo) -> bool:
    return info.is_dir() or info.filename.endswith("/")


def _validate_member_path(name: str) -> str | None:
    """Return an error code if ``name`` is unsafe, else ``None``.

    Every check here runs on the **raw** archive-supplied name — nothing
    is normalized/rewritten before this runs, so a rejected name is never
    silently "fixed" and used anyway.
    """
    if not name or name in {".", "./"}:
        return "ZIP_MEMBER_INVALID_PATH"
    if "\x00" in name:
        return "ZIP_MEMBER_INVALID_PATH"
    if "\\" in name:
        return "ZIP_MEMBER_BACKSLASH_PATH"
    if name.startswith("/"):
        return "ZIP_MEMBER_ABSOLUTE_PATH"
    if _DRIVE_LETTER_PATTERN.match(name):
        return "ZIP_MEMBER_DRIVE_PATH"
    segments = name.split("/")
    if any(segment in ("..", "") for segment in segments):
        return "ZIP_MEMBER_PATH_TRAVERSAL"
    if any(segment == "." for segment in segments):
        return "ZIP_MEMBER_INVALID_PATH"
    return None


def _compression_ratio(info: zipfile.ZipInfo) -> float:
    if info.file_size <= 0:
        return 0.0
    if info.compress_size <= 0:
        return float("inf")
    return info.file_size / info.compress_size


def validate_archive(zip_path: Path, *, settings: Settings) -> list[ManifestRow]:
    """Fully validate an archive before any member is ever extracted.

    Returns the ordered, validated manifest rows on success. Raises
    ``BulkEnrollmentValidationError`` (carrying every discovered problem,
    not just the first) on any failure — the caller must not extract or
    persist anything for a rejected archive. Raises
    ``BulkEnrollmentZipInvalidError`` directly (not via the row-error
    list) if the file is not a readable ZIP at all.
    """
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise BulkEnrollmentZipInvalidError(str(type(exc).__name__)) from exc

    errors: list[dict[str, object]] = []
    try:
        infolist = zf.infolist()
        if not infolist:
            raise BulkEnrollmentZipInvalidError("empty_archive")

        manifest_info: zipfile.ZipInfo | None = None
        valid_members: dict[str, zipfile.ZipInfo] = {}
        seen_names: set[str] = set()
        candidate_file_count = 0
        total_uncompressed = 0

        for info in infolist:
            name = info.filename
            if _is_directory_entry(info):
                continue

            path_error = _validate_member_path(name)
            if path_error is not None:
                _error(errors, code=path_error, message=f"Unsafe path in archive: {name!r}")
                continue  # never inspect a rejected path further

            if name in seen_names:
                _error(
                    errors,
                    code="ZIP_MEMBER_DUPLICATE_PATH",
                    message=f"Duplicate archive path: {name!r}",
                )
                continue
            seen_names.add(name)

            if info.flag_bits & 0x1:
                _error(
                    errors,
                    code="ZIP_MEMBER_ENCRYPTED",
                    message=f"Encrypted archive member not allowed: {name!r}",
                )
                continue
            if _is_symlink_entry(info):
                _error(
                    errors,
                    code="ZIP_MEMBER_SYMLINK",
                    message=f"Symlink archive member not allowed: {name!r}",
                )
                continue

            total_uncompressed += max(info.file_size, 0)
            ratio = _compression_ratio(info)
            if ratio > settings.MAX_BULK_ENROLLMENT_COMPRESSION_RATIO:
                _error(
                    errors,
                    code="ZIP_MEMBER_SUSPICIOUS_COMPRESSION_RATIO",
                    message=f"Suspicious compression ratio for {name!r}.",
                )
                continue

            is_manifest = name == MANIFEST_FILENAME
            if is_manifest:
                if info.file_size > _MANIFEST_MAX_BYTES:
                    _error(
                        errors,
                        code="ZIP_MANIFEST_TOO_LARGE",
                        message="manifest.csv exceeds the maximum allowed size.",
                    )
                    continue
                manifest_info = info
                continue

            candidate_file_count += 1
            lowered = name.lower()
            if any(lowered.endswith(ext) for ext in _NESTED_ARCHIVE_EXTENSIONS):
                _error(
                    errors,
                    code="ZIP_MEMBER_NESTED_ARCHIVE",
                    message=f"Nested archive member not allowed: {name!r}",
                )
                continue
            if not any(lowered.endswith(ext) for ext in _ALLOWED_MEMBER_EXTENSIONS):
                _error(
                    errors,
                    code="ZIP_MEMBER_UNSUPPORTED_EXTENSION",
                    message=f"Unsupported file extension: {name!r}",
                )
                continue
            if info.file_size <= 0:
                _error(
                    errors, code="ZIP_MEMBER_EMPTY", message=f"Archive member is empty: {name!r}"
                )
                continue
            if info.file_size > settings.MAX_ENROLLMENT_IMAGE_BYTES:
                _error(
                    errors,
                    code="ZIP_MEMBER_TOO_LARGE",
                    message=f"Archive member exceeds the per-file byte limit: {name!r}",
                )
                continue

            valid_members[name] = info

        if candidate_file_count > settings.MAX_BULK_ENROLLMENT_FILES:
            _error(
                errors,
                code="ZIP_TOO_MANY_FILES",
                message=(
                    f"Archive contains {candidate_file_count} files, exceeding the "
                    f"{settings.MAX_BULK_ENROLLMENT_FILES}-file limit."
                ),
            )
        if total_uncompressed > settings.MAX_BULK_ENROLLMENT_TOTAL_UNCOMPRESSED_BYTES:
            _error(
                errors,
                code="ZIP_TOTAL_UNCOMPRESSED_TOO_LARGE",
                message="Archive's total uncompressed size exceeds the configured limit.",
            )

        if manifest_info is None:
            _error(
                errors,
                code="ZIP_MANIFEST_MISSING",
                message=f"Archive must contain a root-level {MANIFEST_FILENAME!r} file.",
            )
            raise BulkEnrollmentValidationError(errors)

        rows = _parse_manifest(zf, manifest_info, valid_members=valid_members, errors=errors)

        referenced_names = {row.filename for row in rows}
        for name in valid_members:
            if name not in referenced_names:
                _error(
                    errors,
                    code="ZIP_MEMBER_UNREFERENCED",
                    message=f"Archive member not referenced by any manifest row: {name!r}",
                )

        if errors:
            raise BulkEnrollmentValidationError(errors)

        return sorted(rows, key=lambda row: row.row_number)
    finally:
        zf.close()


def _parse_manifest(
    zf: zipfile.ZipFile,
    manifest_info: zipfile.ZipInfo,
    *,
    valid_members: dict[str, zipfile.ZipInfo],
    errors: list[dict[str, object]],
) -> list[ManifestRow]:
    raw = _read_bounded(zf, manifest_info, max_bytes=_MANIFEST_MAX_BYTES)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        _error(errors, code="ZIP_MANIFEST_INVALID", message="manifest.csv must be UTF-8 encoded.")
        return []

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        _error(errors, code="ZIP_MANIFEST_INVALID", message="manifest.csv has no header row.")
        return []

    headers = {(name or "").strip().lower() for name in reader.fieldnames}
    if not _REQUIRED_MANIFEST_COLUMNS.issubset(headers):
        _error(
            errors,
            code="ZIP_MANIFEST_INVALID",
            message=(
                f"manifest.csv must have columns {sorted(_REQUIRED_MANIFEST_COLUMNS)}; "
                f"found {sorted(headers)}."
            ),
        )
        return []

    rows: list[ManifestRow] = []
    seen_students: set[str] = set()
    seen_filenames: set[str] = set()

    for row_number, raw_row in enumerate(reader, start=2):
        normalized_row = {(key or "").strip().lower(): value for key, value in raw_row.items()}
        student_raw = (normalized_row.get("student_profile_id") or "").strip()
        filename_raw = (normalized_row.get("filename") or "").strip()

        if not student_raw or not filename_raw:
            _error(
                errors,
                code="ZIP_MANIFEST_ROW_INCOMPLETE",
                message=f"Manifest row {row_number} is missing a required value.",
                row_number=row_number,
            )
            continue

        try:
            student_profile_id = uuid.UUID(student_raw)
        except ValueError:
            _error(
                errors,
                code="ZIP_MANIFEST_ROW_INVALID_STUDENT_ID",
                message=f"Manifest row {row_number} has an invalid student_profile_id.",
                row_number=row_number,
            )
            continue

        # Dedupe on the *canonical* string form of the parsed UUID, not
        # the raw manifest text — "550e8400-...", its uppercase form, and
        # a braced "{...}" variant all parse to the same UUID value and
        # must be caught as the same student, not three distinct ones.
        canonical_student_id = str(student_profile_id)
        if canonical_student_id in seen_students:
            _error(
                errors,
                code="ZIP_MANIFEST_DUPLICATE_STUDENT",
                message=f"Manifest row {row_number} duplicates an earlier student_profile_id.",
                row_number=row_number,
            )
            continue
        if filename_raw in seen_filenames:
            _error(
                errors,
                code="ZIP_MANIFEST_DUPLICATE_FILENAME",
                message=f"Manifest row {row_number} duplicates an earlier filename.",
                row_number=row_number,
            )
            continue

        zip_info = valid_members.get(filename_raw)
        if zip_info is None:
            _error(
                errors,
                code="ZIP_MANIFEST_ROW_MISSING_FILE",
                message=(
                    f"Manifest row {row_number} references {filename_raw!r}, which is not a "
                    "valid archive member."
                ),
                row_number=row_number,
            )
            continue

        seen_students.add(canonical_student_id)
        seen_filenames.add(filename_raw)
        rows.append(
            ManifestRow(
                row_number=row_number,
                student_profile_id=student_profile_id,
                filename=filename_raw,
                zip_info=zip_info,
            )
        )

    return rows


def _read_bounded(zf: zipfile.ZipFile, info: zipfile.ZipInfo, *, max_bytes: int) -> bytes:
    """Read one member's bytes, enforcing ``max_bytes`` while decompressing.

    Deliberately does **not** trust ``info.file_size`` alone (a zip's
    local/central-directory size fields can misreport the true
    decompressed size) — the cap is enforced against bytes actually
    produced by the decompressor, chunk by chunk.
    """
    chunks: list[bytes] = []
    read_total = 0
    with zf.open(info) as member:
        for chunk in iter(lambda: member.read(1024 * 1024), b""):
            read_total += len(chunk)
            if read_total > max_bytes:
                raise BulkEnrollmentValidationError(
                    [
                        {
                            "code": "ZIP_MEMBER_DECOMPRESSED_SIZE_EXCEEDED",
                            "message": f"{info.filename!r} decompressed beyond the allowed cap.",
                        }
                    ]
                )
            chunks.append(chunk)
    return b"".join(chunks)


def stream_member_to_path(
    zf: zipfile.ZipFile, info: zipfile.ZipInfo, dest_path: Path, *, max_bytes: int
) -> int:
    """Safely write one archive member's bytes to ``dest_path``.

    The only way any archive member's content is ever read in this
    application — never ``ZipFile.extract()``/``extractall()``. Enforces
    ``max_bytes`` against actual decompressed bytes produced (not the
    archive's own metadata), matching ``_read_bounded`` above. On any
    failure (cap exceeded or I/O error), the partially written file is
    removed before re-raising.
    """
    written = 0
    try:
        with zf.open(info) as member, dest_path.open("wb") as out:
            for chunk in iter(lambda: member.read(1024 * 1024), b""):
                written += len(chunk)
                if written > max_bytes:
                    raise BulkEnrollmentValidationError(
                        [
                            {
                                "code": "ZIP_MEMBER_DECOMPRESSED_SIZE_EXCEEDED",
                                "message": (
                                    f"{info.filename!r} decompressed beyond the allowed cap."
                                ),
                            }
                        ]
                    )
                out.write(chunk)
    except BaseException:
        dest_path.unlink(missing_ok=True)
        raise
    return written


def iter_manifest_rows(rows: list[ManifestRow]) -> Iterator[ManifestRow]:
    """Deterministic iteration order — kept as a named helper for tests/readability."""
    yield from sorted(rows, key=lambda row: row.row_number)
