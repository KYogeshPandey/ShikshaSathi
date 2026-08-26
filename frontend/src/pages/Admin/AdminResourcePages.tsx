import { useQuery } from "@tanstack/react-query";
import { useCallback, type ReactNode } from "react";
import { z } from "zod";
import { academicsApi } from "../../api/academics";
import { apiErrorMessage } from "../../api/errorMessage";
import { profilesApi } from "../../api/profiles";
import { queryKeys } from "../../api/queryKeys";
import { usersApi } from "../../api/users";
import {
  AdminCrudPage,
  type CrudColumn,
  type CrudField,
  type CrudFormValues,
} from "../../components/AdminCrudPage";
import { SlowRequestNotice } from "../../components/SlowRequestNotice";
import type {
  Classroom,
  DayOfWeek,
  StudentProfile,
  Subject,
  TeacherAssignment,
  TeacherProfile,
  TimetableEntry,
  UserDirectoryEntry,
} from "../../types/domain";

const uuid = z.string().uuid("Choose a valid record.");
const optionalUuid = uuid.or(z.literal(""));
const optionalText = z.string().max(255);
const booleanOptions = [
  { label: "Yes", value: "true" },
  { label: "No", value: "false" },
] as const;
const dayOptions = [
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
].map((value) => ({ label: value[0].toUpperCase() + value.slice(1), value }));

function optional(value: string): string | null {
  const trimmed = value.trim();
  return trimmed || null;
}

function userLabel(user: UserDirectoryEntry): string {
  return `${user.full_name} — ${user.email}`;
}

function teacherLabel(
  profile: TeacherProfile,
  users: ReadonlyMap<string, UserDirectoryEntry>,
): string {
  const user = users.get(profile.user_id);
  return user?.full_name ?? "Teacher account unavailable";
}

function lookupOptions<T extends { id: string; is_active: boolean }>(
  items: readonly T[],
  label: (item: T) => string,
  emptyLabel: string,
): ReadonlyArray<{ label: string; value: string }> {
  const options = items
    .filter((item) => item.is_active)
    .map((item) => ({ label: label(item), value: item.id }));
  return options.length ? options : [{ label: emptyLabel, value: "" }];
}

function ReferenceState({
  title,
  pending,
  error,
  children,
}: {
  title: string;
  pending: boolean;
  error: Error | null;
  children: ReactNode;
}) {
  if (pending) {
    return (
      <section className="page-stack">
        <div className="page-heading"><h1>{title}</h1></div>
        <p className="empty-state">Loading available records…</p>
        <SlowRequestNotice />
      </section>
    );
  }
  if (error) {
    return (
      <section className="page-stack">
        <div className="page-heading"><h1>{title}</h1></div>
        <p className="error-message" role="alert">{apiErrorMessage(error)}</p>
      </section>
    );
  }
  return children;
}

export function AdminClassroomsPage() {
  const toFormValues = useCallback(
    (item: Classroom) => ({
      name: item.name,
      code: item.code,
      grade_level: item.grade_level ?? "",
      section: item.section ?? "",
    }),
    [],
  );
  const fields: readonly CrudField[] = [
    { name: "name", label: "Classroom name" },
    { name: "code", label: "Code", createOnly: true },
    { name: "grade_level", label: "Grade level" },
    { name: "section", label: "Section" },
  ];
  const columns: ReadonlyArray<CrudColumn<Classroom>> = [
    { label: "Name", render: (item) => item.name },
    { label: "Code", render: (item) => item.code },
    {
      label: "Grade / section",
      render: (item) => [item.grade_level, item.section].filter(Boolean).join(" / ") || "—",
    },
    { label: "Status", render: (item) => (item.is_active ? "Active" : "Inactive") },
  ];
  return (
    <AdminCrudPage
      title="Classrooms"
      description="Manage active classroom records used throughout assignments and attendance."
      queryKey={queryKeys.classrooms}
      fields={fields}
      columns={columns}
      emptyValues={{ name: "", code: "", grade_level: "", section: "" }}
      schema={z.object({
        name: z.string().trim().min(1),
        code: z.string().trim().min(1),
        grade_level: optionalText,
        section: optionalText,
      })}
      load={(offset) => academicsApi.listClassrooms({ includeInactive: true, offset })}
      create={(values) =>
        academicsApi.createClassroom({
          name: values.name,
          code: values.code,
          grade_level: optional(values.grade_level),
          section: optional(values.section),
        })
      }
      update={(id, values) =>
        academicsApi.updateClassroom(id, {
          name: values.name,
          grade_level: optional(values.grade_level),
          section: optional(values.section),
        })
      }
      deactivate={academicsApi.deactivateClassroom}
      toFormValues={toFormValues}
    />
  );
}

