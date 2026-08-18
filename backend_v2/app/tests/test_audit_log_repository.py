"""Database-backed tests for ``app.modules.attendance.repository.AuditLogRepository``.

Uses the ``db_session`` fixture (app/tests/conftest.py); skips gracefully
if no reachable PostgreSQL test database is available.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.academics.repository import ClassroomRepository, SubjectRepository
from app.modules.attendance.models import AuditOutcome
from app.modules.attendance.repository import AuditLogRepository
from app.modules.auth.security import hash_password
from app.modules.users.models import UserRole
from app.modules.users.normalization import normalize_email
from app.modules.users.repository import UserRepository

_PASSWORD = "a-strong-real-password-1"


async def _create_user(session: AsyncSession, *, email: str, role: UserRole) -> uuid.UUID:
    user = await UserRepository(session).create(
        email=normalize_email(email),
        password_hash=hash_password(_PASSWORD),
        full_name=f"{role.value.title()} Audit Test",
        role=role,
        is_active=True,
    )
    await session.commit()
    return user.id


async def test_create_and_get_by_id_round_trips_metadata(db_session: AsyncSession) -> None:
    actor_id = await _create_user(
        db_session, email="audit-actor-1@example.com", role=UserRole.ADMIN
    )
    repo = AuditLogRepository(db_session)
    entry = await repo.create(
        actor_user_id=actor_id,
        action="attendance_bulk_mark",
        outcome=AuditOutcome.SUCCESS,
        entity_type="attendance_batch",
        request_id="req-abc-123",
        event_metadata={"created_count": 2, "updated_count": 0},
    )
    await db_session.commit()

    fetched = await repo.get_by_id(entry.id)
    assert fetched is not None
    assert fetched.actor_user_id == actor_id
    assert fetched.action == "attendance_bulk_mark"
    assert fetched.outcome is AuditOutcome.SUCCESS
    assert fetched.entity_type == "attendance_batch"
    assert fetched.request_id == "req-abc-123"
    assert fetched.event_metadata == {"created_count": 2, "updated_count": 0}


async def test_get_by_id_returns_none_for_unknown_id(db_session: AsyncSession) -> None:
    repo = AuditLogRepository(db_session)
    assert await repo.get_by_id(uuid.uuid4()) is None


async def test_create_defaults_event_metadata_to_empty_dict(db_session: AsyncSession) -> None:
    actor_id = await _create_user(
        db_session, email="audit-actor-2@example.com", role=UserRole.ADMIN
    )
    repo = AuditLogRepository(db_session)
    entry = await repo.create(
        actor_user_id=actor_id,
        action="attendance_detail_read",
        outcome=AuditOutcome.BLOCKED,
        entity_type="classroom",
    )
    await db_session.commit()

    fetched = await repo.get_by_id(entry.id)
    assert fetched is not None
    assert fetched.event_metadata == {}
    assert fetched.entity_id is None
    assert fetched.classroom_id is None
    assert fetched.subject_id is None
    assert fetched.request_id is None


async def test_list_is_deterministically_ordered_and_paginates(db_session: AsyncSession) -> None:
    actor_id = await _create_user(
        db_session, email="audit-actor-3@example.com", role=UserRole.ADMIN
    )
    repo = AuditLogRepository(db_session)
    created_ids = []
    for index in range(5):
        entry = await repo.create(
            actor_user_id=actor_id,
            action="attendance_bulk_mark",
            outcome=AuditOutcome.SUCCESS,
            entity_type="attendance_batch",
            event_metadata={"sequence": index},
        )
        created_ids.append(entry.id)
    await db_session.commit()

    page_one = await repo.list(actor_user_id=actor_id, limit=2, offset=0)
    page_two = await repo.list(actor_user_id=actor_id, limit=2, offset=2)
    page_three = await repo.list(actor_user_id=actor_id, limit=2, offset=4)

    all_ids = [row.id for row in (*page_one, *page_two, *page_three)]
    assert len(all_ids) == len(set(all_ids)) == 5

    # Re-running the same paginated query must return the exact same rows
    # in the exact same order (deterministic tie-break, not relying on
    # database-default ordering).
    page_one_again = await repo.list(actor_user_id=actor_id, limit=2, offset=0)
    assert [row.id for row in page_one] == [row.id for row in page_one_again]


async def test_list_filters_by_outcome_action_and_entity_type(db_session: AsyncSession) -> None:
    actor_id = await _create_user(
        db_session, email="audit-actor-4@example.com", role=UserRole.ADMIN
    )
    repo = AuditLogRepository(db_session)
    await repo.create(
        actor_user_id=actor_id,
        action="attendance_bulk_mark",
        outcome=AuditOutcome.SUCCESS,
        entity_type="attendance_batch",
    )
    blocked_entry = await repo.create(
        actor_user_id=actor_id,
        action="attendance_detail_read",
        outcome=AuditOutcome.BLOCKED,
        entity_type="classroom",
    )
    await db_session.commit()

    blocked_only = await repo.list(outcome=AuditOutcome.BLOCKED)
    assert {row.id for row in blocked_only} == {blocked_entry.id}

    by_entity_type = await repo.list(entity_type="classroom")
    assert {row.id for row in by_entity_type} == {blocked_entry.id}

    by_action = await repo.list(action="attendance_detail_read")
    assert {row.id for row in by_action} == {blocked_entry.id}


async def test_list_filters_by_classroom_and_subject(db_session: AsyncSession) -> None:
    actor_id = await _create_user(
        db_session, email="audit-actor-5@example.com", role=UserRole.ADMIN
    )
    classroom = await ClassroomRepository(db_session).create(
        name="Audit Classroom", code="audit-classroom"
    )
    subject = await SubjectRepository(db_session).create(name="Audit Subject", code="audit-subject")
    await db_session.commit()

    repo = AuditLogRepository(db_session)
    scoped_entry = await repo.create(
        actor_user_id=actor_id,
        action="attendance_bulk_mark",
        outcome=AuditOutcome.SUCCESS,
        entity_type="attendance_batch",
        classroom_id=classroom.id,
        subject_id=subject.id,
    )
    await repo.create(
        actor_user_id=actor_id,
        action="attendance_bulk_mark",
        outcome=AuditOutcome.SUCCESS,
        entity_type="attendance_batch",
    )
    await db_session.commit()

    by_classroom = await repo.list(classroom_id=classroom.id)
    assert {row.id for row in by_classroom} == {scoped_entry.id}
    by_subject = await repo.list(subject_id=subject.id)
    assert {row.id for row in by_subject} == {scoped_entry.id}


async def test_count_matches_list_filters(db_session: AsyncSession) -> None:
    actor_id = await _create_user(
        db_session, email="audit-actor-6@example.com", role=UserRole.ADMIN
    )
    repo = AuditLogRepository(db_session)
    for _ in range(3):
        await repo.create(
            actor_user_id=actor_id,
            action="attendance_bulk_mark",
            outcome=AuditOutcome.SUCCESS,
            entity_type="attendance_batch",
        )
    await db_session.commit()

    assert await repo.count(actor_user_id=actor_id) == 3
    assert await repo.count(actor_user_id=actor_id, outcome=AuditOutcome.BLOCKED) == 0


def test_audit_log_repository_has_no_update_or_delete_method() -> None:
    """Structural regression test for the append-only design.

    Asserts the append-only contract directly against the repository's
    public interface, not merely by omission in these tests: if an
    ``update``/``delete``/``patch``/``remove`` method is ever added to
    ``AuditLogRepository``, this test fails immediately.
    """
    public_methods = {
        name
        for name in dir(AuditLogRepository)
        if not name.startswith("_") and callable(getattr(AuditLogRepository, name))
    }
    forbidden = {"update", "delete", "patch", "remove", "edit"}
    assert public_methods.isdisjoint(forbidden)
    assert public_methods == {"create", "get_by_id", "list", "count"}


@pytest.mark.parametrize("outcome", list(AuditOutcome))
async def test_every_audit_outcome_value_can_be_persisted(
    db_session: AsyncSession, outcome: AuditOutcome
) -> None:
    actor_id = await _create_user(
        db_session, email=f"audit-outcome-{outcome.value}@example.com", role=UserRole.ADMIN
    )
    repo = AuditLogRepository(db_session)
    entry = await repo.create(
        actor_user_id=actor_id,
        action="attendance_bulk_mark",
        outcome=outcome,
        entity_type="attendance_batch",
    )
    await db_session.commit()

    fetched = await repo.get_by_id(entry.id)
    assert fetched is not None
    assert fetched.outcome is outcome
