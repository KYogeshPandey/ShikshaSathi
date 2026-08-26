"""Orchestrate existing student import, biometric enrollment, and processing.

The spreadsheet remains the identity authority: ZIP member stems are matched
only to rows in this request, never through a global roll-number lookup. The
existing importer, enrollment lifecycle, image validation/storage, and face
processing pipeline retain ownership of their respective rules.
"""

from __future__ import annotations

import uuid
import zipfile
from collections import defaultdict
from collections.abc import AsyncIterator
from pathlib import PurePosixPath
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.modules.academics.repository import ClassroomRepository
from app.modules.biometric_enrollment.errors import (
    BulkEnrollmentZipTooLargeError,
    EnrollmentAlreadyActiveError,
)
from app.modules.biometric_enrollment.service import BiometricEnrollmentService
from app.modules.biometric_enrollment.storage import (
    PrivateBiometricStorage,
    StorageCapExceededError,
)
from app.modules.biometric_enrollment.zip_security import (
    PhotoArchiveFileProblem,
    PhotoArchiveMember,
    validate_photo_archive,
)
from app.modules.bulk_imports.schemas import BulkImportEntity
from app.modules.bulk_imports.service import BulkImportRowOutcome, BulkImportService
from app.modules.face_recognition.processing_service import SampleProcessingService
from app.modules.profiles.errors import (
    ClassroomMembershipReferenceError,
    InactiveClassroomMembershipError,
)
from app.modules.profiles.models import StudentProfile
from app.modules.profiles.repository import StudentProfileRepository
from app.modules.student_onboarding.schemas import (
    StudentOnboardingIssue,
    StudentOnboardingResult,
    StudentOnboardingStudentResult,
    StudentOnboardingUnmatchedFile,
)
from app.modules.users.models import User
from app.modules.users.repository import UserRepository

_PROCESSING_MESSAGES = {
    "zero_faces_detected": "No face was detected in the photo.",
    "multiple_faces_detected": "Multiple faces were detected in the photo.",
    "provider_unavailable": "Face processing is not available on this server.",
    "image_decode_failed": "The photo could not be decoded.",
    "detection_failed": "Face detection failed for this photo.",
    "alignment_failed": "The detected face could not be aligned.",
    "embedding_failed": "The face template could not be created.",
    "storage_file_missing": "The enrolled photo could not be read from storage.",
    "unexpected_processing_error": "Face processing failed unexpectedly.",
}


def _normalize_roll(value: str | None) -> str | None:
    normalized = (value or "").strip().casefold()
    return normalized or None


def _member_stem(filename: str) -> str:
    return PurePosixPath(filename).stem.strip().casefold()


def _issue(code: str, message: str) -> StudentOnboardingIssue:
    return StudentOnboardingIssue(code=code, message=message)


async def _member_chunks(
    zf: zipfile.ZipFile, member: PhotoArchiveMember, *, chunk_size: int = 1024 * 1024
) -> AsyncIterator[bytes]:
    with zf.open(member.zip_info) as handle:
        while chunk := handle.read(chunk_size):
            yield chunk