export function AdminSubjectsPage() {
  const toFormValues = useCallback(
    (item: Subject) => ({
      name: item.name,
      code: item.code,
      is_elective: String(item.is_elective),
    }),
    [],
  );
  return (
    <AdminCrudPage
      title="Subjects"
      description="Manage subjects and elective status."
      queryKey={queryKeys.subjects}
      fields={[
        { name: "name", label: "Subject name" },
        { name: "code", label: "Code", createOnly: true },
        { name: "is_elective", label: "Elective", type: "select", options: booleanOptions },
      ]}
      columns={[
        { label: "Name", render: (item: Subject) => item.name },
        { label: "Code", render: (item: Subject) => item.code },
        { label: "Elective", render: (item: Subject) => (item.is_elective ? "Yes" : "No") },
        { label: "Status", render: (item: Subject) => (item.is_active ? "Active" : "Inactive") },
      ]}
      emptyValues={{ name: "", code: "", is_elective: "false" }}
      schema={z.object({
        name: z.string().trim().min(1),
        code: z.string().trim().min(1),
        is_elective: z.enum(["true", "false"]),
      })}
      load={(offset) => academicsApi.listSubjects({ includeInactive: true, offset })}
      create={(values) =>
        academicsApi.createSubject({
          name: values.name,
          code: values.code,
          is_elective: values.is_elective === "true",
        })
      }
      update={(id, values) =>
        academicsApi.updateSubject(id, {
          name: values.name,
          is_elective: values.is_elective === "true",
        })
      }
      deactivate={academicsApi.deactivateSubject}
      toFormValues={toFormValues}
    />
  );
}

export function AdminTeachersPage() {
  const users = useQuery({
    queryKey: queryKeys.users("teacher"),
    queryFn: () => usersApi.list("teacher", { includeInactive: true }),
  });
  const userMap = new Map(users.data?.items.map((user) => [user.id, user]) ?? []);
  const options = lookupOptions(users.data?.items ?? [], userLabel, "No teacher accounts available");

  return (
    <ReferenceState title="Teachers" pending={users.isPending} error={users.error}>
      <AdminCrudPage
        title="Teachers"
        description="Create and maintain teacher profiles linked to existing teacher accounts."
        queryKey={queryKeys.teachers}
        fields={[
          { name: "user_id", label: "Teacher", type: "select", options, createOnly: true },
          { name: "employee_code", label: "Employee code" },
          { name: "phone_number", label: "Phone number" },
        ]}
        columns={[
          { label: "Teacher", render: (item: TeacherProfile) => teacherLabel(item, userMap) },
          { label: "Employee code", render: (item: TeacherProfile) => item.employee_code ?? "—" },
          { label: "Phone", render: (item: TeacherProfile) => item.phone_number ?? "—" },
          { label: "Status", render: (item: TeacherProfile) => (item.is_active ? "Active" : "Inactive") },
        ]}
        emptyValues={{ user_id: options[0]?.value ?? "", employee_code: "", phone_number: "" }}
        schema={z.object({
          user_id: uuid,
          employee_code: z.string().max(64),
          phone_number: z.string().max(32),
        })}
        load={(offset) => profilesApi.listTeachers({ includeInactive: true, offset })}
        create={(values) =>
          profilesApi.createTeacher({
            user_id: values.user_id,
            employee_code: optional(values.employee_code),
            phone_number: optional(values.phone_number),
          })
        }
        update={(id, values) =>
          profilesApi.updateTeacher(id, {
            employee_code: optional(values.employee_code),
            phone_number: optional(values.phone_number),
          })
        }
        deactivate={profilesApi.deactivateTeacher}
        toFormValues={(item) => ({
          user_id: item.user_id,
          employee_code: item.employee_code ?? "",
          phone_number: item.phone_number ?? "",
        })}
      />
    </ReferenceState>
  );
}

