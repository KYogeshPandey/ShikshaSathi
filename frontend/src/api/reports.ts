import { apiClient } from "./client";
import { withQuery } from "./params";
import type {
  AttendanceReport,
  DefaultersReport,
  LeaderboardReport,
} from "../types/domain";

export interface ReportFilters {
  classroomId: string;
  subjectId: string;
  month?: string;
  dateFrom?: string;
  dateTo?: string;
  studentProfileId?: string;
  threshold?: number;
}

function reportPath(
  path: string,
  filters: ReportFilters,
  options: { student?: boolean; threshold?: boolean } = {},
): string {
  return withQuery(path, {
    classroom_id: filters.classroomId,
    subject_id: filters.subjectId,
    month: filters.month,
    date_from: filters.dateFrom,
    date_to: filters.dateTo,
    student_profile_id: options.student ? filters.studentProfileId : undefined,
    threshold: options.threshold ? filters.threshold : undefined,
  });
}

export const reportsApi = {
  getAttendance: (filters: ReportFilters) =>
    apiClient.get<AttendanceReport>(reportPath("/reports/attendance", filters, { student: true })),
  getDefaulters: (filters: ReportFilters) =>
    apiClient.get<DefaultersReport>(
      reportPath("/reports/defaulters", filters, { threshold: true }),
    ),
  getLeaderboard: (filters: ReportFilters) =>
    apiClient.get<LeaderboardReport>(reportPath("/reports/leaderboard", filters)),
  downloadAttendance: (format: "csv" | "pdf", filters: ReportFilters) =>
    apiClient.download(
      reportPath(`/reports/attendance/export.${format}`, filters, { student: true }),
    ),
};
