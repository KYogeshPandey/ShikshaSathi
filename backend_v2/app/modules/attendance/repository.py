"""Repositories for attendance core and the audit trail.

Follows the same conventions as ``app.modules.academics.repository``:
thin, single-aggregate data access; callers own the transaction boundary
(only ``flush()`` is called here, never ``commit()``); integrity errors
are translated into stable, named domain errors; no ORM relationship is
lazy-loaded under ``asyncpg`` (every cross-table read here is an explicit
``select(...).join(...)`` or a plain ``session.get()`` by primary key).

``AuditLogRepository`` deliberately has no ``update``/``delete`` method —
see ``app.modules.attendance.models.AuditLog``'s docstring and
``docs/adr/0010-phase4-attendance-and-audit-trail.md`` for the append-only
rationale.

Phase 4 Stage 3 extends ``AttendanceRepository`` with the read-side query
shapes the Stage 3 brief requires: an optional ``status`` filter (added to
the shared ``_apply_filters`` so ``list``/``count``/``aggregate_counts``
all support it uniformly), an exact daily-scope listing
(``list_daily``), two grouped-aggregation queries
(``aggregate_by_student``/``aggregate_by_classroom``, each a single
``GROUP BY`` query using the same ``FILTER (WHERE ...)`` technique as
``aggregate_counts`` — never an in-Python scan), and a CSV-export query
(``list_for_export``) that joins ``StudentProfile`` for ``roll_number``
only (classroom/subject codes are already known to the caller from the
exact-scope authorization check and are not re-joined per row). Every
new query method returns a typed ``dataclass``, never a raw SQLAlchemy
``Row``, per the Stage 3 brief's "no raw SQLAlchemy Row objects passed
directly to routers" instruction — enforced here at the repository
boundary so no caller (service or router) ever receives one.
"""

from __future__ import annotations

import builtins
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.attendance.errors import AttendanceRecordAlreadyExistsError
from app.modules.attendance.models import AttendanceRecord, AttendanceStatus, AuditLog, AuditOutcome
from app.modules.profiles.models import StudentProfile

_ATTENDANCE_UNIQUE_CONSTRAINT = "uq_attendance_records_student_classroom_subject_date"


@dataclass(frozen=True)
class StudentAttendanceAggregate:
    """One student's ``(total, present, absent)`` counts within a scope."""

    student_profile_id: uuid.UUID
    total_count: int
    present_count: int
    absent_count: int


@dataclass(frozen=True)
class ClassroomAttendanceAggregate:
    """One classroom's ``(total, present, absent)`` counts within a scope."""

    classroom_id: uuid.UUID
    total_count: int
    present_count: int
    absent_count: int


@dataclass(frozen=True)
class AttendanceExportRow:
    """One CSV-export row's attendance-side data.

    Deliberately does not carry ``classroom_code``/``subject_code`` —
    those are constant for a single export request (``classroom_id``/
    ``subject_id`` are required, exact-scope filters) and are already
    known to the caller from the authorization step, so they are not
    re-joined/re-fetched per row here.
    """

    attendance_date: date
    student_profile_id: uuid.UUID
    student_roll_number: str | None
    status: AttendanceStatus
    remarks: str | None
    marked_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


def _matches_constraint(exc: IntegrityError, constraint_name: str) -> bool:
    """Best-effort extraction of the violated constraint's name.

    Same pattern as ``app.modules.academics.repository._matches_constraint``:
    check the driver exception's ``constraint_name`` attribute first, then
    fall back to matching the constraint name inside the stringified
    original exception (stable across asyncpg adapter patch versions).
    """
    candidates = (
        exc.orig,
        getattr(exc.orig, "__cause__", None),
        getattr(exc.orig, "__context__", None),
    )
    for candidate in candidates:
        name = getattr(candidate, "constraint_name", None)
        if name:
            return str(name) == constraint_name
    return constraint_name in str(exc.orig)


class AttendanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, record_id: uuid.UUID) -> AttendanceRecord | None:
        return await self._session.get(AttendanceRecord, record_id)

    async def get_by_unique_key(
        self,
        *,
        student_profile_id: uuid.UUID,
        classroom_id: uuid.UUID,
        subject_id: uuid.UUID,
        attendance_date: date,
    ) -> AttendanceRecord | None:
        stmt = select(AttendanceRecord).where(
            AttendanceRecord.student_profile_id == student_profile_id,
            AttendanceRecord.classroom_id == classroom_id,
            AttendanceRecord.subject_id == subject_id,
            AttendanceRecord.attendance_date == attendance_date,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    def _apply_filters(
        self,
        stmt: Any,
        *,
        classroom_id: uuid.UUID | None,
        subject_id: uuid.UUID | None,
        student_profile_id: uuid.UUID | None,
        date_from: date | None,
        date_to: date | None,
        status: AttendanceStatus | None = None,
    ) -> Any:
        if classroom_id is not None:
            stmt = stmt.where(AttendanceRecord.classroom_id == classroom_id)
        if subject_id is not None:
            stmt = stmt.where(AttendanceRecord.subject_id == subject_id)
        if student_profile_id is not None:
            stmt = stmt.where(AttendanceRecord.student_profile_id == student_profile_id)
        if date_from is not None:
            stmt = stmt.where(AttendanceRecord.attendance_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(AttendanceRecord.attendance_date <= date_to)
        if status is not None:
            stmt = stmt.where(AttendanceRecord.status == status)
        return stmt

    async def list(
        self,
        *,
        classroom_id: uuid.UUID | None = None,
        subject_id: uuid.UUID | None = None,
        student_profile_id: uuid.UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        status: AttendanceStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[AttendanceRecord]:
        """Deterministically ordered, filtered, paginated attendance rows."""
        stmt = select(AttendanceRecord)
        stmt = self._apply_filters(
            stmt,
            classroom_id=classroom_id,
            subject_id=subject_id,
            student_profile_id=student_profile_id,
            date_from=date_from,
            date_to=date_to,
            status=status,
        )
        stmt = (
            stmt.order_by(
                AttendanceRecord.attendance_date,
                AttendanceRecord.classroom_id,
                AttendanceRecord.subject_id,
                AttendanceRecord.student_profile_id,
                AttendanceRecord.id,
            )
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(
        self,
        *,
        classroom_id: uuid.UUID | None = None,
        subject_id: uuid.UUID | None = None,
        student_profile_id: uuid.UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        status: AttendanceStatus | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(AttendanceRecord)
        stmt = self._apply_filters(
            stmt,
            classroom_id=classroom_id,
            subject_id=subject_id,
            student_profile_id=student_profile_id,
            date_from=date_from,
            date_to=date_to,
            status=status,
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def list_daily(
        self,
        *,
        classroom_id: uuid.UUID,
        subject_id: uuid.UUID,
        attendance_date: date,
    ) -> builtins.list[AttendanceRecord]:
        """The exact-scope daily attendance list: one classroom/subject/date.

        Deterministically ordered by ``student_profile_id`` then ``id`` —
        the same tie-breaker convention as ``list``. Returns an empty list
        (never an error) when no attendance has been marked yet for this
        scope; the router's response schema represents this as a typed
        empty result, per the Stage 3 brief's "return a typed empty
        result when no attendance exists" instruction.
        """
        stmt = (
            select(AttendanceRecord)
            .where(
                AttendanceRecord.classroom_id == classroom_id,
                AttendanceRecord.subject_id == subject_id,
                AttendanceRecord.attendance_date == attendance_date,
            )
            .order_by(AttendanceRecord.student_profile_id, AttendanceRecord.id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def aggregate_counts(
        self,
        *,
        classroom_id: uuid.UUID | None = None,
        subject_id: uuid.UUID | None = None,
        student_profile_id: uuid.UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        status: AttendanceStatus | None = None,
    ) -> tuple[int, int, int]:
        """Return ``(total, present_count, absent_count)`` for the given filters.

        Uses a single-pass query with ``FILTER (WHERE ...)`` aggregates
        (PostgreSQL / SQLAlchemy ``FunctionElement.filter``) rather than
        three separate queries or fetching every row into Python.
        """
        stmt = select(
            func.count().label("total"),
            func.count()
            .filter(AttendanceRecord.status == AttendanceStatus.PRESENT)
            .label("present_count"),
            func.count()
            .filter(AttendanceRecord.status == AttendanceStatus.ABSENT)
            .label("absent_count"),
        ).select_from(AttendanceRecord)
        stmt = self._apply_filters(
            stmt,
            classroom_id=classroom_id,
            subject_id=subject_id,
            student_profile_id=student_profile_id,
            date_from=date_from,
            date_to=date_to,
            status=status,
        )
        row = (await self._session.execute(stmt)).one()
        return int(row.total), int(row.present_count), int(row.absent_count)

    async def aggregate_by_student(
        self,
        *,
        classroom_id: uuid.UUID | None = None,
        subject_id: uuid.UUID | None = None,
        student_profile_id: uuid.UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        status: AttendanceStatus | None = None,
    ) -> builtins.list[StudentAttendanceAggregate]:
        """Per-student ``(total, present, absent)`` counts, one ``GROUP BY`` query.

        Deterministically ordered by ``student_profile_id``. Same
        ``FILTER (WHERE ...)`` aggregation technique as
        ``aggregate_counts`` — no in-Python scan over individual rows.
        """
        stmt = select(
            AttendanceRecord.student_profile_id,
            func.count().label("total"),
            func.count()
            .filter(AttendanceRecord.status == AttendanceStatus.PRESENT)
            .label("present_count"),
            func.count()
            .filter(AttendanceRecord.status == AttendanceStatus.ABSENT)
            .label("absent_count"),
        ).select_from(AttendanceRecord)
        stmt = self._apply_filters(
            stmt,
            classroom_id=classroom_id,
            subject_id=subject_id,
            student_profile_id=student_profile_id,
            date_from=date_from,
            date_to=date_to,
            status=status,
        )
        stmt = stmt.group_by(AttendanceRecord.student_profile_id).order_by(
            AttendanceRecord.student_profile_id
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            StudentAttendanceAggregate(
                student_profile_id=row.student_profile_id,
                total_count=int(row.total),
                present_count=int(row.present_count),
                absent_count=int(row.absent_count),
            )
            for row in rows
        ]

    async def aggregate_by_classroom(
        self,
        *,
        classroom_id: uuid.UUID | None = None,
        subject_id: uuid.UUID | None = None,
        student_profile_id: uuid.UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        status: AttendanceStatus | None = None,
    ) -> builtins.list[ClassroomAttendanceAggregate]:
        """Per-classroom ``(total, present, absent)`` counts, one ``GROUP BY`` query.

        Deterministically ordered by ``classroom_id``. Same aggregation
        technique as ``aggregate_counts``/``aggregate_by_student``.
        """
        stmt = select(
            AttendanceRecord.classroom_id,
            func.count().label("total"),
            func.count()
            .filter(AttendanceRecord.status == AttendanceStatus.PRESENT)
            .label("present_count"),
            func.count()
            .filter(AttendanceRecord.status == AttendanceStatus.ABSENT)
            .label("absent_count"),
        ).select_from(AttendanceRecord)
        stmt = self._apply_filters(
            stmt,
            classroom_id=classroom_id,
            subject_id=subject_id,
            student_profile_id=student_profile_id,
            date_from=date_from,
            date_to=date_to,
            status=status,
        )
        stmt = stmt.group_by(AttendanceRecord.classroom_id).order_by(AttendanceRecord.classroom_id)
        rows = (await self._session.execute(stmt)).all()
        return [
            ClassroomAttendanceAggregate(
                classroom_id=row.classroom_id,
                total_count=int(row.total),
                present_count=int(row.present_count),
                absent_count=int(row.absent_count),
            )
            for row in rows
        ]

    async def list_for_export(
        self,
        *,
        classroom_id: uuid.UUID | None = None,
        subject_id: uuid.UUID | None = None,
        student_profile_id: uuid.UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        status: AttendanceStatus | None = None,
    ) -> builtins.list[AttendanceExportRow]:
        """CSV-export rows: attendance fields plus the student's roll number.

        Joins ``StudentProfile`` for ``roll_number`` only —
        ``classroom_code``/``subject_code`` are constant for a single
        export request (exact-scope filters) and are attached by the
        caller from the already-authorized ``Classroom``/``Subject``,
        not re-fetched per row here. Deterministically ordered by
        ``attendance_date`` then ``student_profile_id`` then ``id``.
        """
        stmt = (
            select(
                AttendanceRecord.attendance_date,
                AttendanceRecord.student_profile_id,
                StudentProfile.roll_number,
                AttendanceRecord.status,
                AttendanceRecord.remarks,
                AttendanceRecord.marked_by_user_id,
                AttendanceRecord.created_at,
                AttendanceRecord.updated_at,
            )
            .select_from(AttendanceRecord)
            .join(StudentProfile, StudentProfile.id == AttendanceRecord.student_profile_id)
        )
        stmt = self._apply_filters(
            stmt,
            classroom_id=classroom_id,
            subject_id=subject_id,
            student_profile_id=student_profile_id,
            date_from=date_from,
            date_to=date_to,
            status=status,
        )
        stmt = stmt.order_by(
            AttendanceRecord.attendance_date,
            AttendanceRecord.student_profile_id,
            AttendanceRecord.id,
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            AttendanceExportRow(
                attendance_date=row.attendance_date,
                student_profile_id=row.student_profile_id,
                student_roll_number=row.roll_number,
                status=row.status,
                remarks=row.remarks,
                marked_by_user_id=row.marked_by_user_id,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    async def create(
        self,
        *,
        student_profile_id: uuid.UUID,
        classroom_id: uuid.UUID,
        subject_id: uuid.UUID,
        attendance_date: date,
        status: AttendanceStatus,
        marked_by_user_id: uuid.UUID,
        remarks: str | None = None,
    ) -> AttendanceRecord:
        """Create one attendance row.

        Raises ``AttendanceRecordAlreadyExistsError`` on a duplicate
        (student, classroom, subject, date) — the database-level backstop
        described in that error's docstring. Any other integrity failure
        (e.g. a foreign-key violation from a since-deleted reference) is
        left to propagate unchanged; Stage 2's service layer is
        responsible for validating references before ever calling this.
        """
        record = AttendanceRecord(
            student_profile_id=student_profile_id,
            classroom_id=classroom_id,
            subject_id=subject_id,
            attendance_date=attendance_date,
            status=status,
            remarks=remarks,
            marked_by_user_id=marked_by_user_id,
        )
        self._session.add(record)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            if _matches_constraint(exc, _ATTENDANCE_UNIQUE_CONSTRAINT):
                raise AttendanceRecordAlreadyExistsError() from exc
            raise
        await self._session.refresh(record)
        return record

    async def update(
        self,
        record: AttendanceRecord,
        *,
        status: AttendanceStatus,
        marked_by_user_id: uuid.UUID,
        remarks: str | None = None,
    ) -> AttendanceRecord:
        """Update an existing attendance row's status/remarks/marked-by.

        Always re-stamps ``marked_by_user_id`` from the authenticated
        actor performing the change (never trusted from client input at
        the service layer) — this repository method simply persists
        whatever the caller supplies.
        """
        record.status = status
        record.remarks = remarks
        record.marked_by_user_id = marked_by_user_id
        await self._session.flush()
        await self._session.refresh(record)
        return record


class AuditLogRepository:
    """Append-only audit-log data access.

    Deliberately has no ``update``/``delete`` method — see
    ``app.modules.attendance.models.AuditLog``'s docstring.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, audit_log_id: uuid.UUID) -> AuditLog | None:
        return await self._session.get(AuditLog, audit_log_id)

    def _apply_filters(
        self,
        stmt: Any,
        *,
        actor_user_id: uuid.UUID | None,
        action: str | None,
        outcome: AuditOutcome | None,
        entity_type: str | None,
        classroom_id: uuid.UUID | None,
        subject_id: uuid.UUID | None,
        date_from: date | None,
        date_to: date | None,
    ) -> Any:
        if actor_user_id is not None:
            stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
        if action is not None:
            stmt = stmt.where(AuditLog.action == action)
        if outcome is not None:
            stmt = stmt.where(AuditLog.outcome == outcome)
        if entity_type is not None:
            stmt = stmt.where(AuditLog.entity_type == entity_type)
        if classroom_id is not None:
            stmt = stmt.where(AuditLog.classroom_id == classroom_id)
        if subject_id is not None:
            stmt = stmt.where(AuditLog.subject_id == subject_id)
        if date_from is not None:
            stmt = stmt.where(func.date(AuditLog.created_at) >= date_from)
        if date_to is not None:
            stmt = stmt.where(func.date(AuditLog.created_at) <= date_to)
        return stmt

    async def list(
        self,
        *,
        actor_user_id: uuid.UUID | None = None,
        action: str | None = None,
        outcome: AuditOutcome | None = None,
        entity_type: str | None = None,
        classroom_id: uuid.UUID | None = None,
        subject_id: uuid.UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[AuditLog]:
        stmt = select(AuditLog)
        stmt = self._apply_filters(
            stmt,
            actor_user_id=actor_user_id,
            action=action,
            outcome=outcome,
            entity_type=entity_type,
            classroom_id=classroom_id,
            subject_id=subject_id,
            date_from=date_from,
            date_to=date_to,
        )
        stmt = stmt.order_by(AuditLog.created_at.desc(), AuditLog.id).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(
        self,
        *,
        actor_user_id: uuid.UUID | None = None,
        action: str | None = None,
        outcome: AuditOutcome | None = None,
        entity_type: str | None = None,
        classroom_id: uuid.UUID | None = None,
        subject_id: uuid.UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(AuditLog)
        stmt = self._apply_filters(
            stmt,
            actor_user_id=actor_user_id,
            action=action,
            outcome=outcome,
            entity_type=entity_type,
            classroom_id=classroom_id,
            subject_id=subject_id,
            date_from=date_from,
            date_to=date_to,
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def create(
        self,
        *,
        actor_user_id: uuid.UUID,
        action: str,
        outcome: AuditOutcome,
        entity_type: str,
        entity_id: uuid.UUID | None = None,
        classroom_id: uuid.UUID | None = None,
        subject_id: uuid.UUID | None = None,
        request_id: str | None = None,
        event_metadata: dict[str, object] | None = None,
    ) -> AuditLog:
        """Append one audit-log row. Never updates or deletes an existing row."""
        log = AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            outcome=outcome,
            entity_type=entity_type,
            entity_id=entity_id,
            classroom_id=classroom_id,
            subject_id=subject_id,
            request_id=request_id,
            event_metadata=event_metadata or {},
        )
        self._session.add(log)
        await self._session.flush()
        await self._session.refresh(log)
        return log
