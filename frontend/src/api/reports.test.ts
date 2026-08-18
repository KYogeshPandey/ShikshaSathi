import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "./client";
import { reportsApi } from "./reports";

afterEach(() => vi.restoreAllMocks());

describe("Phase 8 report API contracts", () => {
  it("maps typed filters to the exact report and export query parameters", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({});
    const download = vi.spyOn(apiClient, "download").mockResolvedValue({
      blob: new Blob(),
      contentType: "text/csv",
      filename: "report.csv",
    });
    const filters = {
      classroomId: "classroom-id",
      subjectId: "subject-id",
      month: "2026-08",
      studentProfileId: "student-id",
      threshold: 72.5,
    };

    await reportsApi.getAttendance(filters);
    await reportsApi.getDefaulters(filters);
    await reportsApi.getLeaderboard(filters);
    await reportsApi.downloadAttendance("csv", filters);

    expect(get.mock.calls[0]?.[0]).toBe(
      "/reports/attendance?classroom_id=classroom-id&subject_id=subject-id&month=2026-08&student_profile_id=student-id",
    );
    expect(get.mock.calls[1]?.[0]).toBe(
      "/reports/defaulters?classroom_id=classroom-id&subject_id=subject-id&month=2026-08&threshold=72.5",
    );
    expect(get.mock.calls[2]?.[0]).toBe(
      "/reports/leaderboard?classroom_id=classroom-id&subject_id=subject-id&month=2026-08",
    );
    expect(download).toHaveBeenCalledWith(
      "/reports/attendance/export.csv?classroom_id=classroom-id&subject_id=subject-id&month=2026-08&student_profile_id=student-id",
    );
  });

  it("sends an explicit bounded date range without a month", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({});
    await reportsApi.getAttendance({
      classroomId: "classroom-id",
      subjectId: "subject-id",
      dateFrom: "2026-08-01",
      dateTo: "2026-08-16",
    });
    expect(get.mock.calls[0]?.[0]).toBe(
      "/reports/attendance?classroom_id=classroom-id&subject_id=subject-id&date_from=2026-08-01&date_to=2026-08-16",
    );
  });
});
