import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { academicsApi } from "../api/academics";
import { attendanceApi } from "../api/attendance";
import type { ApiDownload } from "../api/client";
import { apiErrorMessage } from "../api/errorMessage";
import { queryKeys } from "../api/queryKeys";
import { reportsApi, type ReportFilters } from "../api/reports";

interface ReportFormValues {
  classroom_id: string;
  subject_id: string;
  period_mode: "month" | "range";
  month: string;
  date_from: string;
  date_to: string;
  student_profile_id: string;
  threshold: number;
}

const reportSchema = z
  .object({
    classroom_id: z.string().uuid("Choose a classroom."),
    subject_id: z.string().uuid("Choose a subject."),
    period_mode: z.enum(["month", "range"]),
    month: z.string(),
    date_from: z.string(),
    date_to: z.string(),
    student_profile_id: z.union([z.literal(""), z.string().uuid("Choose a valid student.")]),
    threshold: z.number().min(0, "Threshold must be at least 0.").max(100, "Threshold cannot exceed 100."),
  })
  .superRefine((values, context) => {
    if (values.period_mode === "month") {
      if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(values.month)) {
        context.addIssue({ code: "custom", message: "Choose a valid month.", path: ["month"] });
      }
      return;
    }
    if (!values.date_from || !values.date_to) {
      context.addIssue({ code: "custom", message: "Choose both dates.", path: ["date_to"] });
      return;
    }
    if (values.date_from > values.date_to) {
      context.addIssue({ code: "custom", message: "Start date must be before end date.", path: ["date_to"] });
      return;
    }
    const elapsedDays =
      (Date.parse(values.date_to) - Date.parse(values.date_from)) / (24 * 60 * 60 * 1_000);
    if (elapsedDays >= 366) {
      context.addIssue({ code: "custom", message: "Date range cannot exceed 366 days.", path: ["date_to"] });
    }
  });

function currentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

const defaults: ReportFormValues = {
  classroom_id: "",
  subject_id: "",
  period_mode: "month",
  month: currentMonth(),
  date_from: "",
  date_to: "",
  student_profile_id: "",
  threshold: 75,
};

function saveDownload(download: ApiDownload, fallbackName: string): void {
  const objectUrl = URL.createObjectURL(download.blob);
  const link = document.createElement("a");
  try {
    link.href = objectUrl;
    link.download = download.filename ?? fallbackName;
    document.body.append(link);
    link.click();
  } finally {
    link.remove();
    URL.revokeObjectURL(objectUrl);
  }
}

