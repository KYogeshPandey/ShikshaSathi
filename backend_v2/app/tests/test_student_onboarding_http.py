"""Focused HTTP coverage for migration-free student onboarding."""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import date

from httpx import AsyncClient, Response
from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.biometric_enrollment.repository import (
    BiometricEnrollmentRepository,
    BiometricSampleRepository,
)
from app.modules.bulk_imports.schemas import BulkImportEntity
from app.modules.bulk_imports.service import BulkImportService
from app.modules.profiles.models import StudentProfile
from app.modules.profiles.repository import StudentProfileRepository
from app.modules.users.models import User, UserRole
from app.tests.phase3_http_helpers import auth_headers, create_resource, seed_user
from app.tests.phase5_stage2_http_helpers import make_jpeg_bytes, make_png_bytes
from app.tests.phase5_stage3_helpers import (
    FakeFaceDetector,
    FakeFaceEmbedder,
    make_detected_face,
    patch_providers,
)


def _xlsx_bytes(rows: list[list[object]]) -> bytes:
    workbook = Workbook(write_only=True)
    worksheet = workbook.create_sheet()
    for row in rows:
        worksheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


async def _seed_scope(
    client: AsyncClient, session: AsyncSession, *, suffix: str, rolls: list[str]
) -> tuple[User, User, dict[str, object], list[User]]:
    admin = await seed_user(
        session, email=f"onboard-admin-{suffix}@example.com", role=UserRole.ADMIN
    )
    teacher = await seed_user(
        session, email=f"onboard-teacher-{suffix}@example.com", role=UserRole.TEACHER
    )
    classroom = await create_resource(
        client,
        path="/api/v1/classrooms",
        payload={"name": f"Onboarding {suffix}", "code": f"onboarding-{suffix}"},
        user=admin,
    )
    students: list[User] = []
    for index, roll in enumerate(rolls):
        student = await seed_user(
            session,
            email=f"onboard-{suffix}-{index}@example.com",
            role=UserRole.STUDENT,
        )
        student.full_name = f"Student {roll}"
        students.append(student)
    await session.commit()
    return admin, teacher, classroom, students


def _csv(classroom_id: object, students: list[User], rolls: list[str]) -> bytes:
    rows = ["user_id,classroom_id,roll_number"]
    rows.extend(
        f"{student.id},{classroom_id},{roll}" for student, roll in zip(students, rolls, strict=True)
    )
    return ("\n".join(rows) + "\n").encode()


async def _post(
    client: AsyncClient,
    *,
    actor: User,
    classroom_id: object,
    spreadsheet: bytes,
    spreadsheet_name: str = "students.csv",
    photos: bytes | None = None,
    update_existing: bool = False,
) -> Response:
    files: dict[str, tuple[str, bytes, str]] = {
        "students_file": (spreadsheet_name, spreadsheet, "application/octet-stream")
    }
    if photos is not None:
        files["photos_zip"] = ("photos.zip", photos, "application/zip")
    return await client.post(
        "/api/v1/student-onboarding",
        data={
            "classroom_id": str(classroom_id),
            "update_existing": str(update_existing).lower(),
        },
        files=files,
        headers=auth_headers(actor),
    )


