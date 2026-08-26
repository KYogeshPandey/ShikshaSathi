import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { analyticsApi } from "../api/analytics";
import { apiErrorMessage } from "../api/errorMessage";
import { queryKeys } from "../api/queryKeys";
import { AttendanceAnalyticsPanel } from "../components/AttendanceAnalyticsPanel";
import { SlowRequestNotice } from "../components/SlowRequestNotice";
import type { AnalyticsWindowDays } from "../types/domain";

export function AdminDashboard() {
  const [days, setDays] = useState<AnalyticsWindowDays>(7);
  const analytics = useQuery({
    queryKey: queryKeys.analyticsOverview(days),
    queryFn: () => analyticsApi.getOverview(days),
  });
  const population = analytics.data?.admin_population;

  return (
    <section className="page-stack dashboard-page admin-dashboard-page">
      <div className="page-heading">
        <p className="eyebrow">Admin overview</p>
        <h1>Administration workspace</h1>
        <p>Monitor school scale and attendance signals, then move directly into daily operations.</p>
      </div>

      {analytics.isPending ? <p className="empty-state">Loading school analytics…</p> : null}
      {analytics.isPending ? <SlowRequestNotice /> : null}
      {analytics.error ? (
        <div className="error-message" role="alert">
          <p>{apiErrorMessage(analytics.error)}</p>
          <button className="button button--quiet" onClick={() => void analytics.refetch()} type="button">Retry analytics</button>
        </div>
      ) : null}

      {analytics.data && population ? (
        <>
          <div className="metric-grid" aria-label="School population">
            <article className="metric-card"><span>Active students</span><strong>{population.active_students}</strong></article>
            <article className="metric-card"><span>Active teachers</span><strong>{population.active_teachers}</strong></article>
            <article className="metric-card"><span>Active classrooms</span><strong>{population.active_classrooms}</strong></article>
            <article className="metric-card"><span>Active subjects</span><strong>{population.active_subjects}</strong></article>
          </div>
          <AttendanceAnalyticsPanel overview={analytics.data} days={days} onDaysChange={setDays} />
          <section aria-labelledby="attendance-attention-title" className="table-card attention-panel">
            <div className="table-card__header">
              <div>
                <p className="eyebrow">Attention</p>
                <h2 id="attendance-attention-title">Lowest recorded attendance</h2>
              </div>
              <span>Last {days} days</span>
            </div>
            <p className="analytics-definition">
              Up to three active classrooms with marked records, ordered by attendance rate. This
              comparison is not an institutional policy threshold.
            </p>
            {analytics.data.attention_classrooms.length === 0 ? (
              <p className="empty-state">No classroom attendance data is available for this period.</p>
            ) : (
              <ul className="attention-list">
                {analytics.data.attention_classrooms.map((classroom) => (
                  <li key={classroom.classroom_code}>
                    <div><strong>{classroom.classroom_name}</strong><span>{classroom.classroom_code}</span></div>
                    <div className="attention-list__metric"><strong>{classroom.attendance_percentage.toFixed(2)}%</strong><span>{classroom.total_count} marked records</span></div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      ) : null}

      <div className="card-grid">
        <Link className="action-card" to="/admin/classrooms"><strong>Academic setup</strong><span>Classrooms and subjects</span></Link>
        <Link className="action-card" to="/admin/teachers"><strong>People</strong><span>Teacher and student profiles</span></Link>
        <Link className="action-card" to="/admin/assignments"><strong>Teaching plan</strong><span>Assignments and timetable</span></Link>
        <Link className="action-card" to="/admin/announcements"><strong>Communication</strong><span>Publish announcements</span></Link>
        <Link className="action-card" to="/admin/imports"><strong>Bulk imports</strong><span>CSV and XLSX workflows</span></Link>
        <Link className="action-card" to="/admin/reports"><strong>Reports</strong><span>Attendance, defaulters, leaderboard, and exports</span></Link>
      </div>
    </section>
  );
}
