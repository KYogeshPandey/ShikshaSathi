import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import { ReportsPage } from "./ReportsPage";

const ids = {
  classroom: "00000000-0000-4000-8000-000000000001",
  subject: "00000000-0000-4000-8000-000000000002",
  student1: "00000000-0000-4000-8000-000000000003",
  student2: "00000000-0000-4000-8000-000000000004",
};

const mocks = vi.hoisted(() => ({
  listClassrooms: vi.fn(),
  listSubjects: vi.fn(),
  getRoster: vi.fn(),
  getAttendance: vi.fn(),
  getDefaulters: vi.fn(),
  getLeaderboard: vi.fn(),
  downloadAttendance: vi.fn(),
}));

vi.mock("../api/academics", () => ({
  academicsApi: {
    listClassrooms: mocks.listClassrooms,
    listSubjects: mocks.listSubjects,
  },
}));
vi.mock("../api/attendance", () => ({ attendanceApi: { getRoster: mocks.getRoster } }));
vi.mock("../api/reports", () => ({
  reportsApi: {
    getAttendance: mocks.getAttendance,
    getDefaulters: mocks.getDefaulters,
    getLeaderboard: mocks.getLeaderboard,
    downloadAttendance: mocks.downloadAttendance,
  },
}));

function period() {
  return { month: "2026-08", date_from: "2026-08-01", date_to: "2026-08-31" };
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ReportsPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.listClassrooms.mockResolvedValue({
    items: [{ id: ids.classroom, name: "Grade 7", code: "g7" }],
    total: 1,
    limit: 100,
    offset: 0,
  });
  mocks.listSubjects.mockResolvedValue({
    items: [{ id: ids.subject, name: "Mathematics", code: "math" }],
    total: 1,
    limit: 100,
    offset: 0,
  });
  mocks.getRoster.mockResolvedValue([
    { student_profile_id: ids.student1, roll_number: "01" },
    { student_profile_id: ids.student2, roll_number: "02" },
  ]);
  mocks.getAttendance.mockResolvedValue({
    classroom_id: ids.classroom,
    subject_id: ids.subject,
    student_profile_id: null,
    period: period(),
    summary: { total_count: 2, present_count: 1, absent_count: 1, attendance_percentage: 50 },
    details: [
      { attendance_date: "2026-08-01", student_profile_id: ids.student1, roll_number: "01", status: "present", remarks: null },
      { attendance_date: "2026-08-01", student_profile_id: ids.student2, roll_number: "02", status: "absent", remarks: "Late" },
    ],
  });
  mocks.getDefaulters.mockResolvedValue({
    classroom_id: ids.classroom,
    subject_id: ids.subject,
    period: period(),
    threshold: 75,
    zero_attendance_policy: "included_as_zero_percent",
    students: [
      { student_profile_id: ids.student2, roll_number: "02", total_count: 2, present_count: 1, absent_count: 1, attendance_percentage: 50 },
    ],
  });
  mocks.getLeaderboard.mockResolvedValue({
    classroom_id: ids.classroom,
    subject_id: ids.subject,
    period: period(),
    tie_breaking: "percentage_desc_roll_number_asc_student_profile_id_asc",
    students: [
      { rank: 1, student_profile_id: ids.student1, roll_number: "01", total_count: 2, present_count: 2, absent_count: 0, attendance_percentage: 100 },
      { rank: 2, student_profile_id: ids.student2, roll_number: "02", total_count: 2, present_count: 1, absent_count: 1, attendance_percentage: 50 },
    ],
  });
  mocks.downloadAttendance.mockResolvedValue({
    blob: new Blob(["report"]),
    contentType: "text/csv",
    filename: "authorized-report.csv",
  });
});

async function chooseScopeAndGenerate() {
  const user = userEvent.setup();
  renderPage();
  await screen.findByRole("option", { name: "Grade 7 (g7)" });
  await user.selectOptions(screen.getByLabelText("Classroom"), ids.classroom);
  await user.selectOptions(screen.getByLabelText("Subject"), ids.subject);
  fireEvent.change(screen.getByLabelText("Month"), { target: { value: "2026-08" } });
  await user.click(screen.getByRole("button", { name: "Generate reports" }));
  await screen.findByRole("heading", { name: "Attendance detail" });
  return user;
}