async def test_csv_and_xlsx_without_zip_import_profiles_normally(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    admin, _, classroom, students = await _seed_scope(
        client_db, db_session, suffix="files-only", rolls=["101", "102"]
    )

    csv_response = await _post(
        client_db,
        actor=admin,
        classroom_id=classroom["id"],
        spreadsheet=_csv(classroom["id"], [students[0]], ["101"]),
    )
    assert csv_response.status_code == 200, csv_response.text
    assert csv_response.json()["classroom_id"] == classroom["id"]
    assert csv_response.json()["classroom_name"] == "Onboarding files-only"
    assert csv_response.json()["students"][0]["photo_status"] == "not_provided"
    assert csv_response.json()["students"][0]["biometric_status"] == "not_requested"

    xlsx = _xlsx_bytes(
        [
            ["user_id", "roll_number"],
            [str(students[1].id), 102],
        ]
    )
    xlsx_response = await _post(
        client_db,
        actor=admin,
        classroom_id=classroom["id"],
        spreadsheet=xlsx,
        spreadsheet_name="students.xlsx",
    )
    assert xlsx_response.status_code == 200, xlsx_response.text
    assert xlsx_response.json()["profile_success_count"] == 1
    assert xlsx_response.json()["students"][0]["roll_number"] == "102"
    for student in students:
        profile = await StudentProfileRepository(db_session).get_by_user_id(student.id)
        assert profile is not None
        assert str(profile.classroom_id) == classroom["id"]


async def test_selected_classroom_is_required(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    admin, _, classroom, students = await _seed_scope(
        client_db, db_session, suffix="selected-required", rolls=["101"]
    )

    response = await client_db.post(
        "/api/v1/student-onboarding",
        files={"students_file": ("students.csv", _csv(classroom["id"], students, ["101"]))},
        headers=auth_headers(admin),
    )

    assert response.status_code == 422
    assert await StudentProfileRepository(db_session).get_by_user_id(students[0].id) is None


async def test_selected_classroom_overrides_cross_class_spreadsheet_rows(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    admin, _, classroom_a, students = await _seed_scope(
        client_db, db_session, suffix="selected-scope-a", rolls=["101", "102"]
    )
    _, _, classroom_b, _ = await _seed_scope(
        client_db, db_session, suffix="selected-scope-b", rolls=[]
    )
    _, _, classroom_c, _ = await _seed_scope(
        client_db, db_session, suffix="selected-scope-c", rolls=[]
    )
    spreadsheet = (
        "user_id,classroom_id,roll_number\n"
        f"{students[0].id},{classroom_b['id']},101\n"
        f"{students[1].id},{classroom_c['id']},102\n"
    ).encode()

    with patch_providers(FakeFaceDetector(), FakeFaceEmbedder()):
        response = await _post(
            client_db,
            actor=admin,
            classroom_id=classroom_a["id"],
            spreadsheet=spreadsheet,
            photos=_zip_bytes({"101.jpg": make_jpeg_bytes(), "102.png": make_png_bytes()}),
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["classroom_id"] == classroom_a["id"]
    assert body["profile_success_count"] == 2
    assert body["face_success_count"] == 2
    assert [row["profile_status"] for row in body["students"]] == ["created", "created"]
    assert [row["photo_filename"] for row in body["students"]] == ["101.jpg", "102.png"]
    for student in students:
        profile = await StudentProfileRepository(db_session).get_by_user_id(student.id)
        assert profile is not None
        assert str(profile.classroom_id) == classroom_a["id"]


async def test_generic_detailed_import_keeps_fixed_value_mismatch_strict(
    db_session: AsyncSession,
) -> None:
    selected_classroom_id = uuid.uuid4()
    spreadsheet_classroom_id = uuid.uuid4()
    content = (
        f"user_id,classroom_id,roll_number\n{uuid.uuid4()},{spreadsheet_classroom_id},101\n"
    ).encode()

    detailed = await BulkImportService(db_session).import_file_detailed(
        entity=BulkImportEntity.STUDENT_PROFILES,
        filename="students.csv",
        content=content,
        fixed_values={"classroom_id": selected_classroom_id},
    )

    assert detailed.result.imported_count == 0
    assert detailed.result.failed_count == 1
    assert detailed.rows[0].error is not None
    assert detailed.rows[0].error.code == "BULK_IMPORT_FIXED_VALUE_MISMATCH"


async def test_matching_zip_enrolls_multiple_extensions_and_reports_missing_and_extra(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    rolls = ["101", "102", "103", "104"]
    admin, _, classroom, students = await _seed_scope(
        client_db, db_session, suffix="matching", rolls=rolls
    )
    archive = _zip_bytes(
        {
            "101.JPG": make_jpeg_bytes(color=(10, 11, 12)),
            "102.PNG": make_png_bytes(color=(20, 21, 22)),
            "103.jpeg": make_jpeg_bytes(color=(30, 31, 32)),
            "999.webp": make_png_bytes(color=(40, 41, 42)),
        }
    )

    with patch_providers(FakeFaceDetector(), FakeFaceEmbedder()):
        response = await _post(
            client_db,
            actor=admin,
            classroom_id=classroom["id"],
            spreadsheet=_csv(classroom["id"], students, rolls),
            photos=archive,
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["profile_success_count"] == 4
    assert body["face_success_count"] == 3
    assert [row["biometric_status"] for row in body["students"]] == [
        "enrolled",
        "enrolled",
        "enrolled",
        "not_processed",
    ]
    assert body["students"][0]["full_name"] == "Student 101"
    assert body["students"][3]["issues"][0]["code"] == "PHOTO_MISSING"
    assert body["unmatched_files"][0]["filename"] == "999.webp"


async def test_duplicate_and_unsupported_photos_are_visible_and_never_chosen(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    admin, _, classroom, students = await _seed_scope(
        client_db, db_session, suffix="invalid-photos", rolls=["101", "102"]
    )
    archive = _zip_bytes(
        {
            "101.jpg": make_jpeg_bytes(),
            "101.png": make_png_bytes(),
            "102.gif": b"not-an-allowed-image",
        }
    )

    response = await _post(
        client_db,
        actor=admin,
        classroom_id=classroom["id"],
        spreadsheet=_csv(classroom["id"], students, ["101", "102"]),
        photos=archive,
    )
    assert response.status_code == 200, response.text
    rows = response.json()["students"]
    assert rows[0]["photo_status"] == "duplicate"
    assert rows[0]["biometric_status"] == "not_processed"
    assert rows[1]["photo_status"] == "invalid"
    assert rows[1]["issues"][0]["code"] == "ZIP_MEMBER_UNSUPPORTED_EXTENSION"
    assert response.json()["face_success_count"] == 0


async def test_face_failures_are_isolated_and_profiles_remain_successful(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    admin, _, classroom, students = await _seed_scope(
        client_db, db_session, suffix="face-failures", rolls=["101", "102", "103"]
    )
    archive = _zip_bytes(
        {
            "101.jpg": make_jpeg_bytes(color=(1, 2, 3)),
            "102.jpg": make_jpeg_bytes(color=(4, 5, 6)),
            "103.jpg": make_jpeg_bytes(color=(7, 8, 9)),
        }
    )
    detector = FakeFaceDetector(
        results=[[], [make_detected_face(), make_detected_face()], [make_detected_face()]]
    )

    with patch_providers(detector, FakeFaceEmbedder()):
        response = await _post(
            client_db,
            actor=admin,
            classroom_id=classroom["id"],
            spreadsheet=_csv(classroom["id"], students, ["101", "102", "103"]),
            photos=archive,
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["profile_success_count"] == 3
    assert body["face_success_count"] == 1
    assert body["students"][0]["issues"][0]["code"] == "ZERO_FACES_DETECTED"
    assert body["students"][1]["issues"][0]["code"] == "MULTIPLE_FACES_DETECTED"
    assert body["students"][2]["biometric_status"] == "enrolled"


async def test_existing_enrollment_is_resolved_but_never_overwritten(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    admin, _, classroom, students = await _seed_scope(
        client_db, db_session, suffix="existing", rolls=["101"]
    )
    spreadsheet = _csv(classroom["id"], students, ["101"])

    with patch_providers(FakeFaceDetector(), FakeFaceEmbedder()):
        first = await _post(
            client_db,
            actor=admin,
            classroom_id=classroom["id"],
            spreadsheet=spreadsheet,
            photos=_zip_bytes({"101.jpg": make_jpeg_bytes(color=(1, 1, 1))}),
        )
    assert first.status_code == 200, first.text
    profile_id = first.json()["students"][0]["student_profile_id"]
    enrollment = await BiometricEnrollmentRepository(db_session).get_by_student_profile_id(
        profile_id
    )
    assert enrollment is not None
    active_before = await BiometricSampleRepository(db_session).get_active_for_enrollment(
        enrollment.id
    )
    assert active_before is not None

    second = await _post(
        client_db,
        actor=admin,
        classroom_id=classroom["id"],
        spreadsheet=spreadsheet,
        photos=_zip_bytes({"101.jpg": make_jpeg_bytes(color=(2, 2, 2))}),
        update_existing=True,
    )
    assert second.status_code == 200, second.text
    row = second.json()["students"][0]
    assert row["profile_status"] == "updated"
    assert row["biometric_status"] == "already_enrolled"
    active_after = await BiometricSampleRepository(db_session).get_active_for_enrollment(
        enrollment.id
    )
    assert active_after is not None
    assert active_after.id == active_before.id


async def test_existing_profile_update_off_is_unchanged_and_skips_face_work(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    admin, _, classroom_a, students = await _seed_scope(
        client_db, db_session, suffix="existing-off", rolls=["101"]
    )
    classroom_b = await create_resource(
        client_db,
        path="/api/v1/classrooms",
        payload={"name": "Existing Off Target", "code": "existing-off-target"},
        user=admin,
    )
    profile = await create_resource(
        client_db,
        path="/api/v1/student-profiles",
        payload={
            "user_id": str(students[0].id),
            "classroom_id": classroom_a["id"],
            "roll_number": "101",
        },
        user=admin,
    )

    response = await _post(
        client_db,
        actor=admin,
        classroom_id=classroom_b["id"],
        spreadsheet=_csv(classroom_a["id"], students, ["202"]),
        photos=_zip_bytes({"202.jpg": make_jpeg_bytes()}),
    )

    assert response.status_code == 200, response.text
    row = response.json()["students"][0]
    assert row["profile_status"] == "existing"
    assert row["biometric_status"] == "not_processed"
    unchanged = await StudentProfileRepository(db_session).get_by_id(uuid.UUID(profile["id"]))
    assert unchanged is not None
    assert str(unchanged.classroom_id) == classroom_a["id"]
    assert unchanged.roll_number == "101"
    assert unchanged.is_active is True
    assert (
        await BiometricEnrollmentRepository(db_session).get_by_student_profile_id(unchanged.id)
        is None
    )


async def test_update_existing_moves_same_profile_and_preserves_identity_history_and_password(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    admin, _, classroom_a, students = await _seed_scope(
        client_db, db_session, suffix="existing-move", rolls=["101"]
    )
    classroom_b = await create_resource(
        client_db,
        path="/api/v1/classrooms",
        payload={"name": "Existing Move Target", "code": "existing-move-target"},
        user=admin,
    )
    subject = await create_resource(
        client_db,
        path="/api/v1/subjects",
        payload={"name": "History Subject", "code": "existing-move-history"},
        user=admin,
    )
    profile = await create_resource(
        client_db,
        path="/api/v1/student-profiles",
        payload={
            "user_id": str(students[0].id),
            "classroom_id": classroom_a["id"],
            "roll_number": "101",
        },
        user=admin,
    )
    profile_id = uuid.UUID(profile["id"])
    original_user_id = students[0].id
    original_password_hash = students[0].password_hash
    attendance = AttendanceRecord(
        student_profile_id=profile_id,
        classroom_id=uuid.UUID(str(classroom_a["id"])),
        subject_id=uuid.UUID(str(subject["id"])),
        attendance_date=date(2026, 8, 1),
        status=AttendanceStatus.PRESENT,
        remarks="Historical class attendance",
        marked_by_user_id=admin.id,
    )
    db_session.add(attendance)
    await db_session.commit()
    attendance_id = attendance.id

    response = await _post(
        client_db,
        actor=admin,
        classroom_id=classroom_b["id"],
        spreadsheet=_csv(classroom_a["id"], students, ["202"]),
        update_existing=True,
    )

    assert response.status_code == 200, response.text
    row = response.json()["students"][0]
    assert row["profile_status"] == "updated"
    assert row["student_profile_id"] == str(profile_id)
    moved = await StudentProfileRepository(db_session).get_by_user_id(original_user_id)
    assert moved is not None
    assert moved.id == profile_id
    assert moved.user_id == original_user_id
    assert str(moved.classroom_id) == classroom_b["id"]
    assert moved.roll_number == "202"
    await db_session.refresh(students[0])
    assert students[0].password_hash == original_password_hash
    assert (
        int(
            (
                await db_session.execute(
                    select(func.count(StudentProfile.id)).where(
                        StudentProfile.user_id == original_user_id
                    )
                )
            ).scalar_one()
        )
        == 1
    )
    preserved_attendance = await db_session.get(AttendanceRecord, attendance_id)
    assert preserved_attendance is not None
    assert str(preserved_attendance.classroom_id) == classroom_a["id"]

    old_roster = await client_db.get(
        "/api/v1/student-profiles",
        params={"classroom_id": classroom_a["id"]},
        headers=auth_headers(admin),
    )
    new_roster = await client_db.get(
        "/api/v1/student-profiles",
        params={"classroom_id": classroom_b["id"]},
        headers=auth_headers(admin),
    )
    assert old_roster.json()["total"] == 0
    assert new_roster.json()["total"] == 1
    assert new_roster.json()["items"][0]["id"] == str(profile_id)
    assert new_roster.json()["items"][0]["full_name"] == "Student 101"


async def test_update_existing_reactivates_same_profile_and_can_enroll_missing_biometric(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    admin, _, classroom_a, students = await _seed_scope(
        client_db, db_session, suffix="existing-reactivate", rolls=["101"]
    )
    classroom_b = await create_resource(
        client_db,
        path="/api/v1/classrooms",
        payload={"name": "Reactivation Target", "code": "reactivation-target"},
        user=admin,
    )
    profile = await create_resource(
        client_db,
        path="/api/v1/student-profiles",
        payload={
            "user_id": str(students[0].id),
            "classroom_id": classroom_a["id"],
            "roll_number": "101",
        },
        user=admin,
    )
    await client_db.delete(f"/api/v1/student-profiles/{profile['id']}", headers=auth_headers(admin))

    with patch_providers(FakeFaceDetector(), FakeFaceEmbedder()):
        response = await _post(
            client_db,
            actor=admin,
            classroom_id=classroom_b["id"],
            spreadsheet=_csv(classroom_a["id"], students, ["202"]),
            photos=_zip_bytes({"202.jpg": make_jpeg_bytes()}),
            update_existing=True,
        )

    assert response.status_code == 200, response.text
    row = response.json()["students"][0]
    assert row["profile_status"] == "reactivated"
    assert row["biometric_status"] == "enrolled"
    reactivated = await StudentProfileRepository(db_session).get_by_user_id(students[0].id)
    assert reactivated is not None
    assert reactivated.id == uuid.UUID(profile["id"])
    assert reactivated.is_active is True
    assert str(reactivated.classroom_id) == classroom_b["id"]


async def test_matching_is_limited_to_this_import_not_global_roll_numbers(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    admin, _, classroom_a, students_a = await _seed_scope(
        client_db, db_session, suffix="scope-a", rolls=["101"]
    )
    _, _, classroom_b, students_b = await _seed_scope(
        client_db, db_session, suffix="scope-b", rolls=["101"]
    )
    existing_b = await create_resource(
        client_db,
        path="/api/v1/student-profiles",
        payload={
            "user_id": str(students_b[0].id),
            "classroom_id": classroom_b["id"],
            "roll_number": "101",
        },
        user=admin,
    )

    with patch_providers(FakeFaceDetector(), FakeFaceEmbedder()):
        response = await _post(
            client_db,
            actor=admin,
            classroom_id=classroom_a["id"],
            spreadsheet=_csv(classroom_a["id"], students_a, ["101"]),
            photos=_zip_bytes({"101.jpg": make_jpeg_bytes()}),
        )

    assert response.status_code == 200, response.text
    new_profile_id = response.json()["students"][0]["student_profile_id"]
    assert new_profile_id != existing_b["id"]
    existing_enrollment = await BiometricEnrollmentRepository(db_session).get_by_student_profile_id(
        uuid.UUID(str(existing_b["id"]))
    )
    assert existing_enrollment is None
    new_profile = await StudentProfileRepository(db_session).get_by_id(new_profile_id)
    assert new_profile is not None
    assert str(new_profile.classroom_id) == classroom_a["id"]


async def test_teacher_is_denied_and_admin_is_allowed(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    admin, teacher, classroom, students = await _seed_scope(
        client_db, db_session, suffix="authorization", rolls=["101"]
    )
    spreadsheet = _csv(classroom["id"], students, ["101"])
    denied = await _post(
        client_db,
        actor=teacher,
        classroom_id=classroom["id"],
        spreadsheet=spreadsheet,
    )
    assert denied.status_code == 403
    allowed = await _post(
        client_db,
        actor=admin,
        classroom_id=classroom["id"],
        spreadsheet=spreadsheet,
    )
    assert allowed.status_code == 200
    assert allowed.json()["profile_success_count"] == 1


async def test_unsafe_zip_path_rejects_archive_without_weakening_security(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    admin, _, classroom, students = await _seed_scope(
        client_db, db_session, suffix="zip-security", rolls=["101"]
    )
    response = await _post(
        client_db,
        actor=admin,
        classroom_id=classroom["id"],
        spreadsheet=_csv(classroom["id"], students, ["101"]),
        photos=_zip_bytes({"../101.jpg": make_jpeg_bytes()}),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "BULK_ENROLLMENT_VALIDATION_FAILED"
    profile = await StudentProfileRepository(db_session).get_by_user_id(students[0].id)
    assert profile is not None
