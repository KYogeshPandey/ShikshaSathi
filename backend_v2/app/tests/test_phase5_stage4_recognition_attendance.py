"""Focused Phase 5 Stage 4 authorization, decision, attendance, and audit tests."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.attendance.models import AttendanceRecord, AttendanceStatus, AuditOutcome
from app.modules.attendance.repository import AuditLogRepository
from app.modules.attendance.service import AttendanceService
from app.modules.face_recognition.domain import MatchStatus
from app.modules.face_recognition.models import RecognitionAttendanceAttempt
from app.modules.face_recognition.recognition_attendance_service import (
    ACTION_RECOGNITION_ATTENDANCE_ATTEMPT,
    ACTION_RECOGNITION_ATTENDANCE_CONFIRMATION,
    ACTION_RECOGNITION_ATTENDANCE_DECISION,
    RecognitionAttendanceService,
    RecognitionConfirmationOutcome,
)
from app.modules.profiles.repository import StudentProfileRepository
from app.modules.users.models import UserRole
from app.tests.attendance_http_helpers import seed_attendance_scope
from app.tests.phase3_http_helpers import auth_headers, create_resource, seed_user
from app.tests.phase5_stage2_http_helpers import make_jpeg_bytes
from app.tests.phase5_stage3_helpers import (
    FakeFaceDetector,
    FakeFaceEmbedder,
    make_detected_face,
    make_unit_embedding_vector,
    patch_providers,
)
from app.tests.phase5_stage4_helpers import seed_processed_embedding_direct

_BASE = "/api/v1/face-recognition/attendance/attempts"
_ATTENDANCE_DATE = date(2026, 8, 16)


async def _post_attempt(
    client: AsyncClient,
    *,
    user,
    classroom_id: str,
    subject_id: str,
    image: bytes | None = None,
):
    return await client.post(
        _BASE,
        data={
            "classroom_id": classroom_id,
            "subject_id": subject_id,
            "attendance_date": _ATTENDANCE_DATE.isoformat(),
        },
        files={"file": ("probe.jpg", image or make_jpeg_bytes(), "image/jpeg")},
        headers=auth_headers(user),
    )


async def _attendance_rows(session: AsyncSession) -> list[AttendanceRecord]:
    result = await session.execute(select(AttendanceRecord).order_by(AttendanceRecord.id))
    return list(result.scalars().all())


async def _attempt(session: AsyncSession, attempt_id: str) -> RecognitionAttendanceAttempt:
    attempt = await session.get(RecognitionAttendanceAttempt, uuid.UUID(attempt_id))
    assert attempt is not None
    return attempt


async def test_assigned_teacher_found_marks_via_scoped_attempt_and_retry_is_upsert(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="s4-found")
    student_id = uuid.UUID(scope["student_profile_1"]["id"])
    vector = make_unit_embedding_vector(seed=1.0)
    await seed_processed_embedding_direct(
        db_session,
        student_profile_id=student_id,
        created_by_user_id=scope["admin"].id,
        embedding_values=list(vector.values),
    )
    detector = FakeFaceDetector(results=[[make_detected_face()]])
    embedder = FakeFaceEmbedder(seed=1.0)

    with patch_providers(detector, embedder):
        first = await _post_attempt(
            client_db,
            user=scope["teacher"],
            classroom_id=scope["classroom"]["id"],
            subject_id=scope["subject"]["id"],
        )
        second = await _post_attempt(
            client_db,
            user=scope["teacher"],
            classroom_id=scope["classroom"]["id"],
            subject_id=scope["subject"]["id"],
        )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    body = first.json()
    assert body["decision"] == MatchStatus.FOUND.value
    assert body["matched_student_profile_id"] == str(student_id)
    assert body["requires_confirmation"] is False
    assert set(body) == {
        "attempt_id",
        "classroom_id",
        "subject_id",
        "attendance_date",
        "decision",
        "matched_student_profile_id",
        "attendance_record_id",
        "requires_confirmation",
    }
    assert "embedding" not in first.text.lower()
    assert "image" not in first.text.lower()
    assert "model" not in first.text.lower()

    rows = await _attendance_rows(db_session)
    assert len(rows) == 1
    assert rows[0].student_profile_id == student_id
    assert rows[0].classroom_id == uuid.UUID(scope["classroom"]["id"])
    assert rows[0].subject_id == uuid.UUID(scope["subject"]["id"])
    assert rows[0].attendance_date == _ATTENDANCE_DATE
    assert rows[0].status is AttendanceStatus.PRESENT
    assert rows[0].marked_by_user_id == scope["teacher"].id

    persisted = await _attempt(db_session, body["attempt_id"])
    assert persisted.candidate_count == 2
    assert set(persisted.candidate_student_profile_ids) == {
        uuid.UUID(scope["student_profile_1"]["id"]),
        uuid.UUID(scope["student_profile_2"]["id"]),
    }

    audits = await AuditLogRepository(db_session).list(
        action=ACTION_RECOGNITION_ATTENDANCE_DECISION,
        outcome=AuditOutcome.SUCCESS,
        limit=10,
    )
    assert len(audits) == 2
    assert set(audits[0].event_metadata) == {
        "recognition_attempt_id",
        "recognition_decision",
        "matched_student_profile_id",
        "candidate_count",
    }
    assert audits[0].event_metadata["recognition_decision"] == MatchStatus.FOUND.value


async def test_unrelated_teacher_is_concealed_audited_and_runs_no_inference(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="s4-block")
    other_teacher_id = scope["other_teacher"].id
    with patch("app.modules.face_recognition.router._validate_and_embed_probe_sync") as inference:
        response = await _post_attempt(
            client_db,
            user=scope["other_teacher"],
            classroom_id=scope["classroom"]["id"],
            subject_id=scope["subject"]["id"],
            image=b"not-even-an-image",
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ATTENDANCE_SCOPE_NOT_FOUND"
    inference.assert_not_called()
    assert await _attendance_rows(db_session) == []
    audits = await AuditLogRepository(db_session).list(
        actor_user_id=other_teacher_id,
        action=ACTION_RECOGNITION_ATTENDANCE_ATTEMPT,
        outcome=AuditOutcome.BLOCKED,
        limit=10,
    )
    assert len(audits) == 1
    assert set(audits[0].event_metadata) == {"reason_code", "attempted_action"}


async def test_persisted_found_attendance_failure_then_retry_converges_without_duplicate(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="s5-found-retry")
    student_id = uuid.UUID(scope["student_profile_1"]["id"])
    vector = make_unit_embedding_vector(seed=12.0)
    await seed_processed_embedding_direct(
        db_session,
        student_profile_id=student_id,
        created_by_user_id=scope["admin"].id,
        embedding_values=list(vector.values),
    )
    detector = FakeFaceDetector(results=[[make_detected_face()]])
    embedder = FakeFaceEmbedder(seed=12.0)

    async def _fail_attendance(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated attendance transaction failure")

    with patch_providers(detector, embedder):
        with (
            patch.object(AttendanceService, "bulk_save", new=_fail_attendance),
            pytest.raises(RuntimeError, match="simulated attendance transaction failure"),
        ):
            await _post_attempt(
                client_db,
                user=scope["teacher"],
                classroom_id=scope["classroom"]["id"],
                subject_id=scope["subject"]["id"],
            )

        persisted_after_failure = list(
            (
                await db_session.execute(
                    select(RecognitionAttendanceAttempt).order_by(
                        RecognitionAttendanceAttempt.created_at
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(persisted_after_failure) == 1
        assert persisted_after_failure[0].decision is MatchStatus.FOUND
        assert persisted_after_failure[0].attendance_record_id is None
        assert await _attendance_rows(db_session) == []

        retry = await _post_attempt(
            client_db,
            user=scope["teacher"],
            classroom_id=scope["classroom"]["id"],
            subject_id=scope["subject"]["id"],
        )

    assert retry.status_code == 200, retry.text
    assert retry.json()["decision"] == MatchStatus.FOUND.value
    attendance_rows = await _attendance_rows(db_session)
    assert len(attendance_rows) == 1
    assert attendance_rows[0].student_profile_id == student_id

    all_attempts = list(
        (
            await db_session.execute(
                select(RecognitionAttendanceAttempt).order_by(
                    RecognitionAttendanceAttempt.created_at
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(all_attempts) == 2
    assert sum(attempt.attendance_record_id is None for attempt in all_attempts) == 1
    assert sum(attempt.attendance_record_id is not None for attempt in all_attempts) == 1


async def test_roster_is_server_derived_active_classroom_only_without_global_fallback(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="s4-roster")
    inactive_id = uuid.UUID(scope["student_profile_2"]["id"])
    inactive = await StudentProfileRepository(db_session).get_by_id(inactive_id)
    assert inactive is not None
    await StudentProfileRepository(db_session).deactivate(inactive)
    await db_session.commit()

    other_classroom = await create_resource(
        client_db,
        path="/api/v1/classrooms",
        payload={"name": "Other Stage4 Room", "code": "s4-other-room"},
        user=scope["admin"],
    )
    other_student = await seed_user(
        db_session, email="s4-roster-other@example.com", role=UserRole.STUDENT
    )
    other_profile = await create_resource(
        client_db,
        path="/api/v1/student-profiles",
        payload={
            "user_id": str(other_student.id),
            "classroom_id": other_classroom["id"],
            "roll_number": "99",
        },
        user=scope["admin"],
    )

    detector = FakeFaceDetector(results=[[make_detected_face()]])
    embedder = FakeFaceEmbedder(seed=1.0)
    with patch_providers(detector, embedder):
        response = await _post_attempt(
            client_db,
            user=scope["teacher"],
            classroom_id=scope["classroom"]["id"],
            subject_id=scope["subject"]["id"],
        )

    assert response.status_code == 200, response.text
    assert response.json()["decision"] == MatchStatus.UNKNOWN.value
    persisted = await _attempt(db_session, response.json()["attempt_id"])
    assert persisted.candidate_student_profile_ids == [uuid.UUID(scope["student_profile_1"]["id"])]
    assert inactive_id not in persisted.candidate_student_profile_ids
    assert uuid.UUID(other_profile["id"]) not in persisted.candidate_student_profile_ids


async def test_unknown_writes_nothing_until_idempotent_explicit_confirmation(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="s4-unknown")
    detector = FakeFaceDetector(results=[[make_detected_face()]])
    embedder = FakeFaceEmbedder(seed=1.0)
    with patch_providers(detector, embedder):
        response = await _post_attempt(
            client_db,
            user=scope["teacher"],
            classroom_id=scope["classroom"]["id"],
            subject_id=scope["subject"]["id"],
        )

    assert response.status_code == 200, response.text
    assert response.json()["decision"] == MatchStatus.UNKNOWN.value
    assert response.json()["requires_confirmation"] is True
    assert await _attendance_rows(db_session) == []

    student_id = scope["student_profile_1"]["id"]
    url = f"{_BASE}/{response.json()['attempt_id']}/confirm"
    first = await client_db.post(
        url,
        json={"student_profile_id": student_id},
        headers=auth_headers(scope["teacher"]),
    )
    second = await client_db.post(
        url,
        json={"student_profile_id": student_id},
        headers=auth_headers(scope["teacher"]),
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json() == second.json()
    assert len(await _attendance_rows(db_session)) == 1

    conflicting = await client_db.post(
        url,
        json={"student_profile_id": scope["student_profile_2"]["id"]},
        headers=auth_headers(scope["teacher"]),
    )
    assert conflicting.status_code == 409
    assert conflicting.json()["error"]["code"] == "RECOGNITION_ATTENDANCE_CONFIRMATION_CONFLICT"
    assert len(await _attendance_rows(db_session)) == 1

    decision_audits = await AuditLogRepository(db_session).list(
        action=ACTION_RECOGNITION_ATTENDANCE_DECISION, limit=10
    )
    assert len(decision_audits) == 1
    assert decision_audits[0].event_metadata["recognition_decision"] == "unknown"
    confirmation_audits = await AuditLogRepository(db_session).list(
        action=ACTION_RECOGNITION_ATTENDANCE_CONFIRMATION,
        outcome=AuditOutcome.SUCCESS,
        limit=10,
    )
    assert len(confirmation_audits) == 1
    assert set(confirmation_audits[0].event_metadata) == {
        "recognition_attempt_id",
        "recognition_decision",
        "confirmed_student_profile_id",
    }


async def test_ambiguous_never_auto_writes_and_confirmation_requires_roster_student(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="s4-ambiguous")
    vector = make_unit_embedding_vector(seed=7.0)
    for profile_key in ("student_profile_1", "student_profile_2"):
        await seed_processed_embedding_direct(
            db_session,
            student_profile_id=uuid.UUID(scope[profile_key]["id"]),
            created_by_user_id=scope["admin"].id,
            embedding_values=list(vector.values),
        )
    detector = FakeFaceDetector(results=[[make_detected_face()]])
    embedder = FakeFaceEmbedder(seed=7.0)
    with patch_providers(detector, embedder):
        response = await _post_attempt(
            client_db,
            user=scope["teacher"],
            classroom_id=scope["classroom"]["id"],
            subject_id=scope["subject"]["id"],
        )

    assert response.status_code == 200, response.text
    assert response.json()["decision"] == MatchStatus.AMBIGUOUS.value
    assert response.json()["matched_student_profile_id"] is None
    assert await _attendance_rows(db_session) == []

    other_scope = await seed_attendance_scope(client_db, db_session, suffix="s4-cross")
    url = f"{_BASE}/{response.json()['attempt_id']}/confirm"
    rejected = await client_db.post(
        url,
        json={"student_profile_id": other_scope["student_profile_1"]["id"]},
        headers=auth_headers(scope["teacher"]),
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "RECOGNITION_ATTENDANCE_STUDENT_NOT_IN_ROSTER"
    assert await _attendance_rows(db_session) == []

    accepted = await client_db.post(
        url,
        json={"student_profile_id": scope["student_profile_2"]["id"]},
        headers=auth_headers(scope["teacher"]),
    )
    assert accepted.status_code == 200, accepted.text
    assert len(await _attendance_rows(db_session)) == 1

    blocked = await AuditLogRepository(db_session).list(
        action=ACTION_RECOGNITION_ATTENDANCE_CONFIRMATION,
        outcome=AuditOutcome.BLOCKED,
        limit=10,
    )
    assert len(blocked) == 1
    assert blocked[0].event_metadata["reason_code"] == "student_not_in_authorized_roster"
    all_stage4_audits = await AuditLogRepository(db_session).list(limit=100)
    for audit in all_stage4_audits:
        if not audit.action.startswith("face_recognition.attendance_"):
            continue
        serialized = str(audit.event_metadata).lower()
        for forbidden in ("embedding", "image", "pixel", "model_path", "traceback", "secret"):
            assert forbidden not in serialized


async def test_concurrent_same_confirmation_is_serialized_by_attempt_row_lock(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope = await seed_attendance_scope(client_db, db_session, suffix="s5-confirm-lock")
    detector = FakeFaceDetector(results=[[make_detected_face()]])
    embedder = FakeFaceEmbedder(seed=18.0)
    with patch_providers(detector, embedder):
        response = await _post_attempt(
            client_db,
            user=scope["teacher"],
            classroom_id=scope["classroom"]["id"],
            subject_id=scope["subject"]["id"],
        )
    assert response.status_code == 200, response.text
    assert response.json()["decision"] == MatchStatus.UNKNOWN.value

    attempt_id = uuid.UUID(response.json()["attempt_id"])
    student_id = uuid.UUID(scope["student_profile_1"]["id"])
    teacher = scope["teacher"]
    bind = db_session.bind
    assert isinstance(bind, AsyncEngine)
    session_factory = async_sessionmaker(bind=bind, expire_on_commit=False, autoflush=False)

    async def _confirm_once() -> RecognitionConfirmationOutcome:
        async with session_factory() as session:
            return await RecognitionAttendanceService(session).confirm_attempt(
                current_user=teacher,
                attempt_id=attempt_id,
                student_profile_id=student_id,
                request_id="stage5-concurrent-confirmation",
            )

    first, second = await asyncio.wait_for(
        asyncio.gather(_confirm_once(), _confirm_once()), timeout=15
    )
    assert first == second
    attendance_rows = await _attendance_rows(db_session)
    assert len(attendance_rows) == 1
    assert attendance_rows[0].id == first.attendance_record_id

    persisted = await _attempt(db_session, str(attempt_id))
    assert persisted.confirmed_student_profile_id == student_id
    assert persisted.attendance_record_id == first.attendance_record_id
    confirmation_audits = await AuditLogRepository(db_session).list(
        action=ACTION_RECOGNITION_ATTENDANCE_CONFIRMATION,
        outcome=AuditOutcome.SUCCESS,
        limit=10,
    )
    assert len(confirmation_audits) == 1
