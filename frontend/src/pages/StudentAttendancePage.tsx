import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { academicsApi } from "../api/academics";
import { attendanceApi } from "../api/attendance";
import { apiErrorMessage } from "../api/errorMessage";
import { queryKeys } from "../api/queryKeys";
import { SlowRequestNotice } from "../components/SlowRequestNotice";

interface FilterValues {
  classroom_id: string;
  subject_id: string;
  date_from: string;
  date_to: string;
  status: "" | "present" | "absent";
}

const filtersSchema = z
  .object({
    classroom_id: z.string().uuid().or(z.literal("")),
    subject_id: z.string().uuid().or(z.literal("")),
    date_from: z.string(),
    date_to: z.string(),
    status: z.enum(["", "present", "absent"]),
  })
  .refine((value) => !value.date_from || !value.date_to || value.date_from <= value.date_to, {
    message: "Start date must be before end date.",
    path: ["date_to"],
  });

const emptyFilters: FilterValues = {
  classroom_id: "",
  subject_id: "",
  date_from: "",
  date_to: "",
  status: "",
};

export function StudentAttendancePage() {
  const [filters, setFilters] = useState<FilterValues>(emptyFilters);
  const form = useForm<FilterValues>({ defaultValues: emptyFilters });
  const classrooms = useQuery({
    queryKey: queryKeys.classrooms,
    queryFn: () => academicsApi.listClassrooms(),
  });
  const subjects = useQuery({
    queryKey: queryKeys.subjects,
    queryFn: () => academicsApi.listSubjects(),
  });
  const classroomNames = new Map(
    classrooms.data?.items.map((classroom) => [classroom.id, classroom.name]) ?? [],
  );
  const subjectNames = new Map(
    subjects.data?.items.map((subject) => [subject.id, subject.name]) ?? [],
  );
  const apiFilters = {
    classroomId: filters.classroom_id || undefined,
    subjectId: filters.subject_id || undefined,
    dateFrom: filters.date_from || undefined,
    dateTo: filters.date_to || undefined,
    status: filters.status || undefined,
  };
  const stats = useQuery({
    queryKey: [...queryKeys.studentAttendance, "stats", filters],
    queryFn: () => attendanceApi.getMyStats(apiFilters),
  });
  const detail = useQuery({
    queryKey: [...queryKeys.studentAttendance, "detail", filters],
    queryFn: () => attendanceApi.getMyDetail(apiFilters),
  });

  const applyFilters = form.handleSubmit((values) => {
    const parsed = filtersSchema.safeParse(values);
    if (!parsed.success) {
      for (const issue of parsed.error.issues) {
        form.setError(issue.path[0] as keyof FilterValues, { message: issue.message });
      }
      return;
    }
    setFilters(parsed.data);
  });
  const pending = stats.isPending || detail.isPending || classrooms.isPending || subjects.isPending;
  const error = stats.error ?? detail.error ?? classrooms.error ?? subjects.error;

  return (
    <section className="page-stack">
      <div className="page-heading">
        <p className="eyebrow">Student self-service</p>
        <h1>My attendance</h1>
        <p>Review only your own attendance summary and detailed records.</p>
      </div>
      <form className="form-card" onSubmit={applyFilters} noValidate>
        <h2>Filters</h2>
        <div className="form-grid">
          <label className="field">
            <span>Classroom</span>
            <select disabled={classrooms.isPending} {...form.register("classroom_id")}>
              <option value="">All classrooms</option>
              {classrooms.data?.items.map((classroom) => (
                <option key={classroom.id} value={classroom.id}>{classroom.name}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Subject</span>
            <select disabled={subjects.isPending} {...form.register("subject_id")}>
              <option value="">All subjects</option>
              {subjects.data?.items.map((subject) => (
                <option key={subject.id} value={subject.id}>{subject.name}</option>
              ))}
            </select>
          </label>
          <label className="field"><span>From</span><input type="date" {...form.register("date_from")} /></label>
          <label className="field">
            <span>To</span>
            <input aria-describedby={form.formState.errors.date_to ? "student-date-error" : undefined} aria-invalid={Boolean(form.formState.errors.date_to)} type="date" {...form.register("date_to")} />
            {form.formState.errors.date_to?.message ? <small className="field-error" id="student-date-error">{form.formState.errors.date_to.message}</small> : null}
          </label>
          <label className="field"><span>Status</span><select {...form.register("status")}><option value="">All</option><option value="present">Present</option><option value="absent">Absent</option></select></label>
        </div>
        <div className="button-row">
          <button className="button button--primary" type="submit">Apply filters</button>
          <button className="button button--quiet" onClick={() => { form.reset(emptyFilters); setFilters(emptyFilters); }} type="button">Clear</button>
        </div>
      </form>
      {stats.data ? (
        <div className="metric-grid">
          <article className="metric-card"><span>Total</span><strong>{stats.data.total_count}</strong></article>
          <article className="metric-card"><span>Present</span><strong>{stats.data.present_count}</strong></article>
          <article className="metric-card"><span>Absent</span><strong>{stats.data.absent_count}</strong></article>
          <article className="metric-card"><span>Attendance</span><strong>{stats.data.attendance_percentage.toFixed(1)}%</strong></article>
        </div>
      ) : null}
      {pending ? <p className="empty-state">Loading your attendance…</p> : null}
      {pending ? <SlowRequestNotice /> : null}
      {error ? <p className="error-message" role="alert">{apiErrorMessage(error)}</p> : null}
      <div className="table-card">
        <div className="table-card__header"><h2>Detailed records</h2>{detail.data ? <span>{detail.data.total} total</span> : null}</div>
        {detail.data?.items.length === 0 ? <p className="empty-state">No records match these filters.</p> : null}
        {detail.data?.items.length ? (
          <div className="table-scroll" role="region" aria-label="Detailed attendance records" tabIndex={0}>
            <table>
              <thead><tr><th>Date</th><th>Status</th><th>Classroom</th><th>Subject</th><th>Remarks</th></tr></thead>
              <tbody>{detail.data.items.map((record) => (
                <tr key={record.id}>
                  <td>{record.attendance_date}</td>
                  <td><span className={`status-pill status-pill--${record.status}`}>{record.status}</span></td>
                  <td>{classroomNames.get(record.classroom_id) ?? "Assigned classroom"}</td>
                  <td>{subjectNames.get(record.subject_id) ?? "Assigned subject"}</td>
                  <td>{record.remarks ?? "-"}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        ) : null}
      </div>
    </section>
  );
}