export function AdminStudentsPage() {
  const users = useQuery({
    queryKey: queryKeys.users("student"),
    queryFn: () => usersApi.list("student", { includeInactive: true }),
  });
  const classrooms = useQuery({
    queryKey: queryKeys.classrooms,
    queryFn: () => academicsApi.listClassrooms({ includeInactive: true }),
  });
  const userMap = new Map(users.data?.items.map((user) => [user.id, user]) ?? []);
  const classroomMap = new Map(
    classrooms.data?.items.map((classroom) => [classroom.id, classroom]) ?? [],
  );
  const userOptions = lookupOptions(
    users.data?.items ?? [],
    userLabel,
    "No student accounts available",
  );
  const classroomOptions = [
    { label: "Unassigned", value: "" },
    ...lookupOptions(
      classrooms.data?.items ?? [],
      (classroom) => classroom.name,
      "No classrooms available",
    ).filter((option) => option.value),
  ];
  const error = users.error ?? classrooms.error;

  return (
    <ReferenceState
      title="Students"
      pending={users.isPending || classrooms.isPending}
      error={error}
    >
      <AdminCrudPage
        title="Students"
        description="Manage student profiles and their current classroom membership."
        queryKey={queryKeys.students}
        fields={[
          { name: "user_id", label: "Student", type: "select", options: userOptions, createOnly: true },
          { name: "classroom_id", label: "Classroom", type: "select", options: classroomOptions },
          { name: "roll_number", label: "Roll number" },
        ]}
        columns={[
          {
            label: "Student",
            render: (item: StudentProfile) =>
              userMap.get(item.user_id)?.full_name ?? "Student account unavailable",
          },
          { label: "Roll", render: (item: StudentProfile) => item.roll_number ?? "—" },
          {
            label: "Classroom",
            render: (item: StudentProfile) =>
              item.classroom_id
                ? classroomMap.get(item.classroom_id)?.name ?? "Classroom unavailable"
                : "Unassigned",
          },
          { label: "Status", render: (item: StudentProfile) => (item.is_active ? "Active" : "Inactive") },
        ]}
        emptyValues={{
          user_id: userOptions[0]?.value ?? "",
          classroom_id: "",
          roll_number: "",
        }}
        schema={z
          .object({
            user_id: uuid,
            classroom_id: optionalUuid,
            roll_number: z.string().max(32),
          })
          .refine((values) => Boolean(values.classroom_id) || !values.roll_number, {
            message: "A roll number requires a classroom.",
            path: ["roll_number"],
          })}
        load={(offset) => profilesApi.listStudents({ includeInactive: true, offset })}
        create={(values) =>
          profilesApi.createStudent({
            user_id: values.user_id,
            classroom_id: optional(values.classroom_id),
            roll_number: optional(values.roll_number),
          })
        }
        update={(id, values) =>
          profilesApi.updateMembership(id, {
            classroom_id: optional(values.classroom_id),
            roll_number: optional(values.roll_number),
          })
        }
        deactivate={profilesApi.deactivateStudent}
        toFormValues={(item) => ({
          user_id: item.user_id,
          classroom_id: item.classroom_id ?? "",
          roll_number: item.roll_number ?? "",
        })}
      />
    </ReferenceState>
  );
}

function useAcademicReferenceData() {
  const users = useQuery({
    queryKey: queryKeys.users("teacher"),
    queryFn: () => usersApi.list("teacher", { includeInactive: true }),
  });
  const teachers = useQuery({
    queryKey: queryKeys.teachers,
    queryFn: () => profilesApi.listTeachers({ includeInactive: true }),
  });
  const classrooms = useQuery({
    queryKey: queryKeys.classrooms,
    queryFn: () => academicsApi.listClassrooms({ includeInactive: true }),
  });
  const subjects = useQuery({
    queryKey: queryKeys.subjects,
    queryFn: () => academicsApi.listSubjects({ includeInactive: true }),
  });
  return { users, teachers, classrooms, subjects };
}