class StudentOnboardingService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        storage: PrivateBiometricStorage | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._storage = storage or PrivateBiometricStorage(self._settings)
        self._classrooms = ClassroomRepository(session)
        self._profiles = StudentProfileRepository(session)
        self._users = UserRepository(session)

    async def onboard(
        self,
        *,
        current_user: User,
        classroom_id: uuid.UUID,
        students_filename: str,
        students_content: bytes,
        photos_chunks: AsyncIterator[bytes] | None,
        request_id: str | None = None,
    ) -> StudentOnboardingResult:
        classroom = await self._classrooms.get_by_id(classroom_id)
        if classroom is None:
            raise ClassroomMembershipReferenceError()
        if not classroom.is_active:
            raise InactiveClassroomMembershipError()
        selected_classroom_id = classroom.id
        selected_classroom_name = classroom.name
        detailed = await BulkImportService(self._session).import_file_detailed(
            entity=BulkImportEntity.STUDENT_PROFILES,
            filename=students_filename,
            content=students_content,
            fixed_values={"classroom_id": selected_classroom_id},
        )
        # A handled per-row integrity conflict (notably an already-existing
        # profile on an idempotent rerun) rolls back that row's transaction,
        # which expires every ORM object attached to this session. Refresh the
        # already-authorized actor explicitly before enrollment services read
        # its ID; this avoids an implicit async lazy load outside greenlet
        # context while leaving the existing import transaction semantics intact.
        await self._session.refresh(current_user)
        students = [await self._resolve_row(row) for row in detailed.rows]
        if photos_chunks is None:
            return self._result(
                students,
                classroom_id=selected_classroom_id,
                classroom_name=selected_classroom_name,
                unmatched_files=[],
                photos_provided=False,
            )

        zip_key = self._storage.new_key()
        try:
            try:
                await self._storage.write_bulk_zip_staged(
                    zip_key,
                    photos_chunks,
                    max_bytes=self._settings.MAX_BULK_ENROLLMENT_ZIP_BYTES,
                )
            except StorageCapExceededError as exc:
                raise BulkEnrollmentZipTooLargeError(
                    self._settings.MAX_BULK_ENROLLMENT_ZIP_BYTES
                ) from exc

            inspection = validate_photo_archive(
                self._storage.bulk_zip_staging_path(zip_key), settings=self._settings
            )
            unmatched = await self._apply_photos(
                students=students,
                members=list(inspection.members),
                problems=list(inspection.problems),
                zip_key=zip_key,
                current_user=current_user,
                request_id=request_id,
            )
            return self._result(
                students,
                classroom_id=selected_classroom_id,
                classroom_name=selected_classroom_name,
                unmatched_files=unmatched,
                photos_provided=True,
            )
        finally:
            self._storage.discard_bulk_zip_staged(zip_key)

    async def _resolve_row(self, row: BulkImportRowOutcome) -> StudentOnboardingStudentResult:
        user_id = self._uuid_value(row.values.get("user_id"))
        requested_classroom_id = self._uuid_value(row.values.get("classroom_id"))
        requested_roll = self._string_value(row.values.get("roll_number"))
        profile: StudentProfile | None = None
        profile_status: Literal["imported", "existing", "failed"] = "failed"
        issues: list[StudentOnboardingIssue] = []

        if row.error is None and user_id is not None:
            profile = await self._profiles.get_by_user_id(user_id)
            if profile is not None:
                profile_status = "imported"
        elif (
            row.error is not None
            and row.error.code == "STUDENT_PROFILE_ALREADY_EXISTS"
            and user_id is not None
        ):
            candidate = await self._profiles.get_by_user_id(user_id)
            if (
                candidate is not None
                and candidate.is_active
                and candidate.classroom_id == requested_classroom_id
                and _normalize_roll(candidate.roll_number) == _normalize_roll(requested_roll)
            ):
                profile = candidate
                profile_status = "existing"

        if profile is None:
            if row.error is not None:
                issues.append(_issue(row.error.code, row.error.message))
            elif user_id is None:
                issues.append(_issue("BULK_IMPORT_ROW_VALIDATION_ERROR", "Invalid user_id."))
            else:
                issues.append(
                    _issue(
                        "STUDENT_PROFILE_RESOLUTION_FAILED",
                        "Student profile could not be resolved.",
                    )
                )

        user = await self._users.get_by_id(user_id) if user_id is not None else None
        return StudentOnboardingStudentResult(
            row_number=row.row_number,
            student_profile_id=profile.id if profile is not None else None,
            full_name=user.full_name if user is not None else None,
            roll_number=profile.roll_number if profile is not None else requested_roll,
            profile_status=profile_status,
            photo_status="missing",
            biometric_status="not_processed",
            issues=issues,
        )

    async def _apply_photos(
        self,
        *,
        students: list[StudentOnboardingStudentResult],
        members: list[PhotoArchiveMember],
        problems: list[PhotoArchiveFileProblem],
        zip_key: str,
        current_user: User,
        request_id: str | None,
    ) -> list[StudentOnboardingUnmatchedFile]:
        rows_by_roll: dict[str, list[StudentOnboardingStudentResult]] = defaultdict(list)
        for student in students:
            roll = _normalize_roll(student.roll_number)
            if roll is not None:
                rows_by_roll[roll].append(student)

        members_by_stem: dict[str, list[PhotoArchiveMember]] = defaultdict(list)
        for member in members:
            members_by_stem[_member_stem(member.filename)].append(member)
        problems_by_stem: dict[str, list[PhotoArchiveFileProblem]] = defaultdict(list)
        for problem in problems:
            problems_by_stem[_member_stem(problem.filename)].append(problem)

        unmatched: list[StudentOnboardingUnmatchedFile] = []
        used_filenames: set[str] = set()
        with zipfile.ZipFile(self._storage.bulk_zip_staging_path(zip_key)) as zf:
            for roll, matching_rows in rows_by_roll.items():
                matching_members = members_by_stem.get(roll, [])
                matching_problems = problems_by_stem.get(roll, [])
                all_names = [member.filename for member in matching_members] + [
                    problem.filename for problem in matching_problems
                ]
                if len(matching_rows) > 1 or len(all_names) > 1:
                    message = "Multiple spreadsheet rows or photos use this roll number."
                    for student in matching_rows:
                        student.photo_status = "duplicate"
                        student.biometric_status = "not_processed"
                        student.issues.append(_issue("DUPLICATE_PHOTO_MATCH", message))
                    for filename in all_names:
                        used_filenames.add(filename)
                        unmatched.append(
                            StudentOnboardingUnmatchedFile(
                                filename=filename,
                                code="DUPLICATE_PHOTO_MATCH",
                                message=message,
                            )
                        )
                    continue

                student = matching_rows[0]
                if matching_problems:
                    problem = matching_problems[0]
                    used_filenames.add(problem.filename)
                    student.photo_filename = problem.filename
                    student.photo_status = "invalid"
                    student.biometric_status = "not_processed"
                    student.issues.append(_issue(problem.code, problem.message))
                    unmatched.append(
                        StudentOnboardingUnmatchedFile(
                            filename=problem.filename,
                            code=problem.code,
                            message=problem.message,
                        )
                    )
                    continue
                if not matching_members:
                    student.photo_status = "missing"
                    student.biometric_status = "not_processed"
                    student.issues.append(
                        _issue("PHOTO_MISSING", "No matching photo was provided.")
                    )
                    continue

                member = matching_members[0]
                used_filenames.add(member.filename)
                student.photo_filename = member.filename
                student.photo_status = "matched"
                if student.student_profile_id is None:
                    student.biometric_status = "not_processed"
                    student.issues.append(
                        _issue(
                            "PROFILE_REQUIRED_FOR_ENROLLMENT",
                            "The photo matched, but the student profile was not imported.",
                        )
                    )
                    continue
                await self._enroll_one(
                    student=student,
                    zf=zf,
                    member=member,
                    current_user=current_user,
                    request_id=request_id,
                )

        for member in members:
            if member.filename not in used_filenames:
                unmatched.append(
                    StudentOnboardingUnmatchedFile(
                        filename=member.filename,
                        code="PHOTO_NO_MATCHING_STUDENT",
                        message="No matching student roll number exists in this import.",
                    )
                )
        for problem in problems:
            if problem.filename not in used_filenames:
                unmatched.append(
                    StudentOnboardingUnmatchedFile(
                        filename=problem.filename,
                        code=problem.code,
                        message=problem.message,
                    )
                )
        return unmatched

    async def _enroll_one(
        self,
        *,
        student: StudentOnboardingStudentResult,
        zf: zipfile.ZipFile,
        member: PhotoArchiveMember,
        current_user: User,
        request_id: str | None,
    ) -> None:
        assert student.student_profile_id is not None
        try:
            sample = await BiometricEnrollmentService(
                self._session, settings=self._settings, storage=self._storage
            ).create_sample(
                current_user=current_user,
                student_profile_id=student.student_profile_id,
                chunks=_member_chunks(zf, member),
                declared_content_type=None,
                original_filename=member.filename,
                request_id=request_id,
            )
        except EnrollmentAlreadyActiveError as exc:
            student.biometric_status = "already_enrolled"
            student.issues.append(_issue(exc.code, "Student already has an active enrollment."))
            return
        except AppError as exc:
            student.biometric_status = "failed"
            student.issues.append(_issue(exc.code, exc.message))
            return

        processing = await SampleProcessingService(
            self._session, settings=self._settings, storage=self._storage
        ).process_sample(sample_id=sample.id, actor=current_user, request_id=request_id)
        if processing.succeeded:
            student.biometric_status = "enrolled"
            return
        reason = processing.reason_code or "unexpected_processing_error"
        student.biometric_status = "failed"
        student.issues.append(
            _issue(reason.upper(), _PROCESSING_MESSAGES.get(reason, "Face processing failed."))
        )

    @staticmethod
    def _uuid_value(value: object | None) -> uuid.UUID | None:
        try:
            return uuid.UUID(str(value)) if value is not None else None
        except (TypeError, ValueError, AttributeError):
            return None

    @staticmethod
    def _string_value(value: object | None) -> str | None:
        text = str(value).strip() if value is not None else ""
        return text or None

    @staticmethod
    def _result(
        students: list[StudentOnboardingStudentResult],
        *,
        classroom_id: uuid.UUID,
        classroom_name: str,
        unmatched_files: list[StudentOnboardingUnmatchedFile],
        photos_provided: bool,
    ) -> StudentOnboardingResult:
        if not photos_provided:
            for student in students:
                student.photo_status = "not_provided"
                student.biometric_status = "not_requested"
        return StudentOnboardingResult(
            classroom_id=classroom_id,
            classroom_name=classroom_name,
            total_students=len(students),
            profile_success_count=sum(
                student.profile_status in {"imported", "existing"} for student in students
            ),
            face_success_count=sum(student.biometric_status == "enrolled" for student in students),
            students=students,
            unmatched_files=unmatched_files,
        )
