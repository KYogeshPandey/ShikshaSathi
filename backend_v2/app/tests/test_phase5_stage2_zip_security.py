"""Unit tests for ``app.modules.biometric_enrollment.zip_security``.

Pure ``zipfile`` + stdlib content, no database. Every test builds a real
ZIP archive on disk (``tmp_path``) — including, deliberately, archives
containing unsafe entries (path traversal, symlinks, encryption) — and
asserts ``validate_archive`` rejects them *before* anything is ever
extracted. This module never calls ``ZipFile.extract()``/``extractall()``
anywhere, including in these tests.
"""

from __future__ import annotations

import io
import stat
import zipfile
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from app.core.config import Settings
from app.modules.biometric_enrollment.errors import (
    BulkEnrollmentValidationError,
    BulkEnrollmentZipInvalidError,
)
from app.modules.biometric_enrollment.zip_security import (
    MANIFEST_FILENAME,
    stream_member_to_path,
    validate_archive,
)

_VALID_SECRET = "a" * 40
_STUDENT_A = "11111111-1111-1111-1111-111111111111"
_STUDENT_B = "22222222-2222-2222-2222-222222222222"


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


def _jpeg_bytes(size: tuple[int, int] = (80, 80)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color=(5, 6, 7)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _build_zip(path: Path, entries: list[tuple[zipfile.ZipInfo | str, bytes]]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for entry, content in entries:
            zf.writestr(entry, content)
    return path


def _mark_entry_encrypted(zip_path: Path, filename: str) -> None:
    """Set the general-purpose "encrypted" bit (bit 0) for one entry.

    ``zipfile.ZipFile.writestr`` does not preserve a manually-set
    ``ZipInfo.flag_bits`` (it recomputes the flags field itself), so this
    patches the already-written archive's raw local-file-header and
    central-directory bytes directly — the only way to produce an entry
    that genuinely round-trips as "encrypted" via ``zipfile.ZipInfo``,
    exactly what ``zip_security._validate_archive`` inspects.
    """
    import struct

    data = bytearray(zip_path.read_bytes())
    name_bytes = filename.encode()

    offset = 0
    while True:
        idx = data.find(b"PK\x03\x04", offset)
        if idx == -1:
            break
        name_len = struct.unpack_from("<H", data, idx + 26)[0]
        name_start = idx + 30
        if bytes(data[name_start : name_start + name_len]) == name_bytes:
            flags_offset = idx + 6
            flags = struct.unpack_from("<H", data, flags_offset)[0] | 0x1
            struct.pack_into("<H", data, flags_offset, flags)
        offset = idx + 4

    offset = 0
    while True:
        idx = data.find(b"PK\x01\x02", offset)
        if idx == -1:
            break
        name_len = struct.unpack_from("<H", data, idx + 28)[0]
        name_start = idx + 46
        if bytes(data[name_start : name_start + name_len]) == name_bytes:
            flags_offset = idx + 8
            flags = struct.unpack_from("<H", data, flags_offset)[0] | 0x1
            struct.pack_into("<H", data, flags_offset, flags)
        offset = idx + 4

    zip_path.write_bytes(bytes(data))


def _manifest(rows: list[tuple[str, str]], *, header: str = "student_profile_id,filename") -> bytes:
    lines = [header] + [f"{student_id},{filename}" for student_id, filename in rows]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _error_codes(exc_info: pytest.ExceptionInfo[BulkEnrollmentValidationError]) -> set[str]:
    errors = exc_info.value.details.get("errors", [])
    return {str(item["code"]) for item in errors}


def test_valid_archive_returns_ordered_manifest_rows(tmp_path: Path) -> None:
    zip_path = _build_zip(
        tmp_path / "valid.zip",
        [
            (MANIFEST_FILENAME, _manifest([(_STUDENT_A, "a.jpg"), (_STUDENT_B, "b.jpg")])),
            ("a.jpg", _jpeg_bytes()),
            ("b.jpg", _jpeg_bytes()),
        ],
    )
    rows = validate_archive(zip_path, settings=_settings())
    assert [row.filename for row in rows] == ["a.jpg", "b.jpg"]
    assert rows[0].row_number == 2
    assert rows[1].row_number == 3
    assert str(rows[0].student_profile_id) == _STUDENT_A


def test_path_traversal_dotdot_is_rejected_before_extraction(tmp_path: Path) -> None:
    """The required regression test: ``../../evil.jpg`` must never be extracted."""
    zip_path = _build_zip(
        tmp_path / "traversal.zip",
        [
            (MANIFEST_FILENAME, _manifest([(_STUDENT_A, "../../evil.jpg")])),
            (zipfile.ZipInfo("../../evil.jpg"), _jpeg_bytes()),
        ],
    )
    with pytest.raises(BulkEnrollmentValidationError) as exc_info:
        validate_archive(zip_path, settings=_settings())
    assert "ZIP_MEMBER_PATH_TRAVERSAL" in _error_codes(exc_info)
    # Nothing on disk beyond the archive itself should ever be created by validation.
    assert list(tmp_path.iterdir()) == [zip_path]


def test_backslash_traversal_is_rejected(tmp_path: Path) -> None:
    zip_path = _build_zip(
        tmp_path / "backslash.zip",
        [
            (MANIFEST_FILENAME, _manifest([(_STUDENT_A, "..\\evil.jpg")])),
            (zipfile.ZipInfo("..\\evil.jpg"), _jpeg_bytes()),
        ],
    )
    with pytest.raises(BulkEnrollmentValidationError) as exc_info:
        validate_archive(zip_path, settings=_settings())
    assert "ZIP_MEMBER_BACKSLASH_PATH" in _error_codes(exc_info)


def test_absolute_path_is_rejected(tmp_path: Path) -> None:
    zip_path = _build_zip(
        tmp_path / "absolute.zip",
        [
            (MANIFEST_FILENAME, _manifest([(_STUDENT_A, "/etc/evil.jpg")])),
            (zipfile.ZipInfo("/etc/evil.jpg"), _jpeg_bytes()),
        ],
    )
    with pytest.raises(BulkEnrollmentValidationError) as exc_info:
        validate_archive(zip_path, settings=_settings())
    assert "ZIP_MEMBER_ABSOLUTE_PATH" in _error_codes(exc_info)


def test_drive_letter_path_is_rejected(tmp_path: Path) -> None:
    zip_path = _build_zip(
        tmp_path / "drive.zip",
        [
            (MANIFEST_FILENAME, _manifest([(_STUDENT_A, "C:/evil.jpg")])),
            (zipfile.ZipInfo("C:/evil.jpg"), _jpeg_bytes()),
        ],
    )
    with pytest.raises(BulkEnrollmentValidationError) as exc_info:
        validate_archive(zip_path, settings=_settings())
    assert "ZIP_MEMBER_DRIVE_PATH" in _error_codes(exc_info)


def test_symlink_entry_is_rejected(tmp_path: Path) -> None:
    symlink_info = zipfile.ZipInfo("link.jpg")
    symlink_info.external_attr = (stat.S_IFLNK | 0o777) << 16
    zip_path = _build_zip(
        tmp_path / "symlink.zip",
        [
            (MANIFEST_FILENAME, _manifest([(_STUDENT_A, "link.jpg")])),
            (symlink_info, b"/etc/passwd"),
        ],
    )
    with pytest.raises(BulkEnrollmentValidationError) as exc_info:
        validate_archive(zip_path, settings=_settings())
    assert "ZIP_MEMBER_SYMLINK" in _error_codes(exc_info)


def test_encrypted_member_is_rejected(tmp_path: Path) -> None:
    zip_path = _build_zip(
        tmp_path / "encrypted.zip",
        [
            (MANIFEST_FILENAME, _manifest([(_STUDENT_A, "secret.jpg")])),
            ("secret.jpg", _jpeg_bytes()),
        ],
    )
    _mark_entry_encrypted(zip_path, "secret.jpg")
    with pytest.raises(BulkEnrollmentValidationError) as exc_info:
        validate_archive(zip_path, settings=_settings())
    assert "ZIP_MEMBER_ENCRYPTED" in _error_codes(exc_info)


def test_nested_archive_member_is_rejected(tmp_path: Path) -> None:
    zip_path = _build_zip(
        tmp_path / "nested.zip",
        [
            (MANIFEST_FILENAME, _manifest([(_STUDENT_A, "photos.zip")])),
            ("photos.zip", b"PK\x03\x04fake-nested-zip-bytes"),
        ],
    )
    with pytest.raises(BulkEnrollmentValidationError) as exc_info:
        validate_archive(zip_path, settings=_settings())
    assert "ZIP_MEMBER_NESTED_ARCHIVE" in _error_codes(exc_info)


def test_unsupported_extension_is_rejected(tmp_path: Path) -> None:
    zip_path = _build_zip(
        tmp_path / "unsupported.zip",
        [
            (MANIFEST_FILENAME, _manifest([(_STUDENT_A, "notes.txt")])),
            ("notes.txt", b"just some text"),
        ],
    )
    with pytest.raises(BulkEnrollmentValidationError) as exc_info:
        validate_archive(zip_path, settings=_settings())
    assert "ZIP_MEMBER_UNSUPPORTED_EXTENSION" in _error_codes(exc_info)


def test_duplicate_normalized_path_is_rejected(tmp_path: Path) -> None:
    zip_path = _build_zip(
        tmp_path / "dup_path.zip",
        [
            (MANIFEST_FILENAME, _manifest([(_STUDENT_A, "a.jpg")])),
            ("a.jpg", _jpeg_bytes()),
            ("a.jpg", _jpeg_bytes(size=(10, 10))),
        ],
    )
    with pytest.raises(BulkEnrollmentValidationError) as exc_info:
        validate_archive(zip_path, settings=_settings())
    assert "ZIP_MEMBER_DUPLICATE_PATH" in _error_codes(exc_info)


def test_excessive_file_count_is_rejected(tmp_path: Path) -> None:
    entries: list[tuple[zipfile.ZipInfo | str, bytes]] = [
        (MANIFEST_FILENAME, _manifest([(_STUDENT_A, "a.jpg"), (_STUDENT_B, "b.jpg")])),
        ("a.jpg", _jpeg_bytes()),
        ("b.jpg", _jpeg_bytes()),
    ]
    zip_path = _build_zip(tmp_path / "too_many.zip", entries)
    with pytest.raises(BulkEnrollmentValidationError) as exc_info:
        validate_archive(zip_path, settings=_settings(MAX_BULK_ENROLLMENT_FILES=1))
    assert "ZIP_TOO_MANY_FILES" in _error_codes(exc_info)


def test_excessive_total_uncompressed_size_is_rejected(tmp_path: Path) -> None:
    zip_path = _build_zip(
        tmp_path / "too_big_total.zip",
        [
            (MANIFEST_FILENAME, _manifest([(_STUDENT_A, "a.jpg")])),
            ("a.jpg", _jpeg_bytes(size=(300, 300))),
        ],
    )
    with pytest.raises(BulkEnrollmentValidationError) as exc_info:
        validate_archive(
            zip_path, settings=_settings(MAX_BULK_ENROLLMENT_TOTAL_UNCOMPRESSED_BYTES=1024)
        )
    assert "ZIP_TOTAL_UNCOMPRESSED_TOO_LARGE" in _error_codes(exc_info)


def test_missing_manifest_is_rejected(tmp_path: Path) -> None:
    zip_path = _build_zip(tmp_path / "no_manifest.zip", [("a.jpg", _jpeg_bytes())])
    with pytest.raises(BulkEnrollmentValidationError) as exc_info:
        validate_archive(zip_path, settings=_settings())
    assert "ZIP_MANIFEST_MISSING" in _error_codes(exc_info)


def test_manifest_missing_required_column_is_rejected(tmp_path: Path) -> None:
    zip_path = _build_zip(
        tmp_path / "bad_header.zip",
        [
            (MANIFEST_FILENAME, b"student_profile_id\n" + _STUDENT_A.encode() + b"\n"),
            ("a.jpg", _jpeg_bytes()),
        ],
    )
    with pytest.raises(BulkEnrollmentValidationError) as exc_info:
        validate_archive(zip_path, settings=_settings())
    assert "ZIP_MANIFEST_INVALID" in _error_codes(exc_info)


def test_manifest_row_referencing_missing_file_is_rejected(tmp_path: Path) -> None:
    zip_path = _build_zip(
        tmp_path / "missing_file.zip",
        [(MANIFEST_FILENAME, _manifest([(_STUDENT_A, "does-not-exist.jpg")]))],
    )
    with pytest.raises(BulkEnrollmentValidationError) as exc_info:
        validate_archive(zip_path, settings=_settings())
    assert "ZIP_MANIFEST_ROW_MISSING_FILE" in _error_codes(exc_info)


def test_unreferenced_archive_member_is_rejected(tmp_path: Path) -> None:
    zip_path = _build_zip(
        tmp_path / "unreferenced.zip",
        [
            (MANIFEST_FILENAME, _manifest([(_STUDENT_A, "a.jpg")])),
            ("a.jpg", _jpeg_bytes()),
            ("b.jpg", _jpeg_bytes()),  # never referenced by any manifest row
        ],
    )
    with pytest.raises(BulkEnrollmentValidationError) as exc_info:
        validate_archive(zip_path, settings=_settings())
    assert "ZIP_MEMBER_UNREFERENCED" in _error_codes(exc_info)


def test_duplicate_student_row_is_rejected(tmp_path: Path) -> None:
    zip_path = _build_zip(
        tmp_path / "dup_student.zip",
        [
            (MANIFEST_FILENAME, _manifest([(_STUDENT_A, "a.jpg"), (_STUDENT_A, "b.jpg")])),
            ("a.jpg", _jpeg_bytes()),
            ("b.jpg", _jpeg_bytes()),
        ],
    )
    with pytest.raises(BulkEnrollmentValidationError) as exc_info:
        validate_archive(zip_path, settings=_settings())
    assert "ZIP_MANIFEST_DUPLICATE_STUDENT" in _error_codes(exc_info)


def test_duplicate_student_row_different_uuid_representation_is_rejected(tmp_path: Path) -> None:
    """Same student, spelled differently — canonical lowercase vs. uppercase+braced.

    Manifest-level duplicate-student detection must key off the parsed
    UUID *value* (or its canonical ``str()`` form), not the original raw
    manifest text — ``uuid.UUID`` treats
    ``11111111-1111-1111-1111-111111111111`` and
    ``{11111111-1111-1111-1111-111111111111}`` (also uppercased) as the
    exact same value, and this must still be caught as a duplicate.
    """
    braced_uppercase_variant = "{" + _STUDENT_A.upper() + "}"
    zip_path = _build_zip(
        tmp_path / "dup_student_representation.zip",
        [
            (
                MANIFEST_FILENAME,
                _manifest([(_STUDENT_A, "a.jpg"), (braced_uppercase_variant, "b.jpg")]),
            ),
            ("a.jpg", _jpeg_bytes()),
            ("b.jpg", _jpeg_bytes()),
        ],
    )
    with pytest.raises(BulkEnrollmentValidationError) as exc_info:
        validate_archive(zip_path, settings=_settings())
    assert "ZIP_MANIFEST_DUPLICATE_STUDENT" in _error_codes(exc_info)


def test_duplicate_filename_row_is_rejected(tmp_path: Path) -> None:
    zip_path = _build_zip(
        tmp_path / "dup_filename.zip",
        [
            (MANIFEST_FILENAME, _manifest([(_STUDENT_A, "a.jpg"), (_STUDENT_B, "a.jpg")])),
            ("a.jpg", _jpeg_bytes()),
        ],
    )
    with pytest.raises(BulkEnrollmentValidationError) as exc_info:
        validate_archive(zip_path, settings=_settings())
    assert "ZIP_MANIFEST_DUPLICATE_FILENAME" in _error_codes(exc_info)


def test_invalid_student_id_format_is_rejected(tmp_path: Path) -> None:
    zip_path = _build_zip(
        tmp_path / "bad_student_id.zip",
        [
            (MANIFEST_FILENAME, _manifest([("not-a-uuid", "a.jpg")])),
            ("a.jpg", _jpeg_bytes()),
        ],
    )
    with pytest.raises(BulkEnrollmentValidationError) as exc_info:
        validate_archive(zip_path, settings=_settings())
    assert "ZIP_MANIFEST_ROW_INVALID_STUDENT_ID" in _error_codes(exc_info)


def test_not_a_zip_file_raises_invalid_error_directly(tmp_path: Path) -> None:
    path = tmp_path / "not_a_zip.zip"
    path.write_bytes(b"this is not a zip archive at all")
    with pytest.raises(BulkEnrollmentZipInvalidError):
        validate_archive(path, settings=_settings())


def test_multiple_problems_are_all_reported_together(tmp_path: Path) -> None:
    """Atomicity contract: every problem is collected, not just the first."""
    zip_path = _build_zip(
        tmp_path / "multi_problem.zip",
        [
            (
                MANIFEST_FILENAME,
                _manifest([(_STUDENT_A, "../../evil.jpg"), (_STUDENT_B, "notes.txt")]),
            ),
            (zipfile.ZipInfo("../../evil.jpg"), _jpeg_bytes()),
            ("notes.txt", b"not an image"),
        ],
    )
    with pytest.raises(BulkEnrollmentValidationError) as exc_info:
        validate_archive(zip_path, settings=_settings())
    codes = _error_codes(exc_info)
    assert "ZIP_MEMBER_PATH_TRAVERSAL" in codes
    assert "ZIP_MEMBER_UNSUPPORTED_EXTENSION" in codes


def test_stream_member_to_path_writes_expected_bytes(tmp_path: Path) -> None:
    zip_path = _build_zip(tmp_path / "source.zip", [("a.jpg", _jpeg_bytes())])
    dest = tmp_path / "extracted.jpg"
    with zipfile.ZipFile(zip_path) as zf:
        written = stream_member_to_path(zf, zf.getinfo("a.jpg"), dest, max_bytes=10_000_000)
    assert dest.is_file()
    assert written == dest.stat().st_size


def test_stream_member_to_path_enforces_cap_and_cleans_up(tmp_path: Path) -> None:
    payload = _jpeg_bytes(size=(300, 300))
    zip_path = _build_zip(tmp_path / "source2.zip", [("a.jpg", payload)])
    dest = tmp_path / "extracted2.jpg"
    with (
        zipfile.ZipFile(zip_path) as zf,
        pytest.raises(BulkEnrollmentValidationError),
    ):
        stream_member_to_path(zf, zf.getinfo("a.jpg"), dest, max_bytes=len(payload) // 2)
    assert dest.is_file() is False