export function AdminAssignmentsPage() {
  const references = useAcademicReferenceData();
  const userMap = new Map(references.users.data?.items.map((user) => [user.id, user]) ?? []);
  const teacherMap = new Map(
    references.teachers.data?.items.map((teacher) => [teacher.id, teacher]) ?? [],
  );
  const classroomMap = new Map(
    references.classrooms.data?.items.map((classroom) => [classroom.id, classroom]) ?? [],
  );
  const subjectMap = new Map(
    references.subjects.data?.items.map((subject) => [subject.id, subject]) ?? [],
  );
  const teacherOptions = lookupOptions(
    references.teachers.data?.items ?? [],
    (teacher) => teacherLabel(teacher, userMap),
    "No teacher profiles available",
  );
  const classroomOptions = lookupOptions(
    references.classrooms.data?.items ?? [],
    (classroom) => classroom.name,
    "No classrooms available",
  );
  const subjectOptions = lookupOptions(
    references.subjects.data?.items ?? [],
    (subject) => subject.name,
    "No subjects available",
  );
  const pending = Object.values(references).some((query) => query.isPending);
  const error = Object.values(references).map((query) => query.error).find(Boolean) ?? null;

  return (
    <ReferenceState title="Teacher assignments" pending={pending} error={error}>
      <AdminCrudPage
        title="Teacher assignments"
        description="Authorize exact teacher, classroom, and subject scopes."
        queryKey={queryKeys.assignments}
        fields={[
          { name: "teacher_profile_id", label: "Teacher", type: "select", options: teacherOptions, createOnly: true },
          { name: "classroom_id", label: "Classroom", type: "select", options: classroomOptions, createOnly: true },
          { name: "subject_id", label: "Subject", type: "select", options: subjectOptions, createOnly: true },
          { name: "is_active", label: "Active", type: "select", options: booleanOptions },
        ]}
        columns={[
          {
            label: "Teacher",
            render: (item: TeacherAssignment) => {
              const teacher = teacherMap.get(item.teacher_profile_id);
              return teacher ? teacherLabel(teacher, userMap) : "Teacher unavailable";
            },
          },
          {
            label: "Classroom",
            render: (item: TeacherAssignment) =>
              classroomMap.get(item.classroom_id)?.name ?? "Classroom unavailable",
          },
          {
            label: "Subject",
            render: (item: TeacherAssignment) =>
              subjectMap.get(item.subject_id)?.name ?? "Subject unavailable",
          },
          { label: "Status", render: (item: TeacherAssignment) => (item.is_active ? "Active" : "Inactive") },
        ]}
        emptyValues={{
          teacher_profile_id: teacherOptions[0]?.value ?? "",
          classroom_id: classroomOptions[0]?.value ?? "",
          subject_id: subjectOptions[0]?.value ?? "",
          is_active: "true",
        }}
        schema={z.object({
          teacher_profile_id: uuid,
          classroom_id: uuid,
          subject_id: uuid,
          is_active: z.enum(["true", "false"]),
        })}
        load={(offset) => academicsApi.listAssignments({ includeInactive: true, offset })}
        create={(values) =>
          academicsApi.createAssignment({
            teacher_profile_id: values.teacher_profile_id,
            classroom_id: values.classroom_id,
            subject_id: values.subject_id,
          })
        }
        update={(id, values) => academicsApi.updateAssignment(id, values.is_active === "true")}
        deactivate={academicsApi.deactivateAssignment}
        toFormValues={(item) => ({
          teacher_profile_id: item.teacher_profile_id,
          classroom_id: item.classroom_id,
          subject_id: item.subject_id,
          is_active: String(item.is_active),
        })}
      />
    </ReferenceState>
  );
}

