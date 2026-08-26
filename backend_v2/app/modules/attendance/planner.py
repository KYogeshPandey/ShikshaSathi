"""Exact, deterministic attendance recovery mathematics and schedule expansion."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, time, timedelta
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction

from app.modules.attendance.calculations import attendance_percentage


class AttendancePlanStatus(StrEnum):
    SAFE = "safe"
    RECOVERY_POSSIBLE = "recovery_possible"
    TIGHT_RECOVERY = "tight_recovery"
    NOT_REACHABLE = "not_reachable"


class SubjectAttendanceStatus(StrEnum):
    SAFE = "safe"
    NEAR_TARGET = "near_target"
    RECOVERY_NEEDED = "recovery_needed"
    NO_HISTORY = "no_history"


@dataclass(frozen=True)
class TimetableSlot:
    timetable_entry_id: uuid.UUID
    subject_id: uuid.UUID
    weekday: int
    start_time: time


@dataclass(frozen=True)
class ScheduledClass:
    timetable_entry_id: uuid.UUID
    subject_id: uuid.UUID
    scheduled_date: date
    start_time: time


@dataclass(frozen=True)
class RecoveryCalculation:
    status: AttendancePlanStatus
    reachable: bool
    classes_required: int | None
    scheduled_classes_remaining: int
    scheduled_teaching_days_remaining: int
    teaching_days_required: int | None
    recovery_date: date | None
    projected_attendance_percentage: float
    projected_max_percentage: float
    attendance_buffer_classes: int


def _target_fraction(target_percentage: Decimal) -> Fraction:
    if target_percentage <= 0 or target_percentage > 100:
        raise ValueError("target_percentage must be greater than 0 and at most 100")
    return Fraction(target_percentage) / 100


def _ceil_fraction(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)


def required_attended_classes(
    *, attended: int, held: int, target_percentage: Decimal
) -> int | None:
    """Smallest future attended-class count that reaches the exact target.

    ``None`` means no finite number can reach the target (the 100% target
    after at least one recorded absence). With no history, the first
    attended class establishes 100% attendance and therefore reaches any
    supported target.
    """
    if held < 0 or attended < 0 or attended > held:
        raise ValueError("attendance counts must satisfy 0 <= attended <= held")
    target = _target_fraction(target_percentage)
    if held == 0:
        return 1
    if Fraction(attended, held) >= target:
        return 0
    if target == 1:
        return None
    gap = target * held - attended
    return max(0, _ceil_fraction(gap / (1 - target)))


def expand_timetable(
    slots: Sequence[TimetableSlot],
    *,
    start_date: date,
    deadline: date,
    subject_id: uuid.UUID | None = None,
) -> tuple[ScheduledClass, ...]:
    """Expand recurring weekly slots into concrete dates, inclusively."""
    if deadline < start_date:
        raise ValueError("deadline must not be before start_date")
    slots_by_weekday: dict[int, list[TimetableSlot]] = {}
    for slot in slots:
        if not 0 <= slot.weekday <= 6:
            raise ValueError("weekday must be between 0 and 6")
        if subject_id is not None and slot.subject_id != subject_id:
            continue
        slots_by_weekday.setdefault(slot.weekday, []).append(slot)

    occurrences: list[ScheduledClass] = []
    current_date = start_date
    while current_date <= deadline:
        for slot in slots_by_weekday.get(current_date.weekday(), []):
            occurrences.append(
                ScheduledClass(
                    timetable_entry_id=slot.timetable_entry_id,
                    subject_id=slot.subject_id,
                    scheduled_date=current_date,
                    start_time=slot.start_time,
                )
            )
        current_date += timedelta(days=1)
    occurrences.sort(
        key=lambda item: (
            item.scheduled_date,
            item.start_time,
            str(item.timetable_entry_id),
        )
    )
    return tuple(occurrences)


def subject_attendance_status(
    *, attended: int, held: int, target_percentage: Decimal
) -> SubjectAttendanceStatus:
    target = _target_fraction(target_percentage)
    if held == 0:
        return SubjectAttendanceStatus.NO_HISTORY
    current = Fraction(attended, held)
    if current >= target:
        return SubjectAttendanceStatus.SAFE
    if target - current <= Fraction(5, 100):
        return SubjectAttendanceStatus.NEAR_TARGET
    return SubjectAttendanceStatus.RECOVERY_NEEDED


def _attendance_buffer(
    *,
    attended: int,
    held: int,
    scheduled_classes: int,
    classes_required: int,
    target: Fraction,
) -> int:
    later_classes = max(0, scheduled_classes - classes_required)
    if later_classes == 0:
        return 0
    final_held = held + scheduled_classes
    required_final_attended = _ceil_fraction(target * final_held)
    available_misses = attended + scheduled_classes - required_final_attended
    return min(later_classes, max(0, available_misses))


def calculate_recovery(
    *,
    attended: int,
    held: int,
    target_percentage: Decimal,
    scheduled_classes: Sequence[ScheduledClass],
) -> RecoveryCalculation:
    """Calculate recovery, deadline feasibility, and the scheduled-class buffer."""
    target = _target_fraction(target_percentage)
    classes_required = required_attended_classes(
        attended=attended,
        held=held,
        target_percentage=target_percentage,
    )
    remaining = len(scheduled_classes)
    teaching_days_remaining = len({item.scheduled_date for item in scheduled_classes})
    projected_max = attendance_percentage(attended + remaining, held + remaining)

    if classes_required == 0:
        return RecoveryCalculation(
            status=AttendancePlanStatus.SAFE,
            reachable=True,
            classes_required=0,
            scheduled_classes_remaining=remaining,
            scheduled_teaching_days_remaining=teaching_days_remaining,
            teaching_days_required=0,
            recovery_date=None,
            projected_attendance_percentage=attendance_percentage(attended, held),
            projected_max_percentage=projected_max,
            attendance_buffer_classes=_attendance_buffer(
                attended=attended,
                held=held,
                scheduled_classes=remaining,
                classes_required=0,
                target=target,
            ),
        )

    if classes_required is not None and classes_required <= remaining:
        recovery_classes = scheduled_classes[:classes_required]
        recovery_date = recovery_classes[-1].scheduled_date
        teaching_days_required = len({item.scheduled_date for item in recovery_classes})
        status = (
            AttendancePlanStatus.TIGHT_RECOVERY
            if classes_required * 5 >= remaining * 4
            else AttendancePlanStatus.RECOVERY_POSSIBLE
        )
        return RecoveryCalculation(
            status=status,
            reachable=True,
            classes_required=classes_required,
            scheduled_classes_remaining=remaining,
            scheduled_teaching_days_remaining=teaching_days_remaining,
            teaching_days_required=teaching_days_required,
            recovery_date=recovery_date,
            projected_attendance_percentage=attendance_percentage(
                attended + classes_required,
                held + classes_required,
            ),
            projected_max_percentage=projected_max,
            attendance_buffer_classes=_attendance_buffer(
                attended=attended,
                held=held,
                scheduled_classes=remaining,
                classes_required=classes_required,
                target=target,
            ),
        )

    return RecoveryCalculation(
        status=AttendancePlanStatus.NOT_REACHABLE,
        reachable=False,
        classes_required=classes_required,
        scheduled_classes_remaining=remaining,
        scheduled_teaching_days_remaining=teaching_days_remaining,
        teaching_days_required=None,
        recovery_date=None,
        projected_attendance_percentage=projected_max,
        projected_max_percentage=projected_max,
        attendance_buffer_classes=0,
    )


__all__ = [
    "AttendancePlanStatus",
    "RecoveryCalculation",
    "ScheduledClass",
    "SubjectAttendanceStatus",
    "TimetableSlot",
    "calculate_recovery",
    "expand_timetable",
    "required_attended_classes",
    "subject_attendance_status",
]