export function ReportsPage() {
  const [filters, setFilters] = useState<ReportFilters | null>(null);
  const [downloadNotice, setDownloadNotice] = useState<string | null>(null);
  const form = useForm<ReportFormValues>({ defaultValues: defaults });
  const classroomId = useWatch({ control: form.control, name: "classroom_id" });
  const subjectId = useWatch({ control: form.control, name: "subject_id" });
  const periodMode = useWatch({ control: form.control, name: "period_mode" });

  const classrooms = useQuery({
    queryKey: queryKeys.classrooms,
    queryFn: () => academicsApi.listClassrooms(),
  });
  const subjects = useQuery({
    queryKey: queryKeys.subjects,
    queryFn: () => academicsApi.listSubjects(),
  });
  const roster = useQuery({
    queryKey:
      classroomId && subjectId
        ? queryKeys.attendanceRoster(classroomId, subjectId)
        : [...queryKeys.attendance, "roster", "reports-idle"],
    queryFn: () => attendanceApi.getRoster({ classroomId, subjectId }),
    enabled: Boolean(classroomId && subjectId),
  });

  const attendance = useQuery({
    queryKey: queryKeys.attendanceReport(filters ?? {}),
    queryFn: () => reportsApi.getAttendance(filters!),
    enabled: filters !== null,
  });
  const defaulters = useQuery({
    queryKey: queryKeys.defaultersReport(filters ?? {}),
    queryFn: () => reportsApi.getDefaulters(filters!),
    enabled: filters !== null,
  });
  const leaderboard = useQuery({
    queryKey: queryKeys.leaderboardReport(filters ?? {}),
    queryFn: () => reportsApi.getLeaderboard(filters!),
    enabled: filters !== null,
  });

  const csvExport = useMutation({
    mutationFn: () => reportsApi.downloadAttendance("csv", filters!),
    onSuccess: (download) => {
      saveDownload(download, "attendance-report.csv");
      setDownloadNotice("CSV report downloaded.");
    },
  });
  const pdfExport = useMutation({
    mutationFn: () => reportsApi.downloadAttendance("pdf", filters!),
    onSuccess: (download) => {
      saveDownload(download, "attendance-report.pdf");
      setDownloadNotice("PDF report downloaded.");
    },
  });

  const applyFilters = form.handleSubmit((values) => {
    form.clearErrors();
    const parsed = reportSchema.safeParse(values);
    if (!parsed.success) {
      for (const issue of parsed.error.issues) {
        form.setError(issue.path[0] as keyof ReportFormValues, { message: issue.message });
      }
      return;
    }
    const applied: ReportFilters = {
      classroomId: parsed.data.classroom_id,
      subjectId: parsed.data.subject_id,
      studentProfileId: parsed.data.student_profile_id || undefined,
      threshold: parsed.data.threshold,
    };
    if (parsed.data.period_mode === "month") {
      applied.month = parsed.data.month;
    } else {
      applied.dateFrom = parsed.data.date_from;
      applied.dateTo = parsed.data.date_to;
    }
    setDownloadNotice(null);
    setFilters(applied);
  });

  const optionsError = classrooms.error ?? subjects.error ?? roster.error;
  const reportError = attendance.error ?? defaulters.error ?? leaderboard.error;
  const exportError = csvExport.error ?? pdfExport.error;
  const isLoading = attendance.isPending || defaulters.isPending || leaderboard.isPending;

  return (
    <section className="page-stack">
      <div className="page-heading">
        <p className="eyebrow">Attendance intelligence</p>
        <h1>Reports</h1>
        <p>Review one authorized classroom and subject over a bounded period, then export the same filtered attendance detail.</p>
      </div>

      <form className="form-card" noValidate onSubmit={applyFilters}>
        <h2>Report filters</h2>
        <div className="form-grid">
          <label className="field">
            <span>Classroom</span>
            <select {...form.register("classroom_id")}>
              <option value="">Select classroom</option>
              {classrooms.data?.items.map((classroom) => <option key={classroom.id} value={classroom.id}>{classroom.name} ({classroom.code})</option>)}
            </select>
            {form.formState.errors.classroom_id?.message ? <small className="field-error">{form.formState.errors.classroom_id.message}</small> : null}
          </label>
          <label className="field">
            <span>Subject</span>
            <select {...form.register("subject_id")}>
              <option value="">Select subject</option>
              {subjects.data?.items.map((subject) => <option key={subject.id} value={subject.id}>{subject.name} ({subject.code})</option>)}
            </select>
            {form.formState.errors.subject_id?.message ? <small className="field-error">{form.formState.errors.subject_id.message}</small> : null}
          </label>
          <label className="field">
            <span>Period type</span>
            <select {...form.register("period_mode")}>
              <option value="month">Month</option>
              <option value="range">Date range</option>
            </select>
          </label>
          {periodMode === "month" ? (
            <label className="field">
              <span>Month</span>
              <input type="month" {...form.register("month")} />
              {form.formState.errors.month?.message ? <small className="field-error">{form.formState.errors.month.message}</small> : null}
            </label>
          ) : (
            <>
              <label className="field"><span>From</span><input type="date" {...form.register("date_from")} /></label>
              <label className="field">
                <span>To</span><input type="date" {...form.register("date_to")} />
                {form.formState.errors.date_to?.message ? <small className="field-error">{form.formState.errors.date_to.message}</small> : null}
              </label>
            </>
          )}
          <label className="field">
            <span>Attendance student (optional)</span>
            <select disabled={!roster.data} {...form.register("student_profile_id")}>
              <option value="">All active students</option>
              {roster.data?.map((student) => <option key={student.student_profile_id} value={student.student_profile_id}>Roll {student.roll_number ?? "not assigned"}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Defaulter threshold (%)</span>
            <input type="number" min="0" max="100" step="0.01" {...form.register("threshold", { valueAsNumber: true })} />
            {form.formState.errors.threshold?.message ? <small className="field-error">{form.formState.errors.threshold.message}</small> : null}
          </label>
        </div>
        <div className="button-row">
          <button className="button button--primary" type="submit">Generate reports</button>
          <button className="button button--quiet" onClick={() => { form.reset(defaults); setFilters(null); setDownloadNotice(null); }} type="button">Clear</button>
        </div>
        {optionsError ? <p className="error-message" role="alert">{apiErrorMessage(optionsError)}</p> : null}
      </form>

      {filters && isLoading ? <p className="empty-state">Generating reports...</p> : null}
      {reportError ? <p className="error-message" role="alert">{apiErrorMessage(reportError)}</p> : null}

      {attendance.data ? (
        <>
          <div className="metric-grid">
            <article className="metric-card"><span>Total records</span><strong>{attendance.data.summary.total_count}</strong></article>
            <article className="metric-card"><span>Present</span><strong>{attendance.data.summary.present_count}</strong></article>
            <article className="metric-card"><span>Absent</span><strong>{attendance.data.summary.absent_count}</strong></article>
            <article className="metric-card"><span>Attendance</span><strong>{attendance.data.summary.attendance_percentage.toFixed(2)}%</strong></article>
          </div>
          <div className="table-card">
            <div className="table-card__header"><h2>Attendance detail</h2><span>{attendance.data.details.length} rows</span></div>
            <div className="button-row report-export-actions">
              <button className="button button--quiet" disabled={csvExport.isPending} onClick={() => csvExport.mutate()} type="button">{csvExport.isPending ? "Preparing CSV..." : "Download CSV"}</button>
              <button className="button button--quiet" disabled={pdfExport.isPending} onClick={() => pdfExport.mutate()} type="button">{pdfExport.isPending ? "Preparing PDF..." : "Download PDF"}</button>
            </div>
            {downloadNotice ? <p className="success-message" role="status">{downloadNotice}</p> : null}
            {exportError ? <p className="error-message" role="alert">{apiErrorMessage(exportError)}</p> : null}
            {attendance.data.details.length === 0 ? <p className="empty-state">No attendance records match these filters.</p> : (
              <div className="table-scroll"><table><thead><tr><th>Date</th><th>Roll</th><th>Student</th><th>Status</th><th>Remarks</th></tr></thead><tbody>{attendance.data.details.map((row) => <tr key={`${row.attendance_date}-${row.student_profile_id}`}><td>{row.attendance_date}</td><td>{row.roll_number ?? "-"}</td><td>{row.student_profile_id}</td><td><span className={`status-pill status-pill--${row.status}`}>{row.status}</span></td><td>{row.remarks ?? "-"}</td></tr>)}</tbody></table></div>
            )}
          </div>
        </>
      ) : null}

      {defaulters.data ? (
        <div className="table-card">
          <div className="table-card__header"><h2>Defaulters below {defaulters.data.threshold}%</h2><span>{defaulters.data.students.length} students</span></div>
          {defaulters.data.students.length === 0 ? <p className="empty-state">No active students are below this threshold.</p> : <div className="table-scroll"><table><thead><tr><th>Roll</th><th>Student</th><th>Present</th><th>Total</th><th>Attendance</th></tr></thead><tbody>{defaulters.data.students.map((row) => <tr key={row.student_profile_id}><td>{row.roll_number ?? "-"}</td><td>{row.student_profile_id}</td><td>{row.present_count}</td><td>{row.total_count}</td><td>{row.attendance_percentage.toFixed(2)}%</td></tr>)}</tbody></table></div>}
        </div>
      ) : null}

      {leaderboard.data ? (
        <div className="table-card">
          <div className="table-card__header"><h2>Classroom leaderboard</h2><span>{leaderboard.data.students.length} active students</span></div>
          {leaderboard.data.students.length === 0 ? <p className="empty-state">No active students are in this classroom.</p> : <div className="table-scroll"><table><thead><tr><th>Rank</th><th>Roll</th><th>Student</th><th>Present</th><th>Total</th><th>Attendance</th></tr></thead><tbody>{leaderboard.data.students.map((row) => <tr key={row.student_profile_id}><td>{row.rank}</td><td>{row.roll_number ?? "-"}</td><td>{row.student_profile_id}</td><td>{row.present_count}</td><td>{row.total_count}</td><td>{row.attendance_percentage.toFixed(2)}%</td></tr>)}</tbody></table></div>}
        </div>
      ) : null}
    </section>
  );
}
