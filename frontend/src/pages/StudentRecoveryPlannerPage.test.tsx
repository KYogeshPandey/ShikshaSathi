import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AttendanceRecoveryPlanRequest } from "../types/domain";
import { StudentRecoveryPlannerPage } from "./StudentRecoveryPlannerPage";

const scienceId = "00000000-0000-4000-8000-000000000001";
const mocks = vi.hoisted(() => ({ getRecoveryPlan: vi.fn() }));
vi.mock("../api/attendance", () => ({ attendanceApi: { getRecoveryPlan: mocks.getRecoveryPlan } }));

function plan(payload: AttendanceRecoveryPlanRequest) {
  const notReachable = payload.target_percentage === 90;
  return {
    scope: payload.subject_id ? "subject" : "overall",
    subject_id: payload.subject_id ?? null,
    subject_name: payload.subject_id ? "Science" : null,
    target_percentage: payload.target_percentage,
    deadline: payload.deadline,
    current: { attended: 72, held: 100, absent: 28, percentage: 72 },
    overall: { attended: 72, held: 100, absent: 28, percentage: 72 },
    overall_status: "near_target",
    subjects: [{ subject_id: scienceId, subject_name: "Science", subject_code: "SCI", attended: 20, held: 29, absent: 9, percentage: 68.97, status: "recovery_needed" }],
    status: notReachable ? "not_reachable" : "recovery_possible",
    reachable: !notReachable,
    classes_required: notReachable ? 80 : 12,
    scheduled_classes_remaining: 20,
    scheduled_teaching_days_remaining: 10,
    teaching_days_required: notReachable ? null : 6,
    recovery_date: notReachable ? null : "2026-09-05",
    projected_attendance_percentage: notReachable ? 78 : 75,
    projected_max_percentage: notReachable ? 78 : 76.67,
    attendance_buffer_classes: notReachable ? 0 : 2,
    schedule_assumption: "Projection uses recurring active timetable classes.",
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><StudentRecoveryPlannerPage /></QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getRecoveryPlan.mockImplementation(async (payload: AttendanceRecoveryPlanRequest) => plan(payload));
});

describe("Student Recovery Planner page", () => {
  it("preserves the existing planner inputs and recovery result", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { name: "Attendance Recovery Planner" })).toBeVisible();
    expect(await screen.findByLabelText("Plan for")).toBeVisible();
    expect(screen.getByLabelText("Target attendance")).toHaveValue(75);
    expect(screen.getByText(/attend the next 12 scheduled classes/i)).toBeVisible();
    expect(screen.getByText("05 Sept 2026")).toBeVisible();
    expect(screen.getByText("2 scheduled classes")).toBeVisible();
  });

  it("recalculates a subject plan without changing planner semantics", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByLabelText("Plan for");
    await user.selectOptions(screen.getByLabelText("Plan for"), scienceId);
    await user.clear(screen.getByLabelText("Target attendance"));
    await user.type(screen.getByLabelText("Target attendance"), "90");
    await user.click(screen.getByRole("button", { name: "Calculate plan" }));

    expect(await screen.findByText(/90% cannot be reached before/i)).toBeVisible();
    expect(screen.getByText(/maximum projected attendance: 78.0%/i)).toBeVisible();
    await waitFor(() => expect(mocks.getRecoveryPlan).toHaveBeenLastCalledWith(
      expect.objectContaining({ target_percentage: 90, subject_id: scienceId }),
    ));
  });

  it("validates inputs before requesting a new plan", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByLabelText("Target attendance");
    const calls = mocks.getRecoveryPlan.mock.calls.length;
    await user.clear(screen.getByLabelText("Target attendance"));
    await user.type(screen.getByLabelText("Target attendance"), "0");
    await user.click(screen.getByRole("button", { name: "Calculate plan" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/greater than 0/i);
    expect(mocks.getRecoveryPlan).toHaveBeenCalledTimes(calls);
  });
});
