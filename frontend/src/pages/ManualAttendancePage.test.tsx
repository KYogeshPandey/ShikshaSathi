import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import { ManualAttendancePage } from "./ManualAttendancePage";

const ids = {
  classroom: "00000000-0000-4000-8000-000000000001",
  subject: "00000000-0000-4000-8000-000000000002",
  student: "00000000-0000-4000-8000-000000000003",
};

const mocks = vi.hoisted(() => ({
  listClassrooms: vi.fn(),
  listSubjects: vi.fn(),
  getRoster: vi.fn(),
  getDaily: vi.fn(),
  saveBulk: vi.fn(),
}));

vi.mock("../api/academics", () => ({ academicsApi: { listClassrooms: mocks.listClassrooms, listSubjects: mocks.listSubjects } }));
vi.mock("../api/attendance", () => ({ attendanceApi: { getRoster: mocks.getRoster, getDaily: mocks.getDaily, saveBulk: mocks.saveBulk } }));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><ManualAttendancePage /></QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.listClassrooms.mockResolvedValue({ items: [{ id: ids.classroom, name: "Grade 7", code: "G7" }], total: 1, limit: 100, offset: 0 });
  mocks.listSubjects.mockResolvedValue({ items: [{ id: ids.subject, name: "Math", code: "MATH" }], total: 1, limit: 100, offset: 0 });
  mocks.getRoster.mockResolvedValue([{ student_profile_id: ids.student, roll_number: "7" }]);
  mocks.getDaily.mockResolvedValue({ records: [], classroom_id: ids.classroom, subject_id: ids.subject, attendance_date: "2026-08-16" });
  mocks.saveBulk.mockResolvedValue({ total_count: 1, created_count: 1, updated_count: 0, record_ids: ["record-id"] });
});

async function loadRoster() {
  renderPage();
  const user = userEvent.setup();
  await screen.findByRole("option", { name: "Grade 7 (G7)" });
  await user.selectOptions(screen.getByLabelText("Classroom"), ids.classroom);
  await user.selectOptions(screen.getByLabelText("Subject"), ids.subject);
  await user.click(screen.getByRole("button", { name: "Load roster" }));
  expect(await screen.findByText("Roll 7")).toBeVisible();
  return user;
}

describe("manual attendance", () => {
  it("loads the authoritative roster and submits one bulk payload", async () => {
    const user = await loadRoster();
    const presentButton = screen.getByRole("button", { name: "present" });
    expect(screen.getByRole("button", { name: "absent" })).toHaveAttribute("aria-pressed", "true");
    await user.click(presentButton);
    expect(presentButton).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: "Save attendance" }));

    await waitFor(() => expect(mocks.saveBulk).toHaveBeenCalledOnce());
    expect(mocks.getRoster).toHaveBeenCalledWith({ classroomId: ids.classroom, subjectId: ids.subject });
    expect(mocks.saveBulk.mock.calls[0]?.[0]).toMatchObject({
      classroom_id: ids.classroom,
      subject_id: ids.subject,
      records: [{ student_profile_id: ids.student, status: "present" }],
    });
    expect(await screen.findByText("1 attendance records saved.")).toBeVisible();
  });

  it("does not show a false success message when the bulk save fails", async () => {
    mocks.saveBulk.mockRejectedValue(new ApiError(403, "FORBIDDEN", "Scope not authorized."));
    const user = await loadRoster();
    await user.click(screen.getByRole("button", { name: "Save attendance" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Scope not authorized.");
    expect(screen.queryByText(/attendance records saved/i)).not.toBeInTheDocument();
  });
});
