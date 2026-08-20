import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "./client";
import { attendanceApi } from "./attendance";
import { recognitionApi } from "./recognition";

afterEach(() => vi.restoreAllMocks());

describe("Application API contracts", () => {
  it("uses the teacher-authorized roster scope and student self-service endpoints", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({});

    await attendanceApi.getRoster({ classroomId: "classroom-id", subjectId: "subject-id" });
    await attendanceApi.getMyDetail({ status: "present", offset: 100 });
    await attendanceApi.getMyStats({ dateFrom: "2026-08-01", dateTo: "2026-08-16" });

    expect(get.mock.calls[0]?.[0]).toBe("/attendance/roster?classroom_id=classroom-id&subject_id=subject-id");
    expect(get.mock.calls[1]?.[0]).toContain("/attendance/me/detail?");
    expect(get.mock.calls[1]?.[0]).toContain("status=present");
    expect(get.mock.calls[1]?.[0]).toContain("offset=100");
    expect(get.mock.calls[2]?.[0]).toContain("/attendance/me/stats?");
    expect(get.mock.calls[2]?.[0]).toContain("date_from=2026-08-01");
  });

  it("submits the exact recognition multipart fields", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ attempt_id: "attempt-id" });
    const image = new File(["image"], "face.jpg", { type: "image/jpeg" });

    await recognitionApi.createAttempt({
      classroomId: "classroom-id",
      subjectId: "subject-id",
      attendanceDate: "2026-08-16",
      file: image,
    });

    expect(post.mock.calls[0]?.[0]).toBe("/face-recognition/attendance/attempts");
    const body = post.mock.calls[0]?.[1];
    expect(body).toBeInstanceOf(FormData);
    const form = body as FormData;
    expect(form.get("classroom_id")).toBe("classroom-id");
    expect(form.get("subject_id")).toBe("subject-id");
    expect(form.get("attendance_date")).toBe("2026-08-16");
    expect(form.get("file")).toBe(image);
    expect([...form.keys()].sort()).toEqual(["attendance_date", "classroom_id", "file", "subject_id"]);
  });

  it("confirms a recognition attempt with only the selected roster profile ID", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({});
    await recognitionApi.confirm("attempt-id", "student-profile-id");
    expect(post).toHaveBeenCalledWith(
      "/face-recognition/attendance/attempts/attempt-id/confirm",
      { student_profile_id: "student-profile-id" },
    );
  });
});
