import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
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
  createReview: vi.fn(),
  confirmReview: vi.fn(),
}));

vi.mock("../api/academics", () => ({ academicsApi: { listClassrooms: mocks.listClassrooms, listSubjects: mocks.listSubjects } }));
vi.mock("../api/attendance", () => ({ attendanceApi: { getRoster: mocks.getRoster, saveBulk: mocks.saveBulk } }));
vi.mock("../api/recognition", () => ({ recognitionApi: { createReview: mocks.createReview, confirmReview: mocks.confirmReview } }));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><RecognitionAttendancePage /></QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.listClassrooms.mockResolvedValue({ items: [{ id: ids.classroom, name: "Grade 7", code: "G7" }], total: 1, limit: 100, offset: 0 });
  mocks.listSubjects.mockResolvedValue({ items: [{ id: ids.subject, name: "Math", code: "MATH" }], total: 1, limit: 100, offset: 0 });
  mocks.getRoster.mockResolvedValue([
    { student_profile_id: ids.student, full_name: "Yogesh Pandey", roll_number: "101" },
  ]);
  mocks.confirmReview.mockResolvedValue({ review_id: "review-id", attendance_record_ids: ["record-id"], confirmed_records: [] });
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
  await user.click(screen.getByRole("button", { name: "Create review" }));
  return image;
}

describe("recognition attendance", () => {
  it("shows FOUND as a proposal and writes only after explicit review confirmation", async () => {
    mocks.createReview.mockResolvedValue({
      review_id: "review-found",
      classroom_id: ids.classroom,
      subject_id: ids.subject,
      attendance_date: "2026-08-16",
      face_count: 1,
      proposals: [{ attempt_id: "attempt-found", face_index: 0, decision: "found", matched_student_profile_id: ids.student, best_similarity: 0.99, is_duplicate: false }],
    });
    const image = await submitImage();

    expect(await screen.findByRole("heading", { name: "Review proposals" })).toBeVisible();
    expect(mocks.createReview).toHaveBeenCalledWith(expect.objectContaining({ classroomId: ids.classroom, subjectId: ids.subject, file: image }));
    expect(mocks.saveBulk).not.toHaveBeenCalled();
    expect(mocks.confirmReview).not.toHaveBeenCalled();
    expect(screen.getByText("Yogesh Pandey")).toBeVisible();
    expect(screen.getByText("Roll 101")).toBeVisible();
    expect(screen.queryByText(ids.student)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Confirm reviewed attendance" }));
    await waitFor(() => expect(mocks.confirmReview).toHaveBeenCalledWith("review-found", [
      { student_profile_id: ids.student, status: "present" },
    ]));
  });

  it("keeps unknown faces and missed roster students unmarked until the teacher edits them", async () => {
    mocks.createReview.mockResolvedValue({
      review_id: "review-unknown",
      classroom_id: ids.classroom,
      subject_id: ids.subject,
      attendance_date: "2026-08-16",
      face_count: 1,
      proposals: [{ attempt_id: "attempt-unknown", face_index: 0, decision: "unknown", matched_student_profile_id: null, best_similarity: 0.4, is_duplicate: false }],
    });
    await submitImage();

    const attendanceGroup = await screen.findByRole("group", {
      name: "Attendance for Yogesh Pandey, roll 101",
    });
    expect(within(attendanceGroup).getByRole("button", { name: "unmarked" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Confirm reviewed attendance" })).toBeDisabled();
    await userEvent.click(within(attendanceGroup).getByRole("button", { name: "present" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm reviewed attendance" }));
    await waitFor(() => expect(mocks.confirmReview).toHaveBeenCalledWith("review-unknown", [
      { student_profile_id: ids.student, status: "present" },
    ]));
    expect(mocks.getRoster).toHaveBeenCalledWith({ classroomId: ids.classroom, subjectId: ids.subject });
    expect(await screen.findByText("Reviewed attendance saved.")).toBeVisible();
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
