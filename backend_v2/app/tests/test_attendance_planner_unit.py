"""Pure attendance-recovery mathematics and recurring timetable projection."""

from __future__ import annotations

import uuid
from datetime import date, time, timedelta
from decimal import Decimal

import pytest

from app.modules.attendance.planner import (
    AttendancePlanStatus,
    ScheduledClass,
    TimetableSlot,
    calculate_recovery,
    expand_timetable,
    required_attended_classes,
)

SUBJECT_A = uuid.UUID("00000000-0000-4000-8000-000000000001")
SUBJECT_B = uuid.UUID("00000000-0000-4000-8000-000000000002")
MONDAY = date(2026, 8, 31)


def _slot(*, subject_id: uuid.UUID = SUBJECT_A, weekday: int = 0, hour: int = 9) -> TimetableSlot:
    return TimetableSlot(
        timetable_entry_id=uuid.uuid4(),
        subject_id=subject_id,
        weekday=weekday,
        start_time=time(hour, 0),
    )


def _classes(count: int) -> tuple[ScheduledClass, ...]:
    return tuple(
        ScheduledClass(
            timetable_entry_id=uuid.uuid4(),
            subject_id=SUBJECT_A,
            scheduled_date=MONDAY + timedelta(days=index // 4),
            start_time=time(8 + (index % 4)),
        )
        for index in range(count)
    )


@pytest.mark.parametrize(
    ("attended", "held"),
    [(82, 100), (75, 100)],
)
def test_already_above_or_exactly_at_target_is_safe(attended: int, held: int) -> None:
    result = calculate_recovery(
        attended=attended,
        held=held,
        target_percentage=Decimal("75"),
        scheduled_classes=(),
    )
    assert result.status is AttendancePlanStatus.SAFE
    assert result.classes_required == 0
    assert result.reachable is True


def test_recovery_possible_uses_smallest_exact_integer_crossing() -> None:
    assert required_attended_classes(attended=3, held=5, target_percentage=Decimal("75")) == 3
    result = calculate_recovery(
        attended=72,
        held=100,
        target_percentage=Decimal("75"),
        scheduled_classes=_classes(20),
    )
    assert result.classes_required == 12
    assert result.projected_attendance_percentage == 75.0
    assert result.reachable is True


def test_31_of_50_requires_26_and_is_not_reachable_with_18_classes() -> None:
    assert required_attended_classes(attended=31, held=50, target_percentage=Decimal("75")) == 26
    result = calculate_recovery(
        attended=31,
        held=50,
        target_percentage=Decimal("75"),
        scheduled_classes=_classes(18),
    )
    assert result.status is AttendancePlanStatus.NOT_REACHABLE
    assert result.classes_required == 26
    assert result.projected_max_percentage == 72.06
    assert result.recovery_date is None


def test_zero_history_reaches_target_after_first_scheduled_class() -> None:
    result = calculate_recovery(
        attended=0,
        held=0,
        target_percentage=Decimal("75"),
        scheduled_classes=_classes(1),
    )
    assert result.classes_required == 1
    assert result.projected_attendance_percentage == 100.0
    assert result.recovery_date == MONDAY


def test_no_future_classes_is_not_reachable_below_target() -> None:
    result = calculate_recovery(
        attended=6,
        held=10,
        target_percentage=Decimal("75"),
        scheduled_classes=(),
    )
    assert result.status is AttendancePlanStatus.NOT_REACHABLE
    assert result.scheduled_classes_remaining == 0
    assert result.projected_max_percentage == 60.0


def test_multiple_classes_on_one_day_count_separately_but_one_teaching_day() -> None:
    result = calculate_recovery(
        attended=3,
        held=5,
        target_percentage=Decimal("75"),
        scheduled_classes=_classes(3),
    )
    assert result.classes_required == 3
    assert result.teaching_days_required == 1
    assert result.scheduled_classes_remaining == 3


def test_buffer_counts_missable_scheduled_classes_after_recovery() -> None:
    result = calculate_recovery(
        attended=72,
        held=100,
        target_percentage=Decimal("75"),
        scheduled_classes=_classes(20),
    )
    assert result.classes_required == 12
    assert result.attendance_buffer_classes == 2


def test_weekday_expansion_ignores_unscheduled_days() -> None:
    occurrences = expand_timetable(
        (_slot(weekday=0), _slot(weekday=2, hour=10)),
        start_date=MONDAY,
        deadline=date(2026, 9, 6),
    )
    assert [item.scheduled_date for item in occurrences] == [
        date(2026, 8, 31),
        date(2026, 9, 2),
    ]


def test_multiple_timetable_entries_on_same_day_are_distinct_classes() -> None:
    occurrences = expand_timetable(
        (_slot(hour=9), _slot(hour=10)),
        start_date=MONDAY,
        deadline=MONDAY,
    )
    assert len(occurrences) == 2
    assert {item.start_time for item in occurrences} == {time(9), time(10)}


def test_subject_filter_counts_only_selected_subject_while_overall_counts_all() -> None:
    slots = (_slot(subject_id=SUBJECT_A, hour=9), _slot(subject_id=SUBJECT_B, hour=10))
    overall = expand_timetable(slots, start_date=MONDAY, deadline=MONDAY)
    subject = expand_timetable(
        slots,
        start_date=MONDAY,
        deadline=MONDAY,
        subject_id=SUBJECT_B,
    )
    assert len(overall) == 2
    assert len(subject) == 1
    assert subject[0].subject_id == SUBJECT_B


def test_deadline_before_projection_start_is_rejected() -> None:
    with pytest.raises(ValueError, match="deadline"):
        expand_timetable((), start_date=MONDAY, deadline=date(2026, 8, 30))
