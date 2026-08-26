import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AdminImportsPage } from "./AdminImportsPage";

const mocks = vi.hoisted(() => ({
  upload: vi.fn(),
  onboard: vi.fn(),
  listClassrooms: vi.fn(),
}));

vi.mock("../api/imports", () => ({
  importsApi: { upload: mocks.upload, onboard: mocks.onboard },
}));
vi.mock("../api/academics", () => ({
  academicsApi: { listClassrooms: mocks.listClassrooms },
}));

const classroomId = "0ee1c4bc-641c-5fa7-9537-177b97840172";

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AdminImportsPage />
    </QueryClientProvider>,
  );
}

const successResult = {
  classroom_id: classroomId,
  classroom_name: "AI Section A",
  total_students: 1,
  profile_success_count: 1,
  face_success_count: 1,
  students: [
    {
      row_number: 2,
      student_profile_id: "c93030ae-d6d7-4239-85a0-c139420c9668",
      full_name: "Yogesh Pandey",
      roll_number: "101",
      profile_status: "imported" as const,
      photo_filename: "101.JPG",
      photo_status: "matched" as const,
      biometric_status: "enrolled" as const,
      issues: [],
    },
  ],
  unmatched_files: [{ filename: "999.jpg", code: "PHOTO_NO_MATCHING_STUDENT", message: "No matching student roll number exists in this import." }],
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.upload.mockResolvedValue({
    entity: "classrooms",
    success: true,
    total_rows: 1,
    imported_count: 1,
    failed_count: 0,
    errors: [],
  });
  mocks.onboard.mockResolvedValue(successResult);
  mocks.listClassrooms.mockResolvedValue({
    items: [
      {
        id: classroomId,
        name: "AI Section A",
        code: "AI-A",
        grade_level: null,
        section: "A",
        is_active: true,
        created_at: "2026-08-01T00:00:00Z",
        updated_at: "2026-08-01T00:00:00Z",
      },
    ],
    total: 1,
    limit: 100,
    offset: 0,
  });
});

describe("bulk imports", () => {
  it("keeps generic imports on the existing API", async () => {
    renderPage();
    const user = userEvent.setup();
    const file = new File(["name,code\nClass A,A"], "classrooms.csv", { type: "text/csv" });

    await user.upload(screen.getByLabelText("CSV or XLSX file"), file);
    await user.click(screen.getByRole("button", { name: "Run import" }));

    await waitFor(() => expect(mocks.upload).toHaveBeenCalledWith("classrooms", file));
    expect(mocks.onboard).not.toHaveBeenCalled();
  });

  it("submits the selected XLSX through refs while keeping the ZIP optional", async () => {
    renderPage();
    const user = userEvent.setup();
    const file = new File(["workbook"], "students.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });

    await user.selectOptions(screen.getByLabelText("Record type"), "student-profiles");
    await user.selectOptions(screen.getByLabelText("Classroom"), classroomId);
    expect(screen.getByLabelText("Student CSV or XLSX")).toBeInTheDocument();
    expect(screen.getByLabelText("Student photos ZIP (optional)")).toBeInTheDocument();
    await user.upload(screen.getByLabelText("Student CSV or XLSX"), file);
    await user.click(screen.getByRole("button", { name: "Validate & Import" }));

    await waitFor(() =>
      expect(mocks.onboard).toHaveBeenCalledWith(classroomId, file, undefined),
    );
    expect(screen.queryByText("Choose a CSV or XLSX file.")).not.toBeInTheDocument();
  });

  it("sends both files and renders names, statuses, reasons, and unmatched photos", async () => {
    renderPage();
    const user = userEvent.setup();
    const spreadsheet = new File(["workbook"], "students.xlsx");
    const photos = new File(["zip"], "class-photos.zip", { type: "application/zip" });

    await user.selectOptions(screen.getByLabelText("Record type"), "student-profiles");
    await user.selectOptions(screen.getByLabelText("Classroom"), classroomId);
    await user.upload(screen.getByLabelText("Student CSV or XLSX"), spreadsheet);
    await user.upload(screen.getByLabelText("Student photos ZIP (optional)"), photos);
    await user.click(screen.getByRole("button", { name: "Validate & Import" }));

    await waitFor(() =>
      expect(mocks.onboard).toHaveBeenCalledWith(classroomId, spreadsheet, photos),
    );
    expect(await screen.findByText("Yogesh Pandey")).toBeInTheDocument();
    expect(screen.getByText("101")).toBeInTheDocument();
    expect(screen.getAllByText("AI Section A").length).toBeGreaterThan(0);
    expect(screen.getByText(/Imported/)).toBeInTheDocument();
    expect(screen.getByText(/Face enrolled/)).toBeInTheDocument();
    expect(screen.getByText("999.jpg")).toBeInTheDocument();
    expect(screen.queryByText("c93030ae-d6d7-4239-85a0-c139420c9668")).not.toBeInTheDocument();
  });

  it("shows a missing-photo face failure without hiding profile success", async () => {
    mocks.onboard.mockResolvedValue({
      ...successResult,
      face_success_count: 0,
      unmatched_files: [],
      students: [
        {
          ...successResult.students[0],
          photo_filename: null,
          photo_status: "missing",
          biometric_status: "not_processed",
          issues: [{ code: "PHOTO_MISSING", message: "No matching photo was provided." }],
        },
      ],
    });
    renderPage();
    const user = userEvent.setup();

    await user.selectOptions(screen.getByLabelText("Record type"), "student-profiles");
    await user.selectOptions(screen.getByLabelText("Classroom"), classroomId);
    await user.upload(
      screen.getByLabelText("Student CSV or XLSX"),
      new File(["workbook"], "students.xlsx"),
    );
    await user.upload(
      screen.getByLabelText("Student photos ZIP (optional)"),
      new File(["zip"], "photos.zip"),
    );
    await user.click(screen.getByRole("button", { name: "Validate & Import" }));

    expect(await screen.findByText(/Imported/)).toBeInTheDocument();
    expect(screen.getByText(/Missing/)).toBeInTheDocument();
    expect(screen.getByText(/No matching photo was provided/)).toBeInTheDocument();
  });

  it("shows a useful empty state when no classroom can scope onboarding", async () => {
    mocks.listClassrooms.mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 });
    renderPage();
    const user = userEvent.setup();

    await user.selectOptions(screen.getByLabelText("Record type"), "student-profiles");

    expect(
      await screen.findByText("No classrooms available. Create a classroom first."),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Validate & Import" })).toBeDisabled();
  });
});
