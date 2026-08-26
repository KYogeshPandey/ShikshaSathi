import { apiClient } from "./client";
import { withQuery } from "./params";
import type {
  Page,
  StudentMembershipUpdate,
  StudentProfile,
  StudentProfileCreate,
  StudentProfileUpdate,
  TeacherProfile,
  TeacherProfileCreate,
  TeacherProfileUpdate,
} from "../types/domain";

interface ListOptions {
  classroomId?: string;
  includeInactive?: boolean;
  limit?: number;
  offset?: number;
}

function listPath(path: string, options: ListOptions = {}): string {
  return withQuery(path, {
    classroom_id: options.classroomId,
    include_inactive: options.includeInactive,
    limit: options.limit ?? 100,
    offset: options.offset ?? 0,
  });
}

export const profilesApi = {
  listTeachers: (options?: ListOptions) =>
    apiClient.get<Page<TeacherProfile>>(listPath("/teacher-profiles", options)),
  getMyTeacherProfile: () => apiClient.get<TeacherProfile>("/teacher-profiles/me"),
  createTeacher: (payload: TeacherProfileCreate) =>
    apiClient.post<TeacherProfile>("/teacher-profiles", payload),
  updateTeacher: (id: string, payload: TeacherProfileUpdate) =>
    apiClient.patch<TeacherProfile>(`/teacher-profiles/${id}`, payload),
  deactivateTeacher: (id: string) =>
    apiClient.delete<TeacherProfile>(`/teacher-profiles/${id}`),

  listStudents: (options?: ListOptions) =>
    apiClient.get<Page<StudentProfile>>(listPath("/student-profiles", options)),
  getMyStudentProfile: () => apiClient.get<StudentProfile>("/student-profiles/me"),
  createStudent: (payload: StudentProfileCreate) =>
    apiClient.post<StudentProfile>("/student-profiles", payload),
  updateStudent: (id: string, payload: StudentProfileUpdate) =>
    apiClient.patch<StudentProfile>(`/student-profiles/${id}`, payload),
  updateMembership: (id: string, payload: StudentMembershipUpdate) =>
    apiClient.put<StudentProfile>(`/student-profiles/${id}/classroom-membership`, payload),
  deactivateStudent: (id: string) =>
    apiClient.delete<StudentProfile>(`/student-profiles/${id}`),
};
