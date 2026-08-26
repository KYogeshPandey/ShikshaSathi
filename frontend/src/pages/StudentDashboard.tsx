import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { analyticsApi } from "../api/analytics";
import { attendanceApi } from "../api/attendance";
import { apiErrorMessage } from "../api/errorMessage";
import { queryKeys } from "../api/queryKeys";
import { AttendanceAnalyticsPanel } from "../components/AttendanceAnalyticsPanel";
import { SlowRequestNotice } from "../components/SlowRequestNotice";
import type { AnalyticsWindowDays, SubjectAttendanceStatus } from "../types/domain";

function localIsoDate(offsetDays = 0): string {
  const value = new Date();
  value.setDate(value.getDate() + offsetDays);
  const offset = value.getTimezoneOffset() * 60_000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 10);
}

function subjectStatusLabel(status: SubjectAttendanceStatus): string {
  return {
    safe: "Safe",
    near_target: "Near target",
    recovery_needed: "Recovery needed",
    no_history: "No history",
  }[status];
}

export function StudentDashboard() {
  const [days, setDays] = useState<AnalyticsWindowDays>(7);
  const overviewRequest = useMemo(
    () => ({ target_percentage: 75, deadline: localIsoDate(30) }),
    [],
  );
  const analytics = useQuery({
    queryKey: queryKeys.analyticsOverview(days),
    queryFn: () => analyticsApi.getOverview(days),
  });
  const overview = useQuery({
    queryKey: queryKeys.attendanceRecoveryPlan(overviewRequest),
    queryFn: () => attendanceApi.getRecoveryPlan(overviewRequest),
  });
  const student = analytics.data?.student_context;

  return (
    <section className="page-stack dashboard-page student-overview-page">
      <div className="page-heading">
        <p className="eyebrow">Student overview</p>
        <h1>Student portal</h1>
        <p>Track your attendance, understand subject trends, and open the tools you need.</p>
      </div>

      {overview.isPending ? <p className="empty-state">Loading your attendance overview…</p> : null}
      {overview.isPending ? <SlowRequestNotice /> : null}
      {overview.error ? (
        <div className="error-message" role="alert">
          <p>{apiErrorMessage(overview.error)}</p>
          <button className="button button--quiet" onClick={() => void overview.refetch()} type="button">
            Retry overview
          </button>
        </div>
      ) : null}

      {overview.data ? (
        <>
          <section aria-labelledby="attendance-overview-title" className="table-card student-attendance-overview">
            <div className="table-card__header">
              <h2 id="attendance-overview-title">Attendance overview</h2>
              <span>All marked records in your current classroom</span>
            </div>
            <div className="metric-grid">
              <article className="metric-card metric-card--primary"><span>Current attendance</span><strong>{overview.data.overall.percentage.toFixed(1)}%</strong></article>
              <article className="metric-card"><span>Minimum required</span><strong>{overview.data.target_percentage}%</strong></article>
              <article className="metric-card metric-card--status"><span>Status</span><strong>{subjectStatusLabel(overview.data.overall_status)}</strong></article>
              <article className="metric-card"><span>Present / held</span><strong>{overview.data.overall.attended} / {overview.data.overall.held}</strong></article>
            </div>
          </section>

          <section aria-labelledby="subject-attendance-title" className="table-card">
            <div className="table-card__header">
              <h2 id="subject-attendance-title">Subject attendance</h2>
              <span>{overview.data.subjects.length} subjects</span>
            </div>
            {overview.data.subjects.length === 0 ? (
              <p className="empty-state">No active subjects are assigned to your classroom.</p>
            ) : (
              <div aria-label="Subject-wise attendance" className="table-scroll" role="region" tabIndex={0}>
                <table>
                  <thead><tr><th>Subject</th><th>Present</th><th>Held</th><th>Attendance</th><th>Status</th></tr></thead>
                  <tbody>
                    {overview.data.subjects.map((subject) => (
                      <tr key={subject.subject_id}>
                        <td><strong>{subject.subject_name}</strong><small className="table-secondary">{subject.subject_code}</small></td>
                        <td>{subject.attended}</td>
                        <td>{subject.held}</td>
                        <td>{subject.percentage.toFixed(1)}%</td>
                        <td><span className={`planner-status planner-status--${subject.status}`}>{subjectStatusLabel(subject.status)}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      ) : null}

      <div className="card-grid student-quick-actions" aria-label="Student quick actions">
        <Link className="action-card" to="/student/recovery-planner">
          <strong>Attendance Recovery Planner</strong>
          <span>Plan the classes needed to reach your attendance target.</span>
        </Link>
        <Link className="action-card" to="/student/timetable">
          <strong>Weekly Timetable</strong>
          <span>See your active weekly class schedule.</span>
        </Link>
        <Link className="action-card" to="/student/attendance"><strong>My attendance</strong><span>Summary, filters, and records</span></Link>
        <Link className="action-card" to="/student/announcements"><strong>Announcements</strong><span>Notices available to you</span></Link>
      </div>

      {analytics.isPending ? <p className="empty-state">Loading your attendance analytics…</p> : null}
      {analytics.isPending ? <SlowRequestNotice /> : null}
      {analytics.error ? (
        <div className="error-message" role="alert">
          <p>{apiErrorMessage(analytics.error)}</p>
          <button className="button button--quiet" onClick={() => void analytics.refetch()} type="button">Retry analytics</button>
        </div>
      ) : null}
      {analytics.data && student ? (
        <>
          <div className="metric-grid metric-grid--compact" aria-label="Student profile context">
            <article className="metric-card"><span>Roll number</span><strong>{student.roll_number ?? "Not assigned"}</strong></article>
          </div>
          <AttendanceAnalyticsPanel overview={analytics.data} days={days} onDaysChange={setDays} />
        </>
      ) : null}
    </section>
  );
}
