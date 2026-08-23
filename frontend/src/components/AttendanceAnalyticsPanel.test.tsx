import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { AnalyticsOverview, AnalyticsTrendPoint } from "../types/domain";
import { attendanceInsight } from "../lib/attendanceAnalytics";
import { AttendanceAnalyticsPanel } from "./AttendanceAnalyticsPanel";

function point(
  attendanceDate: string,
  totalCount: number,
  presentCount: number,
): AnalyticsTrendPoint {
  return {
    attendance_date: attendanceDate,
    total_count: totalCount,
    present_count: presentCount,
    absent_count: totalCount - presentCount,
    attendance_percentage: totalCount === 0 ? 0 : (presentCount / totalCount) * 100,
  };
}

function makeOverview(
  overrides: Partial<AnalyticsOverview> = {},
): AnalyticsOverview {
  return {
    role: "admin",
    period: { days: 7, date_from: "2026-08-14", date_to: "2026-08-20" },
    attendance: {
      total_count: 8,
      present_count: 6,
      absent_count: 2,
      attendance_percentage: 75,
    },
    comparison: {
      period: { days: 7, date_from: "2026-08-07", date_to: "2026-08-13" },
      attendance: {
        total_count: 10,
        present_count: 7,
        absent_count: 3,
        attendance_percentage: 70,
      },
      percentage_point_change: 5,
    },
    trend: [
      point("2026-08-14", 2, 1),
      point("2026-08-15", 0, 0),
      point("2026-08-16", 1, 1),
      point("2026-08-17", 1, 1),
      point("2026-08-18", 2, 1),
      point("2026-08-19", 1, 1),
      point("2026-08-20", 1, 1),
    ],
    attendance_definition: "present_marked_records_divided_by_all_marked_records",
    missing_records_policy: "excluded_unmarked",
    admin_population: {
      active_students: 120,
      active_teachers: 12,
      active_classrooms: 8,
      active_subjects: 10,
    },
    teacher_scope: null,
    student_context: null,
    attention_classrooms: [],
    ...overrides,
  };
}

describe("AttendanceAnalyticsPanel", () => {
  it("renders a named chart, truthful summary, formula, and daily table fallback", async () => {
    const user = userEvent.setup();
    render(<AttendanceAnalyticsPanel days={7} onDaysChange={vi.fn()} overview={makeOverview()} />);

    expect(screen.getByRole("img", { name: /daily attendance rate/i })).toBeVisible();
    expect(screen.getByText(/increased by 5 percentage points/i, { selector: ".analytics-insight" })).toBeVisible();
    expect(screen.getByText(/missing or unmarked records are excluded/i)).toBeVisible();

    await user.click(screen.getByText(/view daily attendance values/i));
    expect(screen.getByRole("region", { name: /daily attendance values/i })).toBeVisible();
    expect(screen.getByRole("cell", { name: /no marked records/i })).toBeVisible();
  });

  it("uses native pressed buttons to change the analytics window", async () => {
    const user = userEvent.setup();
    const onDaysChange = vi.fn();
    render(
      <AttendanceAnalyticsPanel days={7} onDaysChange={onDaysChange} overview={makeOverview()} />,
    );

    expect(screen.getByRole("button", { name: /last 7 days/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await user.click(screen.getByRole("button", { name: /last 30 days/i }));
    expect(onDaysChange).toHaveBeenCalledWith(30);
  });

  it("shows a real empty state instead of presenting missing days as zero attendance", () => {
    const empty = makeOverview({
      attendance: {
        total_count: 0,
        present_count: 0,
        absent_count: 0,
        attendance_percentage: 0,
      },
      comparison: {
        period: { days: 7, date_from: "2026-08-07", date_to: "2026-08-13" },
        attendance: {
          total_count: 0,
          present_count: 0,
          absent_count: 0,
          attendance_percentage: 0,
        },
        percentage_point_change: null,
      },
      trend: Array.from({ length: 7 }, (_, index) =>
        point(`2026-08-${String(14 + index).padStart(2, "0")}`, 0, 0),
      ),
    });

    render(<AttendanceAnalyticsPanel days={7} onDaysChange={vi.fn()} overview={empty} />);

    expect(screen.getByText(/no attendance data is available for this period/i)).toBeVisible();
    expect(screen.getByText(/no marked attendance records are available/i)).toBeVisible();
    expect(screen.queryByRole("img", { name: /daily attendance rate/i })).not.toBeInTheDocument();
  });

  it("describes unavailable, unchanged, and declining comparisons without causal claims", () => {
    const base = makeOverview();
    expect(
      attendanceInsight({
        ...base,
        comparison: { ...base.comparison, percentage_point_change: null },
      }),
    ).toMatch(/comparison is not available/i);
    expect(
      attendanceInsight({
        ...base,
        comparison: { ...base.comparison, percentage_point_change: 0 },
      }),
    ).toMatch(/unchanged/i);
    expect(
      attendanceInsight({
        ...base,
        comparison: { ...base.comparison, percentage_point_change: -4.25 },
      }),
    ).toMatch(/decreased by 4.25 percentage points/i);
  });
});
