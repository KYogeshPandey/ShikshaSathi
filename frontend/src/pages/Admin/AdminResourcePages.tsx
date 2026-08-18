import { useCallback } from "react";
import { z } from "zod";
import { academicsApi } from "../../api/academics";
import { profilesApi } from "../../api/profiles";
import { queryKeys } from "../../api/queryKeys";
import {
  AdminCrudPage,
  type CrudColumn,
  type CrudField,
  type CrudFormValues,
} from "../../components/AdminCrudPage";
import type {
  Classroom,
  DayOfWeek,
  StudentProfile,
  Subject,
  TeacherAssignment,
  TeacherProfile,
  TimetableEntry,
} from "../../types/domain";

const uuid = z.string().uuid("Enter a valid UUID.");
const optionalUuid = uuid.or(z.literal(""));
const optionalText = z.string().max(255);
const booleanOptions = [
  { label: "Yes", value: "true" },
  { label: "No", value: "false" },
] as const;
const dayOptions = [
  "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
].map((value) => ({ label: value[0].toUpperCase() + value.slice(1), value }));

function optional(value: string): string | null {
  const trimmed = value.trim();
  return trimmed || null;
}

export function AdminClassroomsPage() {
  const toFormValues = useCallback((item: Classroom) => ({
    name: item.name,
    code: item.code,
    grade_level: item.grade_level ?? "",
    section: item.section ?? "",
  }), []);
  const fields: readonly CrudField[] = [
    { name: "name", label: "Classroom name" },
    { name: "code", label: "Code", createOnly: true },
    { name: "grade_level", label: "Grade level" },
    { name: "section", label: "Section" },
  ];
  const columns: ReadonlyArray<CrudColumn<Classroom>> = [
    { label: "Name", render: (item) => item.name },
    { label: "Code", render: (item) => item.code },
    { label: "Grade / section", render: (item) => [item.grade_level, item.section].filter(Boolean).join(" / ") || "—" },
    { label: "Status", render: (item) => item.is_active ? "Active" : "Inactive" },
  ];
  return <AdminCrudPage title="Classrooms" description="Manage active classroom records used throughout assignments and attendance." queryKey={queryKeys.classrooms} fields={fields} columns={columns} emptyValues={{ name: "", code: "", grade_level: "", section: "" }} schema={z.object({ name: z.string().trim().min(1), code: z.string().trim().min(1), grade_level: optionalText, section: optionalText })} load={(offset) => academicsApi.listClassrooms({ includeInactive: true, offset })} create={(v) => academicsApi.createClassroom({ name: v.name, code: v.code, grade_level: optional(v.grade_level), section: optional(v.section) })} update={(id, v) => academicsApi.updateClassroom(id, { name: v.name, grade_level: optional(v.grade_level), section: optional(v.section) })} deactivate={academicsApi.deactivateClassroom} toFormValues={toFormValues} />;
}

export function AdminSubjectsPage() {
  const toFormValues = useCallback((item: Subject) => ({ name: item.name, code: item.code, is_elective: String(item.is_elective) }), []);
  return <AdminCrudPage title="Subjects" description="Manage subjects and elective status." queryKey={queryKeys.subjects} fields={[{ name: "name", label: "Subject name" }, { name: "code", label: "Code", createOnly: true }, { name: "is_elective", label: "Elective", type: "select", options: booleanOptions }]} columns={[{ label: "Name", render: (item: Subject) => item.name }, { label: "Code", render: (item: Subject) => item.code }, { label: "Elective", render: (item: Subject) => item.is_elective ? "Yes" : "No" }, { label: "Status", render: (item: Subject) => item.is_active ? "Active" : "Inactive" }]} emptyValues={{ name: "", code: "", is_elective: "false" }} schema={z.object({ name: z.string().trim().min(1), code: z.string().trim().min(1), is_elective: z.enum(["true", "false"]) })} load={(offset) => academicsApi.listSubjects({ includeInactive: true, offset })} create={(v) => academicsApi.createSubject({ name: v.name, code: v.code, is_elective: v.is_elective === "true" })} update={(id, v) => academicsApi.updateSubject(id, { name: v.name, is_elective: v.is_elective === "true" })} deactivate={academicsApi.deactivateSubject} toFormValues={toFormValues} />;
}

