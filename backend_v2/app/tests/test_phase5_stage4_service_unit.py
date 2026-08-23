"""DB-independent branch tests for Stage 4 orchestration.

The PostgreSQL tests remain the authoritative persistence coverage. These
tests keep FOUND/UNKNOWN/AMBIGUOUS and confirmation safety executable in an
environment where PostgreSQL itself is unavailable.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.modules.attendance.models import AttendanceStatus
from app.modules.face_recognition.domain import EmbeddingVector, MatchStatus
from app.modules.face_recognition.errors import RecognitionAttendanceStudentNotInRosterError
from app.modules.face_recognition.matching_service import MatchOutcome
from app.modules.face_recognition.recognition_attendance_service import (
    AuthorizedRecognitionScope,
    RecognitionAttendanceService,
)
from app.modules.users.models import UserRole


@asynccontextmanager
async def _transaction(_session):
    yield


def _service() -> RecognitionAttendanceService:
    service = object.__new__(RecognitionAttendanceService)
    service._session = object()
    service._settings = SimpleNamespace(FACE_EMBEDDING_DIMENSION=2)
    service._attempts = SimpleNamespace(
        create=AsyncMock(),
        get_by_id=AsyncMock(),
        set_attendance_record=AsyncMock(),
        confirm=AsyncMock(),
    )
    service._audit_logs = SimpleNamespace(create=AsyncMock())
    service._students = SimpleNamespace(list_by_classroom=AsyncMock())
    return service


def _user():
    return SimpleNamespace(id=uuid.uuid4(), role=UserRole.TEACHER)


def _scope(*student_ids: uuid.UUID) -> AuthorizedRecognitionScope:
    return AuthorizedRecognitionScope(
        classroom_id=uuid.uuid4(),
        subject_id=uuid.uuid4(),
        attendance_date=date(2026, 8, 16),
        candidate_student_profile_ids=student_ids,
    )


@pytest.mark.parametrize("decision", [MatchStatus.UNKNOWN, MatchStatus.AMBIGUOUS])
async def test_unknown_and_ambiguous_persist_decision_but_never_mark(decision: MatchStatus) -> None:
    service = _service()
    actor = _user()
    student_id = uuid.uuid4()
    scope = _scope(student_id)
    attempt = SimpleNamespace(id=uuid.uuid4())
    service._attempts.create.return_value = attempt
    service._mark_present = AsyncMock()
    matching = SimpleNamespace(
        match_probe=AsyncMock(
            return_value=MatchOutcome(
                status=decision,
                matched_student_profile_id=None,
                best_similarity=None,
                runner_up_similarity=None,
            )
        )
    )

    with (
        patch(
            "app.modules.face_recognition.recognition_attendance_service.service_transaction",
            _transaction,
        ),
        patch(
            "app.modules.face_recognition.recognition_attendance_service.MatchingService",
            return_value=matching,
        ),
    ):
        result = await service.create_attempt(
            current_user=actor,
            scope=scope,
            probe_embedding=EmbeddingVector(values=(1.0, 0.0)),
        )

    assert result.decision is decision
    service._mark_present.assert_not_awaited()
    assert service._attempts.create.await_args.kwargs["candidate_student_profile_ids"] == [
        student_id
    ]
    metadata = service._audit_logs.create.await_args.kwargs["event_metadata"]
    assert metadata["recognition_decision"] == decision.value
    assert set(metadata) == {
        "recognition_attempt_id",
        "recognition_decision",
        "matched_student_profile_id",
        "candidate_count",
    }


async def test_found_is_only_a_proposal_until_explicit_confirmation() -> None:
    service = _service()
    actor = _user()
    matched_id = uuid.uuid4()
    scope = _scope(matched_id)
    attempt = SimpleNamespace(id=uuid.uuid4())
    service._attempts.create.return_value = attempt
    service._mark_present = AsyncMock()
    matching = SimpleNamespace(
        match_probe=AsyncMock(
            return_value=MatchOutcome(
                status=MatchStatus.FOUND,
                matched_student_profile_id=matched_id,
                best_similarity=1.0,
                runner_up_similarity=None,
            )
        )
    )

    with (
        patch(
            "app.modules.face_recognition.recognition_attendance_service.service_transaction",
            _transaction,
        ),
        patch(
            "app.modules.face_recognition.recognition_attendance_service.MatchingService",
            return_value=matching,
        ),
    ):
        result = await service.create_attempt(
            current_user=actor,
            scope=scope,
            probe_embedding=EmbeddingVector(values=(1.0, 0.0)),
            request_id="stage4-found",
        )

    assert result.attendance_record_id is None
    service._mark_present.assert_not_awaited()
    service._attempts.set_attendance_record.assert_not_awaited()


async def test_mark_present_constructs_one_present_row_through_attendance_service() -> None:
    service = _service()
    actor = _user()
    attendance_id = uuid.uuid4()
    attendance_service = SimpleNamespace(
        bulk_save=AsyncMock(return_value=SimpleNamespace(record_ids=[attendance_id]))
    )
    classroom_id = uuid.uuid4()
    subject_id = uuid.uuid4()
    student_id = uuid.uuid4()

    with patch(
        "app.modules.face_recognition.recognition_attendance_service.AttendanceService",
        return_value=attendance_service,
    ) as attendance_service_type:
        result = await service._mark_present(
            session=service._session,
            current_user=actor,
            classroom_id=classroom_id,
            subject_id=subject_id,
            attendance_date=date(2026, 8, 16),
            student_profile_id=student_id,
            request_id="stage4-boundary",
        )

    assert result == attendance_id
    attendance_service_type.assert_called_once_with(service._session)
    payload = attendance_service.bulk_save.await_args.kwargs["payload"]
    assert payload.classroom_id == classroom_id
    assert payload.subject_id == subject_id
    assert payload.attendance_date == date(2026, 8, 16)
    assert len(payload.records) == 1
    assert payload.records[0].student_profile_id == student_id
    assert payload.records[0].status is AttendanceStatus.PRESENT


async def test_confirmation_rejects_student_outside_original_roster_without_marking() -> None:
    service = _service()
    actor = _user()
    roster_student = uuid.uuid4()
    selected_student = uuid.uuid4()
    attempt = SimpleNamespace(
        id=uuid.uuid4(),
        classroom_id=uuid.uuid4(),
        subject_id=uuid.uuid4(),
        attendance_date=date(2026, 8, 16),
        decision=MatchStatus.UNKNOWN,
        candidate_student_profile_ids=[roster_student],
        confirmed_student_profile_id=None,
        attendance_record_id=None,
    )
    service._attempts.get_by_id.return_value = attempt
    service._students.list_by_classroom.return_value = [
        SimpleNamespace(id=roster_student, is_active=True),
        SimpleNamespace(id=selected_student, is_active=True),
    ]
    service._audit_invalid_confirmation = AsyncMock()
    service._mark_present = AsyncMock()
    authorization = SimpleNamespace(authorize_scope=AsyncMock())

    with (
        patch(
            "app.modules.face_recognition.recognition_attendance_service.service_transaction",
            _transaction,
        ),
        patch(
            "app.modules.face_recognition.recognition_attendance_service.AttendanceReadService",
            return_value=authorization,
        ),
        pytest.raises(RecognitionAttendanceStudentNotInRosterError),
    ):
        await service.confirm_attempt(
            current_user=actor,
            attempt_id=attempt.id,
            student_profile_id=selected_student,
        )

    authorization.authorize_scope.assert_awaited_once()
    service._mark_present.assert_not_awaited()
    service._audit_invalid_confirmation.assert_awaited_once()


async def test_repeated_same_confirmation_is_idempotent_without_second_mark() -> None:
    service = _service()
    actor = _user()
    student_id = uuid.uuid4()
    attendance_id = uuid.uuid4()
    attempt = SimpleNamespace(
        id=uuid.uuid4(),
        classroom_id=uuid.uuid4(),
        subject_id=uuid.uuid4(),
        attendance_date=date(2026, 8, 16),
        decision=MatchStatus.AMBIGUOUS,
        candidate_student_profile_ids=[student_id],
        confirmed_student_profile_id=student_id,
        attendance_record_id=attendance_id,
    )
    service._attempts.get_by_id.return_value = attempt
    service._students.list_by_classroom.return_value = [
        SimpleNamespace(id=student_id, is_active=True)
    ]
    service._mark_present = AsyncMock()
    authorization = SimpleNamespace(authorize_scope=AsyncMock())

    with (
        patch(
            "app.modules.face_recognition.recognition_attendance_service.service_transaction",
            _transaction,
        ),
        patch(
            "app.modules.face_recognition.recognition_attendance_service.AttendanceReadService",
            return_value=authorization,
        ),
    ):
        result = await service.confirm_attempt(
            current_user=actor,
            attempt_id=attempt.id,
            student_profile_id=student_id,
        )

    assert result.attendance_record_id == attendance_id
    service._mark_present.assert_not_awaited()
    service._attempts.confirm.assert_not_awaited()
