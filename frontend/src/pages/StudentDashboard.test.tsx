import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { StudentDashboard } from "./StudentDashboard";

const mocks = vi.hoisted(() => ({ getOverview: vi.fn(), getRecoveryPlan: vi.fn() }));

vi.mock("../api/analytics", () => ({ analyticsApi: { getOverview: mocks.getOverview } }));
vi.mock("../api/attendance", () => ({ attendanceApi: { getRecoveryPlan: mocks.getRecoveryPlan } }));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter><StudentDashboard /></MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getOverview.mockResolvedValue({
    role: "student",
    period: { days: 7, date_from: "2026-08-19", date_to: "2026-08-25" },
    attendance: { total_count: 7, present_count: 5, absent_count: 2, attendance_percentage: 71.43 },
    comparison: {
      period: { days: 7, date_from: "2026-08-12", date_to: "2026-08-18" },
      attendance: { total_count: 7, present_count: 4, absent_count: 3, attendance_percentage: 57.14 },
      percentage_point_change: 14.29,
    },
    trend: [],
    attendance_definition: "present_marked_records_divided_by_all_marked_records",
    missing_records_policy: "excluded_unmarked",
    admin_population: null,
    teacher_scope: null,
    student_context: { roll_number: "101" },
    attention_classrooms: [],
  });
  mocks.getRecoveryPlan.mockResolvedValue({
    target_percentage: 75,
    overall: { attended: 72, held: 100, absent: 28, percentage: 72 },
    overall_status: "near_target",
    subjects: [
      { subject_id: "science-id", subject_name: "Science", subject_code: "SCI", attended: 20, held: 29, absent: 9, percentage: 68.97, status: "recovery_needed" },
    ],
  });
});

describe("Student overview", () => {
  it("shows a concise summary and links to dedicated planner and timetable routes", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "Attendance overview" })).toBeVisible();
    expect(screen.getByRole("region", { name: "Subject-wise attendance" })).toHaveTextContent("Science");
    expect(screen.getByRole("link", { name: /Attendance Recovery Planner/i })).toHaveAttribute(
      "href",
      "/student/recovery-planner",
    );
    expect(screen.getByRole("link", { name: /Weekly Timetable/i })).toHaveAttribute(
      "href",
      "/student/timetable",
    );
    expect(screen.queryByLabelText("Plan for")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Student weekly timetable" })).not.toBeInTheDocument();
    expect(await screen.findByText("Recent attendance trend")).toBeVisible();
  });
});
