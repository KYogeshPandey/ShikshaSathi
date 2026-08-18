import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { academicsApi } from "../api/academics";
import { attendanceApi } from "../api/attendance";
import { apiErrorMessage } from "../api/errorMessage";
import { queryKeys } from "../api/queryKeys";
import type { AttendanceStatus, BulkAttendanceRequest } from "../types/domain";

interface ScopeValues {
  classroom_id: string;
  subject_id: string;
  attendance_date: string;
}

const scopeSchema = z.object({
  classroom_id: z.string().uuid("Choose a classroom."),
  subject_id: z.string().uuid("Choose a subject."),
  attendance_date: z.string().date("Choose a valid date."),
});

function today(): string {
  const date = new Date();
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
}

export function ManualAttendancePage() {
  const client = useQueryClient();
  const [scope, setScope] = useState<ScopeValues | null>(null);
  const [statuses, setStatuses] = useState<Record<string, AttendanceStatus>>({});
  const [notice, setNotice] = useState<string | null>(null);
  const form = useForm<ScopeValues>({ defaultValues: { classroom_id: "", subject_id: "", attendance_date: today() } });
  const classrooms = useQuery({ queryKey: queryKeys.classrooms, queryFn: () => academicsApi.listClassrooms() });
  const subjects = useQuery({ queryKey: queryKeys.subjects, queryFn: () => academicsApi.listSubjects() });
  const roster = useQuery({
    queryKey: scope ? queryKeys.attendanceRoster(scope.classroom_id, scope.subject_id) : [...queryKeys.attendance, "roster", "idle"],
    queryFn: () => attendanceApi.getRoster({ classroomId: scope!.classroom_id, subjectId: scope!.subject_id }),
    enabled: Boolean(scope),
  });
  const daily = useQuery({
    queryKey: scope ? [...queryKeys.attendance, "daily", scope.classroom_id, scope.subject_id, scope.attendance_date] : [...queryKeys.attendance, "daily", "idle"],
    queryFn: () => attendanceApi.getDaily({ classroomId: scope!.classroom_id, subjectId: scope!.subject_id }, scope!.attendance_date),
    enabled: Boolean(scope),
  });

  const savedStatuses = new Map(daily.data?.records.map((record) => [record.student_profile_id, record.status]) ?? []);
  const statusFor = (studentProfileId: string): AttendanceStatus => statuses[studentProfileId] ?? savedStatuses.get(studentProfileId) ?? "absent";

  const save = useMutation({
    mutationFn: (payload: BulkAttendanceRequest) => attendanceApi.saveBulk(payload),
    onSuccess: async (result) => {
      setNotice(`${result.total_count} attendance records saved.`);
      await client.invalidateQueries({ queryKey: queryKeys.attendance });
    },
    onError: () => setNotice(null),
  });

  const loadRoster = form.handleSubmit((values) => {
    setNotice(null);
    const parsed = scopeSchema.safeParse(values);
    if (!parsed.success) {
      for (const issue of parsed.error.issues) form.setError(issue.path[0] as keyof ScopeValues, { message: issue.message });
      return;
    }
    setStatuses({});
    setScope(parsed.data);
  });

  const saveAttendance = () => {
    if (!scope || !roster.data) return;
    save.mutate({
      classroom_id: scope.classroom_id,
      subject_id: scope.subject_id,
      attendance_date: scope.attendance_date,
      records: roster.data.map((student) => ({ student_profile_id: student.student_profile_id, status: statusFor(student.student_profile_id) })),
    });
  };

  return (
    <section className="page-stack">
      <div className="page-heading"><p className="eyebrow">Teacher attendance</p><h1>Manual attendance</h1><p>Load the server-authorized classroom roster, review every student, then save one bulk attendance request.</p></div>
      <form className="form-card" onSubmit={loadRoster} noValidate>
        <div className="form-grid">
          <label className="field"><span>Classroom</span><select {...form.register("classroom_id")}><option value="">Select classroom</option>{classrooms.data?.items.map((item) => <option key={item.id} value={item.id}>{item.name} ({item.code})</option>)}</select>{form.formState.errors.classroom_id?.message ? <small className="field-error">{form.formState.errors.classroom_id.message}</small> : null}</label>
          <label className="field"><span>Subject</span><select {...form.register("subject_id")}><option value="">Select subject</option>{subjects.data?.items.map((item) => <option key={item.id} value={item.id}>{item.name} ({item.code})</option>)}</select>{form.formState.errors.subject_id?.message ? <small className="field-error">{form.formState.errors.subject_id.message}</small> : null}</label>
          <label className="field"><span>Date</span><input type="date" {...form.register("attendance_date")} />{form.formState.errors.attendance_date?.message ? <small className="field-error">{form.formState.errors.attendance_date.message}</small> : null}</label>
        </div>
        <button className="button button--primary" disabled={classrooms.isPending || subjects.isPending} type="submit">Load roster</button>
        {classrooms.error || subjects.error ? <p className="error-message" role="alert">{apiErrorMessage(classrooms.error ?? subjects.error)}</p> : null}
      </form>
      {roster.isPending || daily.isPending ? <p className="empty-state">Loading authorized roster and saved attendance...</p> : null}
      {roster.error || daily.error ? <p className="error-message" role="alert">{apiErrorMessage(roster.error ?? daily.error)}</p> : null}
      {scope && roster.data?.length === 0 ? <p className="empty-state">This authorized classroom has no active students.</p> : null}
      {roster.data?.length ? (
        <div className="table-card">
          <div className="table-card__header"><h2>Roster</h2><span>{roster.data.length} active students</span></div>
          <div className="attendance-list">
            {roster.data.map((student) => (
              <div className="attendance-row" key={student.student_profile_id}>
                <div><strong>Roll {student.roll_number ?? "not assigned"}</strong><small>{student.student_profile_id}</small></div>
                <div className="segmented" role="group" aria-label={`Attendance for roll ${student.roll_number ?? student.student_profile_id}`}>
                  {(["present", "absent"] as const).map((status) => <button className={statusFor(student.student_profile_id) === status ? "segment segment--active" : "segment"} key={status} onClick={() => setStatuses((current) => ({ ...current, [student.student_profile_id]: status }))} type="button">{status}</button>)}
                </div>
              </div>
            ))}
          </div>
          <button className="button button--primary" disabled={save.isPending} onClick={saveAttendance} type="button">{save.isPending ? "Saving..." : "Save attendance"}</button>
          {notice ? <p className="success-message" role="status">{notice}</p> : null}
          {save.error ? <p className="error-message" role="alert">{apiErrorMessage(save.error)}</p> : null}
        </div>
      ) : null}
    </section>
  );
}