export function AdminTimetablePage() {
  const references = useAcademicReferenceData();
  const userMap = new Map(references.users.data?.items.map((user) => [user.id, user]) ?? []);
  const teacherMap = new Map(
    references.teachers.data?.items.map((teacher) => [teacher.id, teacher]) ?? [],
  );
  const classroomMap = new Map(
    references.classrooms.data?.items.map((classroom) => [classroom.id, classroom]) ?? [],
  );
  const subjectMap = new Map(
    references.subjects.data?.items.map((subject) => [subject.id, subject]) ?? [],
  );
  const teacherOptions = lookupOptions(
    references.teachers.data?.items ?? [],
    (teacher) => teacherLabel(teacher, userMap),
    "No teacher profiles available",
  );
  const classroomOptions = lookupOptions(
    references.classrooms.data?.items ?? [],
    (classroom) => classroom.name,
    "No classrooms available",
  );
  const subjectOptions = lookupOptions(
    references.subjects.data?.items ?? [],
    (subject) => subject.name,
    "No subjects available",
  );
  const pending = Object.values(references).some((query) => query.isPending);
  const error = Object.values(references).map((query) => query.error).find(Boolean) ?? null;
  const valuesToPayload = (values: CrudFormValues) => ({
    classroom_id: values.classroom_id,
    subject_id: values.subject_id,
    teacher_profile_id: values.teacher_profile_id,
    day_of_week: values.day_of_week as DayOfWeek,
    start_time: values.start_time,
    end_time: values.end_time,
  });

  return (
    <ReferenceState title="Timetable entries" pending={pending} error={error}>
      <AdminCrudPage
        title="Timetable entries"
        description="Maintain assignment-backed classroom timetable slots."
        queryKey={queryKeys.timetable}
        fields={[
          { name: "classroom_id", label: "Classroom", type: "select", options: classroomOptions },
          { name: "subject_id", label: "Subject", type: "select", options: subjectOptions },
          { name: "teacher_profile_id", label: "Teacher", type: "select", options: teacherOptions },
          { name: "day_of_week", label: "Day", type: "select", options: dayOptions },
          { name: "start_time", label: "Start time", type: "time" },
          { name: "end_time", label: "End time", type: "time" },
        ]}
        columns={[
          {
            label: "Day",
            render: (item: TimetableEntry) =>
              item.day_of_week[0].toUpperCase() + item.day_of_week.slice(1),
          },
          {
            label: "Time",
            render: (item: TimetableEntry) =>
              `${item.start_time.slice(0, 5)}–${item.end_time.slice(0, 5)}`,
          },
          {
            label: "Classroom",
            render: (item: TimetableEntry) =>
              classroomMap.get(item.classroom_id)?.name ?? "Classroom unavailable",
          },
          {
            label: "Subject",
            render: (item: TimetableEntry) =>
              subjectMap.get(item.subject_id)?.name ?? "Subject unavailable",
          },
          {
            label: "Teacher",
            render: (item: TimetableEntry) => {
              const teacher = teacherMap.get(item.teacher_profile_id);
              return teacher ? teacherLabel(teacher, userMap) : "Teacher unavailable";
            },
          },
          { label: "Status", render: (item: TimetableEntry) => (item.is_active ? "Active" : "Inactive") },
        ]}
        emptyValues={{
          classroom_id: classroomOptions[0]?.value ?? "",
          subject_id: subjectOptions[0]?.value ?? "",
          teacher_profile_id: teacherOptions[0]?.value ?? "",
          day_of_week: "monday",
          start_time: "08:00",
          end_time: "09:00",
        }}
        schema={z
          .object({
            classroom_id: uuid,
            subject_id: uuid,
            teacher_profile_id: uuid,
            day_of_week: z.enum([
              "monday",
              "tuesday",
              "wednesday",
              "thursday",
              "friday",
              "saturday",
              "sunday",
            ]),
            start_time: z.string().min(1),
            end_time: z.string().min(1),
          })
          .refine((values) => values.start_time < values.end_time, {
            message: "End time must be after start time.",
            path: ["end_time"],
          })}
        load={(offset) => academicsApi.listTimetable({ includeInactive: true, offset })}
        create={(values) => academicsApi.createTimetable(valuesToPayload(values))}
        update={(id, values) => academicsApi.updateTimetable(id, valuesToPayload(values))}
        deactivate={academicsApi.deactivateTimetable}
        toFormValues={(item) => ({
          classroom_id: item.classroom_id,
          subject_id: item.subject_id,
          teacher_profile_id: item.teacher_profile_id,
          day_of_week: item.day_of_week,
          start_time: item.start_time.slice(0, 5),
          end_time: item.end_time.slice(0, 5),
        })}
      />
    </ReferenceState>
  );
}
