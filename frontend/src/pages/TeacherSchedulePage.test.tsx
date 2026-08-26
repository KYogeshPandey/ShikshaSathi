import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TeacherSchedulePage } from "./TeacherSchedulePage";

const ids = { classroom: "0ee1c4bc-641c-5fa7-9537-177b97840172", subject: "6242154d-f47f-45be-9754-60cb959bb1b3" };
const mocks = vi.hoisted(() => ({ listClassrooms: vi.fn(), listSubjects: vi.fn(), listTimetable: vi.fn() }));
vi.mock("../api/academics", () => ({ academicsApi: mocks }));

function page(items: unknown[]) { return { items, total: items.length, limit: 100, offset: 0 }; }
function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><TeacherSchedulePage /></QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  const active = { is_active: true, created_at: "2026-08-01", updated_at: "2026-08-01" };
  mocks.listClassrooms.mockResolvedValue(page([{ ...active, id: ids.classroom, name: "AI Section A", code: "AI-A", grade_level: null, section: "A" }]));
  mocks.listSubjects.mockResolvedValue(page([{ ...active, id: ids.subject, name: "Mathematics", code: "MATH", is_elective: false }]));
  mocks.listTimetable.mockResolvedValue(page([{ ...active, id: "slot", classroom_id: ids.classroom, subject_id: ids.subject, teacher_profile_id: "teacher", day_of_week: "monday", start_time: "09:00:00", end_time: "09:45:00" }]));
});

describe("Teacher timetable", () => {
  it("renders classroom and subject names instead of UUIDs", async () => {
    renderPage();
    const table = await screen.findByRole("region", { name: "Assigned timetable" });
    expect(table).toHaveTextContent("Monday");
    expect(table).toHaveTextContent("09:00–09:45");
    expect(table).toHaveTextContent("AI Section A");
    expect(table).toHaveTextContent("Mathematics");
    expect(table).not.toHaveTextContent(ids.classroom);
    expect(table).not.toHaveTextContent(ids.subject);
  });
});
