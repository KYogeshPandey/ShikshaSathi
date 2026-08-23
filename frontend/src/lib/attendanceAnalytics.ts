import type { AnalyticsOverview } from "../types/domain";

const percentFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
  minimumFractionDigits: 0,
});

export function formatAttendancePercentage(value: number): string {
  return `${percentFormatter.format(value)}%`;
}

export function attendanceInsight(overview: AnalyticsOverview): string {
  if (overview.attendance.total_count === 0) {
    return `No marked attendance records are available for the last ${overview.period.days} days.`;
  }

  const change = overview.comparison.percentage_point_change;
  if (change === null) {
    return `Attendance was ${formatAttendancePercentage(overview.attendance.attendance_percentage)}. A previous-period comparison is not available because one period has no marked records.`;
  }
  if (change === 0) {
    return `Attendance was unchanged from the previous ${overview.period.days} days at ${formatAttendancePercentage(overview.attendance.attendance_percentage)}.`;
  }

  const direction = change > 0 ? "increased" : "decreased";
  return `Attendance ${direction} by ${percentFormatter.format(Math.abs(change))} percentage points compared with the previous ${overview.period.days} days.`;
}
