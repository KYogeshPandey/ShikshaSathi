"""Shared, authoritative attendance calculations.

Every attendance/report percentage uses this function so Phase 8 cannot drift
from the Phase 4 semantics: present / total * 100, rounded to two decimals,
with an explicit 0.0 result when no rows exist.
"""

from __future__ import annotations


def attendance_percentage(present_count: int, total_count: int) -> float:
    if total_count == 0:
        return 0.0
    return round((present_count / total_count) * 100, 2)


__all__ = ["attendance_percentage"]
