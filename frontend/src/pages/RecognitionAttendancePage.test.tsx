import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RecognitionAttendancePage } from "./RecognitionAttendancePage";

const ids = {
  classroom: "00000000-0000-4000-8000-000000000011",
  subject: "00000000-0000-4000-8000-000000000012",
  student: "00000000-0000-4000-8000-000000000013",
};

const mocks = vi.hoisted(() => ({
  listClassrooms: vi.fn(),
  listSubjects: vi.fn(),
  getRoster: vi.fn(),
  saveBulk: vi.fn(),
  createAttempt: vi.fn(),
  confirm: vi.fn(),
}));

vi.mock("../api/academics", () => ({ academicsApi: { listClassrooms: mocks.listClassrooms, listSubjects: mocks.listSubjects } }));
vi.mock("../api/attendance", () => ({ attendanceApi: { getRoster: mocks.getRoster, saveBulk: mocks.saveBulk } }));
vi.mock("../api/recognition", () => ({ recognitionApi: { createAttempt: mocks.createAttempt, confirm: mocks.confirm } }));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><RecognitionAttendancePage /></QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.listClassrooms.mockResolvedValue({ items: [{ id: ids.classroom, name: "Grade 7", code: "G7" }], total: 1, limit: 100, offset: 0 });
  mocks.listSubjects.mockResolvedValue({ items: [{ id: ids.subject, name: "Math", code: "MATH" }], total: 1, limit: 100, offset: 0 });
  mocks.getRoster.mockResolvedValue([{ student_profile_id: ids.student, roll_number: "7" }]);
  mocks.confirm.mockResolvedValue({ confirmed_student_profile_id: ids.student });
});

afterEach(() => vi.restoreAllMocks());

async function submitImage() {
  renderPage();
  const user = userEvent.setup();
  await screen.findByRole("option", { name: "Grade 7 (G7)" });
  await user.selectOptions(screen.getByLabelText("Classroom"), ids.classroom);
  await user.selectOptions(screen.getByLabelText("Subject"), ids.subject);
  const image = new File(["face"], "face.jpg", { type: "image/jpeg" });
  await user.upload(screen.getByLabelText("Image file fallback"), image);
  await user.click(screen.getByRole("button", { name: "Submit recognition attempt" }));
  return image;
}

describe("recognition attendance", () => {
  it("treats FOUND as already written and never sends a second bulk write", async () => {
    mocks.createAttempt.mockResolvedValue({
      attempt_id: "attempt-found",
      classroom_id: ids.classroom,
      subject_id: ids.subject,
      attendance_date: "2026-08-16",
      decision: "found",
      matched_student_profile_id: ids.student,
      attendance_record_id: "record-id",
      requires_confirmation: false,
    });
    const image = await submitImage();

    expect(await screen.findByRole("heading", { name: "FOUND" })).toBeVisible();
    expect(mocks.createAttempt).toHaveBeenCalledWith(expect.objectContaining({ classroomId: ids.classroom, subjectId: ids.subject, file: image }));
    expect(mocks.saveBulk).not.toHaveBeenCalled();
    expect(mocks.confirm).not.toHaveBeenCalled();
  });

  it("allows UNKNOWN confirmation only from the exact authorized roster", async () => {
    mocks.createAttempt.mockResolvedValue({
      attempt_id: "attempt-unknown",
      classroom_id: ids.classroom,
      subject_id: ids.subject,
      attendance_date: "2026-08-16",
      decision: "unknown",
      matched_student_profile_id: null,
      attendance_record_id: null,
      requires_confirmation: true,
    });
    await submitImage();

    await userEvent.selectOptions(await screen.findByLabelText("Confirm student"), ids.student);
    await userEvent.click(screen.getByRole("button", { name: "Confirm attendance" }));
    await waitFor(() => expect(mocks.confirm).toHaveBeenCalledWith("attempt-unknown", ids.student));
    expect(mocks.getRoster).toHaveBeenCalledWith({ classroomId: ids.classroom, subjectId: ids.subject });
    expect(await screen.findByText("Attendance confirmation saved.")).toBeVisible();
  });

  it("stops every camera track when the page unmounts", async () => {
    const stop = vi.fn();
    const stream = { getTracks: () => [{ stop }] } as unknown as MediaStream;
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn().mockResolvedValue(stream) } });
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
    const user = userEvent.setup();
    const view = renderPage();

    await user.click(await screen.findByRole("button", { name: "Start camera" }));
    await waitFor(() => expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalled());
    view.unmount();
    expect(stop).toHaveBeenCalledOnce();
  });
});