export function AdminTeachersPage() {
  const toFormValues = useCallback((item: TeacherProfile) => ({ user_id: item.user_id, employee_code: item.employee_code ?? "", phone_number: item.phone_number ?? "" }), []);
  return <AdminCrudPage title="Teachers" description="Create and maintain teacher profiles linked to existing teacher user accounts." queryKey={queryKeys.teachers} fields={[{ name: "user_id", label: "Teacher user UUID", createOnly: true }, { name: "employee_code", label: "Employee code" }, { name: "phone_number", label: "Phone number" }]} columns={[{ label: "Employee code", render: (item: TeacherProfile) => item.employee_code ?? "—" }, { label: "User UUID", render: (item: TeacherProfile) => item.user_id }, { label: "Phone", render: (item: TeacherProfile) => item.phone_number ?? "—" }, { label: "Status", render: (item: TeacherProfile) => item.is_active ? "Active" : "Inactive" }]} emptyValues={{ user_id: "", employee_code: "", phone_number: "" }} schema={z.object({ user_id: uuid, employee_code: z.string().max(64), phone_number: z.string().max(32) })} load={(offset) => profilesApi.listTeachers({ includeInactive: true, offset })} create={(v) => profilesApi.createTeacher({ user_id: v.user_id, employee_code: optional(v.employee_code), phone_number: optional(v.phone_number) })} update={(id, v) => profilesApi.updateTeacher(id, { employee_code: optional(v.employee_code), phone_number: optional(v.phone_number) })} deactivate={profilesApi.deactivateTeacher} toFormValues={toFormValues} />;
}

export function AdminStudentsPage() {
  const toFormValues = useCallback((item: StudentProfile) => ({ user_id: item.user_id, classroom_id: item.classroom_id ?? "", roll_number: item.roll_number ?? "" }), []);
  const updateStudent = async (id: string, values: CrudFormValues) => profilesApi.updateMembership(id, { classroom_id: optional(values.classroom_id), roll_number: optional(values.roll_number) });
  return <AdminCrudPage title="Students" description="Manage student profiles and their current classroom membership." queryKey={queryKeys.students} fields={[{ name: "user_id", label: "Student user UUID", createOnly: true }, { name: "classroom_id", label: "Classroom UUID" }, { name: "roll_number", label: "Roll number" }]} columns={[{ label: "Roll number", render: (item: StudentProfile) => item.roll_number ?? "—" }, { label: "Classroom UUID", render: (item: StudentProfile) => item.classroom_id ?? "Unassigned" }, { label: "User UUID", render: (item: StudentProfile) => item.user_id }, { label: "Status", render: (item: StudentProfile) => item.is_active ? "Active" : "Inactive" }]} emptyValues={{ user_id: "", classroom_id: "", roll_number: "" }} schema={z.object({ user_id: uuid, classroom_id: optionalUuid, roll_number: z.string().max(32) }).refine((v) => Boolean(v.classroom_id) || !v.roll_number, { message: "A roll number requires a classroom.", path: ["roll_number"] })} load={(offset) => profilesApi.listStudents({ includeInactive: true, offset })} create={(v) => profilesApi.createStudent({ user_id: v.user_id, classroom_id: optional(v.classroom_id), roll_number: optional(v.roll_number) })} update={updateStudent} deactivate={profilesApi.deactivateStudent} toFormValues={toFormValues} />;
}

