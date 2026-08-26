import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { StudentAttendancePage } from "./StudentAttendancePage";

const ids = { classroom: "55555555-5555-4555-8555-555555555555", subject: "66666666-6666-4666-8666-666666666666" };
const attendance = vi.hoisted(() => ({ getMyStats: vi.fn(), getMyDetail: vi.fn() }));
const academics = vi.hoisted(() => ({ listClassrooms: vi.fn(), listSubjects: vi.fn() }));
vi.mock("../api/attendance", () => ({ attendanceApi: attendance }));
vi.mock("../api/academics", () => ({ academicsApi: academics }));

function page(items: unknown[]) { return { items, total: items.length, limit: 100, offset: 0 }; }
function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><StudentAttendancePage /></QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  const active = { is_active: true, created_at: "2026-08-01", updated_at: "2026-08-01" };
  academics.listClassrooms.mockResolvedValue(page([{ ...active, id: ids.classroom, name: "AI Section A", code: "AI-A", grade_level: null, section: "A" }]));
  academics.listSubjects.mockResolvedValue(page([{ ...active, id: ids.subject, name: "Mathematics", code: "MATH", is_elective: false }]));
  attendance.getMyStats.mockResolvedValue({ student_profile_id: "student", total_count: 1, present_count: 1, absent_count: 0, attendance_percentage: 100 });
  attendance.getMyDetail.mockResolvedValue(page([{ id: "record", student_profile_id: "student", classroom_id: ids.classroom, subject_id: ids.subject, attendance_date: "2026-08-25", status: "present", remarks: null, marked_by_user_id: "teacher", created_at: "2026-08-25", updated_at: "2026-08-25" }]));
});

describe("Student attendance labels", () => {
  it("uses named filters and rows while preserving IDs in API filters", async () => {
    const user = userEvent.setup();
    renderPage();
    const table = await screen.findByRole("region", { name: "Detailed attendance records" });
    expect(screen.getByLabelText("Classroom")).toHaveDisplayValue("All classrooms");
    expect(screen.getByLabelText("Subject")).toHaveDisplayValue("All subjects");
    expect(screen.queryByText(/UUID/i)).not.toBeInTheDocument();
    expect(table).toHaveTextContent("AI Section A");
    expect(table).toHaveTextContent("Mathematics");
    expect(table).not.toHaveTextContent(ids.classroom);
    expect(table).not.toHaveTextContent(ids.subject);

    await user.selectOptions(screen.getByLabelText("Classroom"), ids.classroom);
    await user.selectOptions(screen.getByLabelText("Subject"), ids.subject);
    await user.click(screen.getByRole("button", { name: "Apply filters" }));
    await waitFor(() => expect(attendance.getMyDetail).toHaveBeenLastCalledWith(
      expect.objectContaining({ classroomId: ids.classroom, subjectId: ids.subject }),
    ));
  });
});
