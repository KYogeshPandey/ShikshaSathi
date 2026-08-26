import { apiClient } from "./client";
import { withQuery } from "./params";
import type {
  AttendanceBulkSaveResult,
  AttendanceRecoveryPlan,
  AttendanceRecoveryPlanRequest,
  AttendanceRecord,
  AttendanceRosterStudent,
  BulkAttendanceRequest,
  DailyAttendanceResponse,
  Page,
  StudentSelfStats,
} from "../types/domain";

interface Scope {
  classroomId: string;
  subjectId: string;
}

interface DetailFilters {
  classroomId?: string;
  subjectId?: string;
  dateFrom?: string;
  dateTo?: string;
  status?: "present" | "absent";
  offset?: number;
}

export const attendanceApi = {
  getRoster: ({ classroomId, subjectId }: Scope) =>
    apiClient.get<AttendanceRosterStudent[]>(
      withQuery("/attendance/roster", {
        classroom_id: classroomId,
        subject_id: subjectId,
      }),
    ),
  getDaily: ({ classroomId, subjectId }: Scope, attendanceDate: string) =>
    apiClient.get<DailyAttendanceResponse>(
      withQuery("/attendance/daily", {
        classroom_id: classroomId,
        subject_id: subjectId,
        attendance_date: attendanceDate,
      }),
    ),
  saveBulk: (payload: BulkAttendanceRequest) =>
    apiClient.post<AttendanceBulkSaveResult>("/attendance/bulk", payload),
  getMyDetail: (filters: DetailFilters = {}) =>
    apiClient.get<Page<AttendanceRecord>>(
      withQuery("/attendance/me/detail", {
        classroom_id: filters.classroomId,
        subject_id: filters.subjectId,
        date_from: filters.dateFrom,
        date_to: filters.dateTo,
        status: filters.status,
        limit: 100,
        offset: filters.offset ?? 0,
      }),
    ),
  getMyStats: (filters: DetailFilters = {}) =>
    apiClient.get<StudentSelfStats>(
      withQuery("/attendance/me/stats", {
        classroom_id: filters.classroomId,
        subject_id: filters.subjectId,
        date_from: filters.dateFrom,
        date_to: filters.dateTo,
      }),
    ),
  getRecoveryPlan: (payload: AttendanceRecoveryPlanRequest) =>
    apiClient.post<AttendanceRecoveryPlan>("/attendance/me/recovery-plan", payload),
};
