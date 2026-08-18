import { apiClient } from "./client";
import { withQuery } from "./params";
import type {
  Classroom,
  ClassroomCreate,
  ClassroomUpdate,
  Page,
  Subject,
  SubjectCreate,
  SubjectUpdate,
  TeacherAssignment,
  TeacherAssignmentCreate,
  TimetableEntry,
  TimetableEntryCreate,
  TimetableEntryUpdate,
} from "../types/domain";

interface ListOptions {
  includeInactive?: boolean;
  limit?: number;
  offset?: number;
}

function listPath(path: string, options: ListOptions = {}): string {
  return withQuery(path, {
    include_inactive: options.includeInactive,
    limit: options.limit ?? 100,
    offset: options.offset ?? 0,
  });
}

export const academicsApi = {
  listClassrooms: (options?: ListOptions) =>
    apiClient.get<Page<Classroom>>(listPath("/classrooms", options)),
  createClassroom: (payload: ClassroomCreate) =>
    apiClient.post<Classroom>("/classrooms", payload),
  updateClassroom: (id: string, payload: ClassroomUpdate) =>
    apiClient.patch<Classroom>(`/classrooms/${id}`, payload),
  deactivateClassroom: (id: string) => apiClient.delete<Classroom>(`/classrooms/${id}`),

  listSubjects: (options?: ListOptions) =>
    apiClient.get<Page<Subject>>(listPath("/subjects", options)),
  createSubject: (payload: SubjectCreate) => apiClient.post<Subject>("/subjects", payload),
  updateSubject: (id: string, payload: SubjectUpdate) =>
    apiClient.patch<Subject>(`/subjects/${id}`, payload),
  deactivateSubject: (id: string) => apiClient.delete<Subject>(`/subjects/${id}`),

  listAssignments: (options?: ListOptions) =>
    apiClient.get<Page<TeacherAssignment>>(listPath("/teacher-assignments", options)),
  createAssignment: (payload: TeacherAssignmentCreate) =>
    apiClient.post<TeacherAssignment>("/teacher-assignments", payload),
  updateAssignment: (id: string, isActive: boolean) =>
    apiClient.patch<TeacherAssignment>(`/teacher-assignments/${id}`, {
      is_active: isActive,
    }),
  deactivateAssignment: (id: string) =>
    apiClient.delete<TeacherAssignment>(`/teacher-assignments/${id}`),

  listTimetable: (options?: ListOptions) =>
    apiClient.get<Page<TimetableEntry>>(listPath("/timetable-entries", options)),
  createTimetable: (payload: TimetableEntryCreate) =>
    apiClient.post<TimetableEntry>("/timetable-entries", payload),
  updateTimetable: (id: string, payload: TimetableEntryUpdate) =>
    apiClient.patch<TimetableEntry>(`/timetable-entries/${id}`, payload),
  deactivateTimetable: (id: string) =>
    apiClient.delete<TimetableEntry>(`/timetable-entries/${id}`),
};
