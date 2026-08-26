import { useQuery } from "@tanstack/react-query";
import { useCallback, useState, type ReactNode } from "react";
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

function activeStatus(isActive: boolean): ReactNode {
  return (
    <span className={`status-pill status-pill--${isActive ? "active" : "inactive"}`}>
      {isActive ? "Active" : "Inactive"}
    </span>
  );
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
    { label: "Status", render: (item) => activeStatus(item.is_active) },
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
        { label: "Status", render: (item: Subject) => activeStatus(item.is_active) },
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
          { label: "Status", render: (item: TeacherProfile) => activeStatus(item.is_active) },
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
  const [classroomId, setClassroomId] = useState("");
  const [includeInactive, setIncludeInactive] = useState(false);
  const [offset, setOffset] = useState(0);
  const classrooms = useQuery({
    queryKey: queryKeys.classrooms,
    queryFn: () => academicsApi.listClassrooms(),
  });
  const students = useQuery({
    queryKey: [...queryKeys.students, classroomId, includeInactive, offset],
    queryFn: () =>
      profilesApi.listStudents({ classroomId, includeInactive, offset }),
    enabled: Boolean(classroomId),
  });
  const selectedClassroom = classrooms.data?.items.find((item) => item.id === classroomId);
  const hasNext = students.data
    ? offset + students.data.limit < students.data.total
    : false;

  return (
    <ReferenceState
      title="Students"
      pending={classrooms.isPending}
      error={classrooms.error}
    >
      <section className="page-stack" aria-labelledby="students-heading">
        <div className="page-heading">
          <div>
            <p className="eyebrow">Administration</p>
            <h1 id="students-heading">Students</h1>
            <p>View classroom-wise student rosters.</p>
          </div>
        </div>
        <div className="form-card">
          <div className="form-grid">
            <label className="field">
              <span>Classroom</span>
              <select
                value={classroomId}
                onChange={(event) => {
                  setClassroomId(event.target.value);
                  setOffset(0);
                }}
              >
                <option value="">Select classroom</option>
                {classrooms.data?.items.map((classroom) => (
                  <option key={classroom.id} value={classroom.id}>{classroom.name}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Status</span>
              <select
                value={includeInactive ? "all" : "active"}
                onChange={(event) => {
                  setIncludeInactive(event.target.value === "all");
                  setOffset(0);
                }}
              >
                <option value="active">Active</option>
                <option value="all">All</option>
              </select>
            </label>
          </div>
        </div>
        <div className="table-card">
          <div className="table-card__header">
            <h2>{selectedClassroom?.name ?? "Classroom roster"}</h2>
            {students.data ? <span>{students.data.total} students</span> : null}
          </div>
          {!classroomId ? <p className="empty-state">Select a classroom to view its roster.</p> : null}
          {students.isPending && classroomId ? <p className="empty-state">Loading students…</p> : null}
          {students.isPending && classroomId ? <SlowRequestNotice /> : null}
          {students.error ? <p className="error-message" role="alert">{apiErrorMessage(students.error)}</p> : null}
          {students.data?.items.length === 0 ? <p className="empty-state">No students found.</p> : null}
          {students.data?.items.length ? (
            <div className="table-scroll" role="region" aria-label="Students roster table" tabIndex={0}>
              <table>
                <thead><tr><th>Student</th><th>Roll</th><th>Status</th></tr></thead>
                <tbody>
                  {students.data.items.map((student: StudentProfile) => (
                    <tr key={student.id}>
                      <td>{student.full_name ?? "Student account unavailable"}</td>
                      <td>{student.roll_number ?? "—"}</td>
                      <td>{activeStatus(student.is_active)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          {classroomId ? (
            <div className="pagination">
              <button className="button button--quiet" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 100))} type="button">Previous</button>
              <button className="button button--quiet" disabled={!hasNext} onClick={() => setOffset(offset + 100)} type="button">Next</button>
            </div>
          ) : null}
        </div>
      </section>
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
  const [viewClassroomId, setViewClassroomId] = useState("");
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
  const viewClassroom = classroomMap.get(viewClassroomId);

  return (
    <ReferenceState title="Teacher assignments" pending={pending} error={error}>
      <AdminCrudPage
        title="Assignments"
        description="Authorize exact teacher, classroom, and subject scopes."
        formTitle="Create teacher assignment"
        listTitle={viewClassroom ? `Current assignments — ${viewClassroom.name}` : "Current assignments"}
        listEnabled={Boolean(viewClassroomId)}
        paginationKey={viewClassroomId}
        viewControls={
          <div className="form-card">
            <label className="field">
              <span>View assignments for</span>
              <select
                aria-label="View assignments for"
                value={viewClassroomId}
                onChange={(event) => setViewClassroomId(event.target.value)}
              >
                <option value="">Select classroom</option>
                {references.classrooms.data?.items.filter((item) => item.is_active).map((item) => (
                  <option key={item.id} value={item.id}>{item.name}</option>
                ))}
              </select>
            </label>
          </div>
        }
        queryKey={[...queryKeys.assignments, "classroom", viewClassroomId]}
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
          { label: "Status", render: (item: TeacherAssignment) => activeStatus(item.is_active) },
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
        load={(offset) => academicsApi.listAssignments({
          classroomId: viewClassroomId,
          includeInactive: true,
          offset,
        })}
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
  const [viewClassroomId, setViewClassroomId] = useState("");
  const references = useAcademicReferenceData();
  const assignments = useQuery({
    queryKey: [...queryKeys.assignments, "timetable-options"],
    queryFn: () => academicsApi.listAssignments({ includeInactive: true }),
  });
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
  const assignmentMap = new Map(
    assignments.data?.items.map((assignment) => [assignment.id, assignment]) ?? [],
  );
  const assignmentOptions = (assignments.data?.items ?? [])
    .filter((assignment) => assignment.is_active)
    .map((assignment) => {
      const teacher = teacherMap.get(assignment.teacher_profile_id);
      const classroom = classroomMap.get(assignment.classroom_id);
      const subject = subjectMap.get(assignment.subject_id);
      return {
        label: `${classroom?.name ?? "Classroom unavailable"} — ${subject?.name ?? "Subject unavailable"} — ${teacher ? teacherLabel(teacher, userMap) : "Teacher unavailable"}`,
        value: assignment.id,
      };
    });
  if (!assignmentOptions.length) {
    assignmentOptions.push({ label: "No active teaching assignments available", value: "" });
  }
  const pending = assignments.isPending || Object.values(references).some((query) => query.isPending);
  const error = assignments.error ?? Object.values(references).map((query) => query.error).find(Boolean) ?? null;
  const viewClassroom = classroomMap.get(viewClassroomId);
  const valuesToPayload = (values: CrudFormValues) => {
    const assignment = assignmentMap.get(values.assignment_id);
    if (!assignment) throw new Error("Choose an active teaching assignment.");
    return {
      classroom_id: assignment.classroom_id,
      subject_id: assignment.subject_id,
      teacher_profile_id: assignment.teacher_profile_id,
      day_of_week: values.day_of_week as DayOfWeek,
      start_time: values.start_time,
      end_time: values.end_time,
    };
  };

  return (
    <ReferenceState title="Timetable" pending={pending} error={error}>
      <AdminCrudPage
        title="Timetable"
        description="Maintain assignment-backed classroom timetable slots."
        formTitle="Create timetable slot"
        listTitle={viewClassroom ? `Current timetable — ${viewClassroom.name}` : "Current timetable"}
        listEnabled={Boolean(viewClassroomId)}
        paginationKey={viewClassroomId}
        viewControls={
          <div className="form-card">
            <label className="field">
              <span>View timetable for</span>
              <select
                aria-label="View timetable for"
                value={viewClassroomId}
                onChange={(event) => setViewClassroomId(event.target.value)}
              >
                <option value="">Select classroom</option>
                {references.classrooms.data?.items.filter((item) => item.is_active).map((item) => (
                  <option key={item.id} value={item.id}>{item.name}</option>
                ))}
              </select>
            </label>
          </div>
        }
        queryKey={[...queryKeys.timetable, "classroom", viewClassroomId]}
        fields={[
          { name: "assignment_id", label: "Teaching assignment", type: "select", options: assignmentOptions },
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
          { label: "Status", render: (item: TimetableEntry) => activeStatus(item.is_active) },
        ]}
        emptyValues={{
          assignment_id: assignmentOptions[0]?.value ?? "",
          day_of_week: "monday",
          start_time: "08:00",
          end_time: "09:00",
        }}
        schema={z
          .object({
            assignment_id: uuid,
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
        load={(offset) => academicsApi.listTimetable({
          classroomId: viewClassroomId,
          includeInactive: true,
          offset,
        })}
        create={(values) => academicsApi.createTimetable(valuesToPayload(values))}
        update={(id, values) => academicsApi.updateTimetable(id, valuesToPayload(values))}
        deactivate={academicsApi.deactivateTimetable}
        toFormValues={(item) => {
          const assignment = assignments.data?.items.find(
            (candidate) =>
              candidate.classroom_id === item.classroom_id &&
              candidate.subject_id === item.subject_id &&
              candidate.teacher_profile_id === item.teacher_profile_id,
          );
          return {
            assignment_id: assignment?.id ?? "",
            day_of_week: item.day_of_week,
            start_time: item.start_time.slice(0, 5),
            end_time: item.end_time.slice(0, 5),
          };
        }}
      />
    </ReferenceState>
  );
}
