import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  AdminAssignmentsPage,
  AdminStudentsPage,
  AdminTeachersPage,
  AdminTimetablePage,
} from "./AdminResourcePages";

const ids = {
  studentUser: "11111111-1111-4111-8111-111111111111",
  teacherUser: "22222222-2222-4222-8222-222222222222",
  studentProfile: "33333333-3333-4333-8333-333333333333",
  teacherProfile: "44444444-4444-4444-8444-444444444444",
  classroom: "55555555-5555-4555-8555-555555555555",
  subject: "66666666-6666-4666-8666-666666666666",
  assignment: "77777777-7777-4777-8777-777777777777",
  timetable: "88888888-8888-4888-8888-888888888888",
};

const academics = vi.hoisted(() => ({
  listClassrooms: vi.fn(), listSubjects: vi.fn(), listAssignments: vi.fn(), listTimetable: vi.fn(),
  createAssignment: vi.fn(), updateAssignment: vi.fn(), deactivateAssignment: vi.fn(),
  createTimetable: vi.fn(), updateTimetable: vi.fn(), deactivateTimetable: vi.fn(),
}));
const profiles = vi.hoisted(() => ({
  listTeachers: vi.fn(), listStudents: vi.fn(), createTeacher: vi.fn(), updateTeacher: vi.fn(), deactivateTeacher: vi.fn(),
  createStudent: vi.fn(), updateMembership: vi.fn(), deactivateStudent: vi.fn(),
}));
const users = vi.hoisted(() => ({ list: vi.fn() }));

vi.mock("../../api/academics", () => ({ academicsApi: academics }));
vi.mock("../../api/profiles", () => ({ profilesApi: profiles }));
vi.mock("../../api/users", () => ({ usersApi: users }));

const active = { is_active: true, created_at: "2026-08-01T00:00:00Z", updated_at: "2026-08-01T00:00:00Z" };
const classroom = { ...active, id: ids.classroom, name: "AI Section A", code: "AI-A", grade_level: null, section: "A" };
const subject = { ...active, id: ids.subject, name: "Mathematics", code: "MATH", is_elective: false };
const teacher = { ...active, id: ids.teacherProfile, user_id: ids.teacherUser, employee_code: "DEMO-T-001", phone_number: null };
const student = { ...active, id: ids.studentProfile, user_id: ids.studentUser, classroom_id: ids.classroom, roll_number: "101" };
const assignment = { ...active, id: ids.assignment, teacher_profile_id: ids.teacherProfile, classroom_id: ids.classroom, subject_id: ids.subject };
const timetable = { ...active, id: ids.timetable, classroom_id: ids.classroom, subject_id: ids.subject, teacher_profile_id: ids.teacherProfile, day_of_week: "monday", start_time: "09:00:00", end_time: "09:45:00" };

function page(items: unknown[]) { return { items, total: items.length, limit: 100, offset: 0 }; }
function renderPage(component: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}>{component}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  users.list.mockImplementation(async (role: string) => page(role === "student"
    ? [{ id: ids.studentUser, email: "yogesh@example.com", full_name: "Yogesh Pandey", role: "student", is_active: true }]
    : [{ id: ids.teacherUser, email: "teacher@example.com", full_name: "Demo Teacher One", role: "teacher", is_active: true }]));
  academics.listClassrooms.mockResolvedValue(page([classroom]));
  academics.listSubjects.mockResolvedValue(page([subject]));
  academics.listAssignments.mockResolvedValue(page([assignment]));
  academics.listTimetable.mockResolvedValue(page([timetable]));
  profiles.listTeachers.mockResolvedValue(page([teacher]));
  profiles.listStudents.mockResolvedValue(page([student]));
  profiles.createStudent.mockResolvedValue(student);
  profiles.createTeacher.mockResolvedValue(teacher);
  academics.createAssignment.mockResolvedValue(assignment);
  academics.createTimetable.mockResolvedValue(timetable);
});

describe("human-readable Admin resource pages", () => {
  it("shows Student and classroom labels while keeping IDs in create payloads", async () => {
    const user = userEvent.setup();
    renderPage(<AdminStudentsPage />);
    const table = await screen.findByRole("region", { name: "Students records table" });
    expect(table).toHaveTextContent("Yogesh Pandey");
    expect(table).toHaveTextContent("101");
    expect(table).toHaveTextContent("AI Section A");
    expect(table).not.toHaveTextContent(ids.studentUser);
    expect(table).not.toHaveTextContent(ids.classroom);

    await user.selectOptions(screen.getByLabelText("Classroom"), ids.classroom);
    await user.type(screen.getByLabelText("Roll number"), "102");
    await user.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => expect(profiles.createStudent).toHaveBeenCalledWith({
      user_id: ids.studentUser, classroom_id: ids.classroom, roll_number: "102",
    }));
  });

  it("shows Teacher identity instead of the linked User UUID", async () => {
    renderPage(<AdminTeachersPage />);
    const table = await screen.findByRole("region", { name: "Teachers records table" });
    expect(screen.getByLabelText("Teacher")).toHaveDisplayValue("Demo Teacher One — teacher@example.com");
    expect(table).toHaveTextContent("Demo Teacher One");
    expect(table).toHaveTextContent("DEMO-T-001");
    expect(table).not.toHaveTextContent(ids.teacherUser);
  });

  it("uses named assignment selectors and submits their internal IDs", async () => {
    const user = userEvent.setup();
    renderPage(<AdminAssignmentsPage />);
    const table = await screen.findByRole("region", { name: "Teacher assignments records table" });
    expect(table).toHaveTextContent("Demo Teacher One");
    expect(table).toHaveTextContent("AI Section A");
    expect(table).toHaveTextContent("Mathematics");
    expect(table).not.toHaveTextContent(ids.assignment);
    await user.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => expect(academics.createAssignment).toHaveBeenCalledWith({
      teacher_profile_id: ids.teacherProfile, classroom_id: ids.classroom, subject_id: ids.subject,
    }));
  });

  it("renders and creates timetable entries with names and clean day/time labels", async () => {
    const user = userEvent.setup();
    renderPage(<AdminTimetablePage />);
    const table = await screen.findByRole("region", { name: "Timetable entries records table" });
    expect(table).toHaveTextContent("Monday");
    expect(table).toHaveTextContent("09:00–09:45");
    expect(table).toHaveTextContent("AI Section A");
    expect(table).toHaveTextContent("Mathematics");
    expect(table).toHaveTextContent("Demo Teacher One");
    expect(table).not.toHaveTextContent(ids.classroom);

    await user.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => expect(academics.createTimetable).toHaveBeenCalledWith({
      classroom_id: ids.classroom,
      subject_id: ids.subject,
      teacher_profile_id: ids.teacherProfile,
      day_of_week: "monday",
      start_time: "08:00",
      end_time: "09:00",
    }));
  });
});
