"""Database-backed tests for ``app.modules.attendance.service.AttendanceService``.

Uses the ``db_session`` fixture (app/tests/conftest.py), which requires a
reachable Phase 4-migrated PostgreSQL test database and skips gracefully
if one is not available — same convention as
``app.tests.test_attendance_repository`` and
``app.tests.test_academics_repository``. No router/HTTP layer exists yet
(Stage 3), so every test calls ``AttendanceService`` directly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.academics.errors import InactiveAcademicReferenceError
from app.modules.academics.models import Classroom, Subject, TeacherAssignment
from app.modules.academics.repository import (
    ClassroomRepository,
    SubjectRepository,
    TeacherAssignmentRepository,
)
from app.modules.attendance.errors import (
    AttendanceBatchTooLargeError,
    AttendanceDuplicateStudentInBatchError,
    AttendanceInactiveStudentError,
    AttendanceRoleNotPermittedError,
    AttendanceScopeNotFoundError,
    AttendanceStudentNotFoundError,
    AttendanceStudentNotInClassroomError,
)
from app.modules.attendance.models import AttendanceStatus, AuditOutcome
from app.modules.attendance.repository import AttendanceRepository, AuditLogRepository
from app.modules.attendance.schemas import (
    MAX_BULK_ATTENDANCE_ROWS,
    BulkAttendanceRecordIn,
    BulkAttendanceRequest,
)
from app.modules.attendance.service import ACTION_ATTENDANCE_BULK_MARK, AttendanceService
from app.modules.auth.security import hash_password
from app.modules.profiles.models import StudentProfile, TeacherProfile
from app.modules.profiles.repository import StudentProfileRepository, TeacherProfileRepository
from app.modules.users.models import User, UserRole
from app.modules.users.normalization import normalize_email
from app.modules.users.repository import UserRepository

_PASSWORD = "a-strong-real-password-1"


# --- fixture helpers ---------------------------------------------------------


async def _create_user(
    session: AsyncSession, *, email: str, role: UserRole, is_active: bool = True
) -> User:
    user = await UserRepository(session).create(
        email=normalize_email(email),
        password_hash=hash_password(_PASSWORD),
        full_name=f"{role.value.title()} Service Test",
        role=role,
        is_active=is_active,
    )
    await session.commit()
    return user


async def _create_classroom(
    session: AsyncSession, *, code: str, is_active: bool = True
) -> Classroom:
    classroom = await ClassroomRepository(session).create(name=code.title(), code=code)
    if not is_active:
        classroom = await ClassroomRepository(session).update(classroom, is_active=False)
    await session.commit()
    return classroom


async def _create_subject(session: AsyncSession, *, code: str, is_active: bool = True) -> Subject:
    subject = await SubjectRepository(session).create(name=code.title(), code=code)
    if not is_active:
        subject = await SubjectRepository(session).update(subject, is_active=False)
    await session.commit()
    return subject


async def _create_teacher(
    session: AsyncSession,
    *,
    email: str,
    profile_active: bool = True,
) -> tuple[User, TeacherProfile]:
    user = await _create_user(session, email=email, role=UserRole.TEACHER)
    profile = await TeacherProfileRepository(session).create(user_id=user.id)
    if not profile_active:
        profile = await TeacherProfileRepository(session).deactivate(profile)
    await session.commit()
    return user, profile


async def _create_assignment(
    session: AsyncSession,
    *,
    teacher_profile_id: uuid.UUID,
    classroom_id: uuid.UUID,
    subject_id: uuid.UUID,
    is_active: bool = True,
) -> TeacherAssignment:
    assignment = await TeacherAssignmentRepository(session).create(
        teacher_profile_id=teacher_profile_id,
        classroom_id=classroom_id,
        subject_id=subject_id,
    )
    if not is_active:
        assignment = await TeacherAssignmentRepository(session).deactivate(assignment)
    await session.commit()
    return assignment


async def _create_student(
    session: AsyncSession,
    *,
    email: str,
    classroom_id: uuid.UUID | None,
    roll_number: str,
    is_active: bool = True,
) -> tuple[User, StudentProfile]:
    user = await _create_user(session, email=email, role=UserRole.STUDENT)
    profile = await StudentProfileRepository(session).create(
        user_id=user.id, classroom_id=classroom_id, roll_number=roll_number
    )
    if not is_active:
        profile = await StudentProfileRepository(session).deactivate(profile)
    await session.commit()
    return user, profile


@dataclass
class _Scope:
    classroom: Classroom
    subject: Subject
    admin_user: User
    teacher_user: User
    teacher_profile: TeacherProfile
    assignment: TeacherAssignment
    student_a: StudentProfile
    student_b: StudentProfile


async def _seed_basic(session: AsyncSession, *, suffix: str) -> _Scope:
    classroom = await _create_classroom(session, code=f"svc-room-{suffix}")
    subject = await _create_subject(session, code=f"svc-subj-{suffix}")
    admin_user = await _create_user(
        session, email=f"svc-admin-{suffix}@example.com", role=UserRole.ADMIN
    )
    teacher_user, teacher_profile = await _create_teacher(
        session, email=f"svc-teacher-{suffix}@example.com"
    )
    assignment = await _create_assignment(
        session,
        teacher_profile_id=teacher_profile.id,
        classroom_id=classroom.id,
        subject_id=subject.id,
    )
    _, student_a = await _create_student(
        session,
        email=f"svc-student-a-{suffix}@example.com",
        classroom_id=classroom.id,
        roll_number="01",
    )
    _, student_b = await _create_student(
        session,
        email=f"svc-student-b-{suffix}@example.com",
        classroom_id=classroom.id,
        roll_number="02",
    )
    return _Scope(
        classroom=classroom,
        subject=subject,
        admin_user=admin_user,
        teacher_user=teacher_user,
        teacher_profile=teacher_profile,
        assignment=assignment,
        student_a=student_a,
        student_b=student_b,
    )


def _single_record_payload(
    scope: _Scope,
    *,
    status: AttendanceStatus,
    attendance_date: date = date(2026, 7, 1),
    student_id: uuid.UUID | None = None,
    remarks: str | None = None,
) -> BulkAttendanceRequest:
    return BulkAttendanceRequest(
        classroom_id=scope.classroom.id,
        subject_id=scope.subject.id,
        attendance_date=attendance_date,
        records=[
            BulkAttendanceRecordIn(
                student_profile_id=student_id or scope.student_a.id,
                status=status,
                remarks=remarks,
            )
        ],
    )


async def _attendance_count(
    session: AsyncSession, *, classroom_id: uuid.UUID, subject_id: uuid.UUID, on: date
) -> int:
    return await AttendanceRepository(session).count(
        classroom_id=classroom_id, subject_id=subject_id, date_from=on, date_to=on
    )


# --- 1/2: happy paths --------------------------------------------------------


async def test_admin_bulk_save_succeeds(db_session: AsyncSession) -> None:
    scope = await _seed_basic(db_session, suffix="admin-ok")
    service = AttendanceService(db_session)
    payload = BulkAttendanceRequest(
        classroom_id=scope.classroom.id,
        subject_id=scope.subject.id,
        attendance_date=date(2026, 7, 1),
        records=[
            BulkAttendanceRecordIn(
                student_profile_id=scope.student_a.id, status=AttendanceStatus.PRESENT
            ),
            BulkAttendanceRecordIn(
                student_profile_id=scope.student_b.id,
                status=AttendanceStatus.ABSENT,
                remarks="sick",
            ),
        ],
    )
    result = await service.bulk_save(
        current_user=scope.admin_user, payload=payload, request_id="req-admin-ok"
    )
    assert result.created_count == 2
    assert result.updated_count == 0
    assert result.total_count == 2
    assert len(result.record_ids) == 2


async def test_assigned_teacher_bulk_save_succeeds(db_session: AsyncSession) -> None:
    scope = await _seed_basic(db_session, suffix="teacher-ok")
    service = AttendanceService(db_session)
    payload = _single_record_payload(scope, status=AttendanceStatus.PRESENT)
    result = await service.bulk_save(
        current_user=scope.teacher_user, payload=payload, request_id="req-teacher-ok"
    )
    assert result.created_count == 1
    assert result.updated_count == 0


# --- 3: unrelated teacher rejected -------------------------------------------


async def test_unrelated_teacher_rejected_with_concealed_scope_error(
    db_session: AsyncSession,
) -> None:
    scope = await _seed_basic(db_session, suffix="unrel")
    other_teacher_user, _ = await _create_teacher(
        db_session, email="svc-other-teacher-unrel@example.com"
    )
    service = AttendanceService(db_session)
    payload = _single_record_payload(scope, status=AttendanceStatus.PRESENT)
    with pytest.raises(AttendanceScopeNotFoundError):
        await service.bulk_save(
            current_user=other_teacher_user, payload=payload, request_id="req-unrel"
        )


# --- 4/5/6: blocked audit ------------------------------------------------------


async def test_blocked_attempt_persists_exactly_one_blocked_audit(db_session: AsyncSession) -> None:
    scope = await _seed_basic(db_session, suffix="blocked-count")
    other_teacher_user, _ = await _create_teacher(
        db_session, email="svc-other-teacher-blocked-count@example.com"
    )
    actor_user_id = other_teacher_user.id
    service = AttendanceService(db_session)
    payload = _single_record_payload(scope, status=AttendanceStatus.PRESENT)
    with pytest.raises(AttendanceScopeNotFoundError):
        await service.bulk_save(
            current_user=other_teacher_user, payload=payload, request_id="req-blocked-count"
        )
    rows = await AuditLogRepository(db_session).list(
        actor_user_id=actor_user_id, outcome=AuditOutcome.BLOCKED
    )
    assert len(rows) == 1


async def test_blocked_audit_records_expected_fields(db_session: AsyncSession) -> None:
    scope = await _seed_basic(db_session, suffix="blocked-fields")
    other_teacher_user, _ = await _create_teacher(
        db_session, email="svc-other-teacher-blocked-fields@example.com"
    )
    actor_user_id = other_teacher_user.id
    classroom_id = scope.classroom.id
    subject_id = scope.subject.id
    service = AttendanceService(db_session)
    payload = _single_record_payload(scope, status=AttendanceStatus.PRESENT)
    with pytest.raises(AttendanceScopeNotFoundError):
        await service.bulk_save(
            current_user=other_teacher_user, payload=payload, request_id="req-blocked-fields"
        )
    rows = await AuditLogRepository(db_session).list(
        actor_user_id=actor_user_id, outcome=AuditOutcome.BLOCKED
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.actor_user_id == actor_user_id
    assert row.request_id == "req-blocked-fields"
    assert row.action == ACTION_ATTENDANCE_BULK_MARK
    assert row.outcome is AuditOutcome.BLOCKED
    assert row.classroom_id == classroom_id
    assert row.subject_id == subject_id
    assert row.event_metadata.get("reason_code") == "teacher_assignment_inactive_or_missing"


async def test_blocked_audit_metadata_has_no_secrets_or_payload(db_session: AsyncSession) -> None:
    scope = await _seed_basic(db_session, suffix="blocked-safe")
    other_teacher_user, _ = await _create_teacher(
        db_session, email="svc-other-teacher-blocked-safe@example.com"
    )
    actor_user_id = other_teacher_user.id
    service = AttendanceService(db_session)
    payload = _single_record_payload(
        scope, status=AttendanceStatus.ABSENT, remarks="TOP-SECRET-REMARK-VALUE"
    )
    with pytest.raises(AttendanceScopeNotFoundError):
        await service.bulk_save(
            current_user=other_teacher_user, payload=payload, request_id="req-blocked-safe"
        )
    rows = await AuditLogRepository(db_session).list(
        actor_user_id=actor_user_id, outcome=AuditOutcome.BLOCKED
    )
    assert len(rows) == 1
    metadata = rows[0].event_metadata
    assert set(metadata.keys()) == {"reason_code", "attempted_action"}
    serialized = str(metadata)
    assert "TOP-SECRET-REMARK-VALUE" not in serialized
    assert "password" not in serialized.lower()
    assert "token" not in serialized.lower()


# --- 7/8: inactive teacher profile / assignment (concealed) -------------------


async def test_inactive_teacher_profile_rejected(db_session: AsyncSession) -> None:
    scope = await _seed_basic(db_session, suffix="inactive-profile")
    inactive_teacher_user, inactive_profile = await _create_teacher(
        db_session, email="svc-inactive-profile@example.com", profile_active=False
    )
    await _create_assignment(
        db_session,
        teacher_profile_id=inactive_profile.id,
        classroom_id=scope.classroom.id,
        subject_id=scope.subject.id,
    )
    actor_user_id = inactive_teacher_user.id
    service = AttendanceService(db_session)
    payload = _single_record_payload(scope, status=AttendanceStatus.PRESENT)
    with pytest.raises(AttendanceScopeNotFoundError):
        await service.bulk_save(current_user=inactive_teacher_user, payload=payload)
    rows = await AuditLogRepository(db_session).list(
        actor_user_id=actor_user_id, outcome=AuditOutcome.BLOCKED
    )
    assert rows[0].event_metadata.get("reason_code") == "teacher_profile_inactive_or_missing"


async def test_inactive_assignment_rejected(db_session: AsyncSession) -> None:
    scope = await _seed_basic(db_session, suffix="inactive-assign")
    await TeacherAssignmentRepository(db_session).deactivate(scope.assignment)
    await db_session.commit()
    actor_user_id = scope.teacher_user.id
    service = AttendanceService(db_session)
    payload = _single_record_payload(scope, status=AttendanceStatus.PRESENT)
    with pytest.raises(AttendanceScopeNotFoundError):
        await service.bulk_save(current_user=scope.teacher_user, payload=payload)
    rows = await AuditLogRepository(db_session).list(
        actor_user_id=actor_user_id, outcome=AuditOutcome.BLOCKED
    )
    assert rows[0].event_metadata.get("reason_code") == "teacher_assignment_inactive_or_missing"


# --- 9/10: inactive classroom / subject (admin path) ---------------------------


async def test_inactive_classroom_rejected(db_session: AsyncSession) -> None:
    scope = await _seed_basic(db_session, suffix="inactive-room")
    await ClassroomRepository(db_session).update(scope.classroom, is_active=False)
    await db_session.commit()
    service = AttendanceService(db_session)
    payload = _single_record_payload(scope, status=AttendanceStatus.PRESENT)
    with pytest.raises(InactiveAcademicReferenceError):
        await service.bulk_save(current_user=scope.admin_user, payload=payload)


async def test_inactive_subject_rejected(db_session: AsyncSession) -> None:
    scope = await _seed_basic(db_session, suffix="inactive-subj")
    await SubjectRepository(db_session).update(scope.subject, is_active=False)
    await db_session.commit()
    service = AttendanceService(db_session)
    payload = _single_record_payload(scope, status=AttendanceStatus.PRESENT)
    with pytest.raises(InactiveAcademicReferenceError):
        await service.bulk_save(current_user=scope.admin_user, payload=payload)


# --- 11/12: student validation --------------------------------------------------


async def test_inactive_student_rejected(db_session: AsyncSession) -> None:
    scope = await _seed_basic(db_session, suffix="inactive-student")
    _, inactive_student = await _create_student(
        db_session,
        email="svc-inactive-student@example.com",
        classroom_id=scope.classroom.id,
        roll_number="09",
        is_active=False,
    )
    service = AttendanceService(db_session)
    payload = _single_record_payload(
        scope, status=AttendanceStatus.PRESENT, student_id=inactive_student.id
    )
    with pytest.raises(AttendanceInactiveStudentError):
        await service.bulk_save(current_user=scope.admin_user, payload=payload)
    assert (
        await _attendance_count(
            db_session,
            classroom_id=scope.classroom.id,
            subject_id=scope.subject.id,
            on=date(2026, 7, 1),
        )
        == 0
    )


async def test_student_outside_target_classroom_rejected(db_session: AsyncSession) -> None:
    scope = await _seed_basic(db_session, suffix="wrong-room")
    other_classroom = await _create_classroom(db_session, code="svc-other-room-wrong-room")
    _, outside_student = await _create_student(
        db_session,
        email="svc-outside-student@example.com",
        classroom_id=other_classroom.id,
        roll_number="01",
    )
    service = AttendanceService(db_session)
    payload = _single_record_payload(
        scope, status=AttendanceStatus.PRESENT, student_id=outside_student.id
    )
    with pytest.raises(AttendanceStudentNotInClassroomError):
        await service.bulk_save(current_user=scope.admin_user, payload=payload)


# --- 13/14: batch-shape defense in depth (bypasses schema validation) ---------


async def test_duplicate_student_ids_rejected_before_writes(db_session: AsyncSession) -> None:
    scope = await _seed_basic(db_session, suffix="dup-ids")
    payload = BulkAttendanceRequest.model_construct(
        classroom_id=scope.classroom.id,
        subject_id=scope.subject.id,
        attendance_date=date(2026, 7, 5),
        records=[
            BulkAttendanceRecordIn(
                student_profile_id=scope.student_a.id, status=AttendanceStatus.PRESENT
            ),
            BulkAttendanceRecordIn(
                student_profile_id=scope.student_a.id, status=AttendanceStatus.ABSENT
            ),
        ],
    )
    service = AttendanceService(db_session)
    with pytest.raises(AttendanceDuplicateStudentInBatchError):
        await service.bulk_save(current_user=scope.admin_user, payload=payload)
    assert (
        await _attendance_count(
            db_session,
            classroom_id=scope.classroom.id,
            subject_id=scope.subject.id,
            on=date(2026, 7, 5),
        )
        == 0
    )


async def test_batch_larger_than_max_rejected(db_session: AsyncSession) -> None:
    scope = await _seed_basic(db_session, suffix="too-big")
    too_many = [
        BulkAttendanceRecordIn(student_profile_id=uuid.uuid4(), status=AttendanceStatus.PRESENT)
        for _ in range(MAX_BULK_ATTENDANCE_ROWS + 1)
    ]
    payload = BulkAttendanceRequest.model_construct(
        classroom_id=scope.classroom.id,
        subject_id=scope.subject.id,
        attendance_date=date(2026, 7, 6),
        records=too_many,
    )
    service = AttendanceService(db_session)
    with pytest.raises(AttendanceBatchTooLargeError):
        await service.bulk_save(current_user=scope.admin_user, payload=payload)


# --- 15/16/17: create/update/marked_by semantics -------------------------------


async def test_new_rows_are_created(db_session: AsyncSession) -> None:
    scope = await _seed_basic(db_session, suffix="create-new")
    service = AttendanceService(db_session)
    payload = _single_record_payload(
        scope, status=AttendanceStatus.PRESENT, attendance_date=date(2026, 7, 7)
    )
    result = await service.bulk_save(current_user=scope.admin_user, payload=payload)
    assert result.created_count == 1
    assert result.updated_count == 0
    record = await AttendanceRepository(db_session).get_by_unique_key(
        student_profile_id=scope.student_a.id,
        classroom_id=scope.classroom.id,
        subject_id=scope.subject.id,
        attendance_date=date(2026, 7, 7),
    )
    assert record is not None
    assert record.status is AttendanceStatus.PRESENT


async def test_existing_rows_updated_deterministically(db_session: AsyncSession) -> None:
    scope = await _seed_basic(db_session, suffix="update-existing")
    service = AttendanceService(db_session)
    on = date(2026, 7, 8)

    first = await service.bulk_save(
        current_user=scope.admin_user,
        payload=_single_record_payload(scope, status=AttendanceStatus.PRESENT, attendance_date=on),
    )
    second = await service.bulk_save(
        current_user=scope.admin_user,
        payload=_single_record_payload(
            scope, status=AttendanceStatus.ABSENT, attendance_date=on, remarks="corrected"
        ),
    )

    assert first.created_count == 1
    assert first.updated_count == 0
    assert second.created_count == 0
    assert second.updated_count == 1
    # Same underlying row updated in place, not duplicated.
    assert first.record_ids == second.record_ids

    record = await AttendanceRepository(db_session).get_by_unique_key(
        student_profile_id=scope.student_a.id,
        classroom_id=scope.classroom.id,
        subject_id=scope.subject.id,
        attendance_date=on,
    )
    assert record is not None
    assert record.status is AttendanceStatus.ABSENT
    assert record.remarks == "corrected"
    assert (
        await _attendance_count(
            db_session, classroom_id=scope.classroom.id, subject_id=scope.subject.id, on=on
        )
        == 1
    )


async def test_marked_by_user_id_comes_from_current_user(db_session: AsyncSession) -> None:
    scope = await _seed_basic(db_session, suffix="marked-by")
    service = AttendanceService(db_session)
    payload = _single_record_payload(
        scope, status=AttendanceStatus.PRESENT, attendance_date=date(2026, 7, 9)
    )
    await service.bulk_save(current_user=scope.teacher_user, payload=payload)
    record = await AttendanceRepository(db_session).get_by_unique_key(
        student_profile_id=scope.student_a.id,
        classroom_id=scope.classroom.id,
        subject_id=scope.subject.id,
        attendance_date=date(2026, 7, 9),
    )
    assert record is not None
    assert record.marked_by_user_id == scope.teacher_user.id
    assert record.marked_by_user_id != scope.admin_user.id


# --- 18/19: rollback behavior ---------------------------------------------------


async def test_forced_repository_failure_midway_rolls_back_complete_batch(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    scope = await _seed_basic(db_session, suffix="mid-fail")
    service = AttendanceService(db_session)
    original_create = service._attendance.create
    calls = {"n": 0}

    async def flaky_create(**kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated repository failure")
        return await original_create(**kwargs)

    monkeypatch.setattr(service._attendance, "create", flaky_create)

    on = date(2026, 7, 10)
    classroom_id = scope.classroom.id
    subject_id = scope.subject.id
    payload = BulkAttendanceRequest(
        classroom_id=classroom_id,
        subject_id=subject_id,
        attendance_date=on,
        records=[
            BulkAttendanceRecordIn(
                student_profile_id=scope.student_a.id, status=AttendanceStatus.PRESENT
            ),
            BulkAttendanceRecordIn(
                student_profile_id=scope.student_b.id, status=AttendanceStatus.ABSENT
            ),
        ],
    )
    with pytest.raises(RuntimeError, match="simulated repository failure"):
        await service.bulk_save(current_user=scope.admin_user, payload=payload)

    assert calls["n"] == 2
    assert (
        await _attendance_count(db_session, classroom_id=classroom_id, subject_id=subject_id, on=on)
        == 0
    )


async def test_invalid_later_student_leaves_zero_partial_writes(db_session: AsyncSession) -> None:
    scope = await _seed_basic(db_session, suffix="later-invalid")
    service = AttendanceService(db_session)
    on = date(2026, 7, 11)
    classroom_id = scope.classroom.id
    subject_id = scope.subject.id
    payload = BulkAttendanceRequest(
        classroom_id=classroom_id,
        subject_id=subject_id,
        attendance_date=on,
        records=[
            BulkAttendanceRecordIn(
                student_profile_id=scope.student_a.id, status=AttendanceStatus.PRESENT
            ),
            BulkAttendanceRecordIn(student_profile_id=uuid.uuid4(), status=AttendanceStatus.ABSENT),
        ],
    )
    with pytest.raises(AttendanceStudentNotFoundError):
        await service.bulk_save(current_user=scope.admin_user, payload=payload)
    assert (
        await _attendance_count(db_session, classroom_id=classroom_id, subject_id=subject_id, on=on)
        == 0
    )


# --- 20/21/22/23: success-audit atomicity and content --------------------------


async def test_failed_success_audit_insertion_rolls_back_all_attendance_writes(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    scope = await _seed_basic(db_session, suffix="audit-fail")
    service = AttendanceService(db_session)

    async def failing_audit_create(**kwargs: object) -> object:
        raise RuntimeError("simulated audit write failure")

    monkeypatch.setattr(service._audit_logs, "create", failing_audit_create)

    on = date(2026, 7, 12)
    classroom_id = scope.classroom.id
    subject_id = scope.subject.id
    payload = _single_record_payload(scope, status=AttendanceStatus.PRESENT, attendance_date=on)
    with pytest.raises(RuntimeError, match="simulated audit write failure"):
        await service.bulk_save(current_user=scope.admin_user, payload=payload)

    assert (
        await _attendance_count(db_session, classroom_id=classroom_id, subject_id=subject_id, on=on)
        == 0
    )
    success_rows = await AuditLogRepository(db_session).list(
        outcome=AuditOutcome.SUCCESS, classroom_id=classroom_id, subject_id=subject_id
    )
    assert success_rows == []


async def test_failed_attendance_transaction_creates_no_success_audit(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    scope = await _seed_basic(db_session, suffix="no-audit-on-fail")
    service = AttendanceService(db_session)

    async def failing_create(**kwargs: object) -> object:
        raise RuntimeError("simulated repository failure")

    monkeypatch.setattr(service._attendance, "create", failing_create)

    on = date(2026, 7, 13)
    classroom_id = scope.classroom.id
    subject_id = scope.subject.id
    payload = _single_record_payload(scope, status=AttendanceStatus.PRESENT, attendance_date=on)
    with pytest.raises(RuntimeError, match="simulated repository failure"):
        await service.bulk_save(current_user=scope.admin_user, payload=payload)

    success_rows = await AuditLogRepository(db_session).list(
        outcome=AuditOutcome.SUCCESS, classroom_id=classroom_id, subject_id=subject_id
    )
    assert success_rows == []


async def test_successful_batch_creates_exactly_one_success_audit(db_session: AsyncSession) -> None:
    scope = await _seed_basic(db_session, suffix="one-audit")
    service = AttendanceService(db_session)
    payload = BulkAttendanceRequest(
        classroom_id=scope.classroom.id,
        subject_id=scope.subject.id,
        attendance_date=date(2026, 7, 14),
        records=[
            BulkAttendanceRecordIn(
                student_profile_id=scope.student_a.id, status=AttendanceStatus.PRESENT
            ),
            BulkAttendanceRecordIn(
                student_profile_id=scope.student_b.id, status=AttendanceStatus.ABSENT
            ),
        ],
    )
    await service.bulk_save(
        current_user=scope.admin_user, payload=payload, request_id="req-one-audit"
    )
    success_rows = await AuditLogRepository(db_session).list(
        outcome=AuditOutcome.SUCCESS, classroom_id=scope.classroom.id, subject_id=scope.subject.id
    )
    assert len(success_rows) == 1


async def test_success_audit_metadata_is_bounded_and_safe(db_session: AsyncSession) -> None:
    scope = await _seed_basic(db_session, suffix="audit-safe")
    service = AttendanceService(db_session)
    payload = _single_record_payload(
        scope,
        status=AttendanceStatus.ABSENT,
        attendance_date=date(2026, 7, 15),
        remarks="MEDICAL-NOTE-CONFIDENTIAL",
    )
    result = await service.bulk_save(
        current_user=scope.admin_user, payload=payload, request_id="req-audit-safe"
    )
    success_rows = await AuditLogRepository(db_session).list(
        outcome=AuditOutcome.SUCCESS, classroom_id=scope.classroom.id, subject_id=scope.subject.id
    )
    assert len(success_rows) == 1
    metadata = success_rows[0].event_metadata

    expected_keys = {
        "attendance_date",
        "created_count",
        "updated_count",
        "total_count",
        "record_ids",
        "record_ids_truncated",
    }
    assert set(metadata.keys()) == expected_keys
    assert metadata["record_ids"] == [str(record_id) for record_id in result.record_ids]
    assert metadata["record_ids_truncated"] is False

    serialized = str(metadata)
    assert "MEDICAL-NOTE-CONFIDENTIAL" not in serialized
    assert "password" not in serialized.lower()
    assert "token" not in serialized.lower()
    assert "authorization" not in serialized.lower()


# --- 24: role gate -------------------------------------------------------------


async def test_student_role_cannot_call_bulk_save(db_session: AsyncSession) -> None:
    scope = await _seed_basic(db_session, suffix="student-role")
    student_user, _ = await _create_student(
        db_session,
        email="svc-student-role@example.com",
        classroom_id=scope.classroom.id,
        roll_number="10",
    )
    service = AttendanceService(db_session)
    payload = _single_record_payload(scope, status=AttendanceStatus.PRESENT)
    with pytest.raises(AttendanceRoleNotPermittedError):
        await service.bulk_save(current_user=student_user, payload=payload)