describe("reports workflow", () => {
  it("does not request reports until valid filters are submitted", async () => {
    renderPage();
    await screen.findByRole("option", { name: "Grade 7 (g7)" });
    expect(mocks.getAttendance).not.toHaveBeenCalled();
    expect(mocks.getDefaulters).not.toHaveBeenCalled();
    expect(mocks.getLeaderboard).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Generate reports" }));
    expect(await screen.findByText("Choose a classroom.")).toBeVisible();
    expect(mocks.getAttendance).not.toHaveBeenCalled();
  });

  it("loads summaries, details, defaulters, and leaderboard in server order", async () => {
    await chooseScopeAndGenerate();
    const expectedFilters = {
      classroomId: ids.classroom,
      subjectId: ids.subject,
      month: "2026-08",
      studentProfileId: undefined,
      threshold: 75,
    };
    expect(mocks.getAttendance).toHaveBeenCalledWith(expectedFilters);
    expect(mocks.getDefaulters).toHaveBeenCalledWith(expectedFilters);
    expect(mocks.getLeaderboard).toHaveBeenCalledWith(expectedFilters);
    const context = screen.getByRole("region", { name: "Applied report context" });
    expect(within(context).getByText("Grade 7 (g7)")).toBeVisible();
    expect(within(context).getByText("Mathematics (math)")).toBeVisible();
    expect(within(context).getByText("2026-08-01 to 2026-08-31")).toBeVisible();
    expect(within(context).getByText(/unmarked records are not counted as absent/i)).toBeVisible();
    expect(screen.getAllByText("50.00%")).toHaveLength(3);
    expect(screen.getByText("Late")).toBeVisible();

    const leaderboardCard = screen.getByRole("heading", { name: "Classroom leaderboard" }).closest(".table-card");
    expect(leaderboardCard).not.toBeNull();
    const rows = within(leaderboardCard as HTMLElement).getAllByRole("row").slice(1);
    expect(within(rows[0]!).getByText("01")).toBeVisible();
    expect(within(rows[1]!).getByText("02")).toBeVisible();
  });

  it("surfaces report errors without presenting stale success", async () => {
    mocks.getAttendance.mockRejectedValue(
      new ApiError(403, "FORBIDDEN", "This reporting scope is not authorized."),
    );
    renderPage();
    const user = userEvent.setup();
    await screen.findByRole("option", { name: "Grade 7 (g7)" });
    await user.selectOptions(screen.getByLabelText("Classroom"), ids.classroom);
    await user.selectOptions(screen.getByLabelText("Subject"), ids.subject);
    await user.click(screen.getByRole("button", { name: "Generate reports" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This reporting scope is not authorized.",
    );
    expect(screen.queryByText(/downloaded/i)).not.toBeInTheDocument();
  });

  it("downloads through an object URL and always revokes it", async () => {
    const createObjectUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:phase-8-report");
    const revokeObjectUrl = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const user = await chooseScopeAndGenerate();

    await user.click(screen.getByRole("button", { name: "Download CSV" }));
    expect(await screen.findByRole("status")).toHaveTextContent("CSV report downloaded.");
    expect(mocks.downloadAttendance).toHaveBeenCalledWith("csv", expect.objectContaining({ month: "2026-08" }));
    expect(createObjectUrl).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledOnce();
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:phase-8-report");
  });

  it("supports a bounded explicit date range", async () => {
    renderPage();
    const user = userEvent.setup();
    await screen.findByRole("option", { name: "Grade 7 (g7)" });
    await user.selectOptions(screen.getByLabelText("Classroom"), ids.classroom);
    await user.selectOptions(screen.getByLabelText("Subject"), ids.subject);
    await user.selectOptions(screen.getByLabelText("Period type"), "range");
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-08-01" } });
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-08-16" } });
    await user.click(screen.getByRole("button", { name: "Generate reports" }));
    await waitFor(() => expect(mocks.getAttendance).toHaveBeenCalledWith(expect.objectContaining({
      dateFrom: "2026-08-01",
      dateTo: "2026-08-16",
    })));
    expect(mocks.getAttendance.mock.calls[0]?.[0]).not.toHaveProperty("month");
  });
});