export function AdminAssignmentsPage() {
  const toFormValues = useCallback((item: TeacherAssignment) => ({ teacher_profile_id: item.teacher_profile_id, classroom_id: item.classroom_id, subject_id: item.subject_id, is_active: String(item.is_active) }), []);
  return <AdminCrudPage title="Teacher assignments" description="Authorize exact teacher, classroom, and subject scopes." queryKey={queryKeys.assignments} fields={[{ name: "teacher_profile_id", label: "Teacher profile UUID", createOnly: true }, { name: "classroom_id", label: "Classroom UUID", createOnly: true }, { name: "subject_id", label: "Subject UUID", createOnly: true }, { name: "is_active", label: "Active", type: "select", options: booleanOptions }]} columns={[{ label: "Teacher", render: (item: TeacherAssignment) => item.teacher_profile_id }, { label: "Classroom", render: (item: TeacherAssignment) => item.classroom_id }, { label: "Subject", render: (item: TeacherAssignment) => item.subject_id }, { label: "Status", render: (item: TeacherAssignment) => item.is_active ? "Active" : "Inactive" }]} emptyValues={{ teacher_profile_id: "", classroom_id: "", subject_id: "", is_active: "true" }} schema={z.object({ teacher_profile_id: uuid, classroom_id: uuid, subject_id: uuid, is_active: z.enum(["true", "false"]) })} load={(offset) => academicsApi.listAssignments({ includeInactive: true, offset })} create={(v) => academicsApi.createAssignment({ teacher_profile_id: v.teacher_profile_id, classroom_id: v.classroom_id, subject_id: v.subject_id })} update={(id, v) => academicsApi.updateAssignment(id, v.is_active === "true")} deactivate={academicsApi.deactivateAssignment} toFormValues={toFormValues} />;
}

export function AdminTimetablePage() {
  const toFormValues = useCallback((item: TimetableEntry) => ({ classroom_id: item.classroom_id, subject_id: item.subject_id, teacher_profile_id: item.teacher_profile_id, day_of_week: item.day_of_week, start_time: item.start_time.slice(0, 5), end_time: item.end_time.slice(0, 5) }), []);
  const valuesToPayload = (v: CrudFormValues) => ({ classroom_id: v.classroom_id, subject_id: v.subject_id, teacher_profile_id: v.teacher_profile_id, day_of_week: v.day_of_week as DayOfWeek, start_time: v.start_time, end_time: v.end_time });
  return <AdminCrudPage title="Timetable entries" description="Maintain assignment-backed classroom timetable slots." queryKey={queryKeys.timetable} fields={[{ name: "classroom_id", label: "Classroom UUID" }, { name: "subject_id", label: "Subject UUID" }, { name: "teacher_profile_id", label: "Teacher profile UUID" }, { name: "day_of_week", label: "Day", type: "select", options: dayOptions }, { name: "start_time", label: "Start time", type: "time" }, { name: "end_time", label: "End time", type: "time" }]} columns={[{ label: "Day", render: (item: TimetableEntry) => item.day_of_week }, { label: "Time", render: (item: TimetableEntry) => `${item.start_time}–${item.end_time}` }, { label: "Classroom", render: (item: TimetableEntry) => item.classroom_id }, { label: "Subject", render: (item: TimetableEntry) => item.subject_id }, { label: "Status", render: (item: TimetableEntry) => item.is_active ? "Active" : "Inactive" }]} emptyValues={{ classroom_id: "", subject_id: "", teacher_profile_id: "", day_of_week: "monday", start_time: "08:00", end_time: "09:00" }} schema={z.object({ classroom_id: uuid, subject_id: uuid, teacher_profile_id: uuid, day_of_week: z.enum(["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]), start_time: z.string().min(1), end_time: z.string().min(1) }).refine((v) => v.start_time < v.end_time, { message: "End time must be after start time.", path: ["end_time"] })} load={(offset) => academicsApi.listTimetable({ includeInactive: true, offset })} create={(v) => academicsApi.createTimetable(valuesToPayload(v))} update={(id, v) => academicsApi.updateTimetable(id, valuesToPayload(v))} deactivate={academicsApi.deactivateTimetable} toFormValues={toFormValues} />;
}
