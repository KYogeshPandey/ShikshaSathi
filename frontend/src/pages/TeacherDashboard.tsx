import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { analyticsApi } from "../api/analytics";
import { apiErrorMessage } from "../api/errorMessage";
import { queryKeys } from "../api/queryKeys";
import { AttendanceAnalyticsPanel } from "../components/AttendanceAnalyticsPanel";
import { SlowRequestNotice } from "../components/SlowRequestNotice";
import type { AnalyticsWindowDays } from "../types/domain";

export function TeacherDashboard() {
  const [days, setDays] = useState<AnalyticsWindowDays>(7);
  const analytics = useQuery({
    queryKey: queryKeys.analyticsOverview(days),
    queryFn: () => analyticsApi.getOverview(days),
  });
  const scope = analytics.data?.teacher_scope;

  return (
    <section className="page-stack">
      <div className="page-heading">
        <p className="eyebrow">Teacher overview</p>
        <h1>Teacher workspace</h1>
        <p>Review attendance only within your active teaching scope, schedule, and assigned classes.</p>
      </div>
      {analytics.isPending ? <p className="empty-state">Loading your workspace analytics…</p> : null}
      {analytics.isPending ? <SlowRequestNotice /> : null}
      {analytics.error ? (
        <div className="error-message" role="alert">
          <p>{apiErrorMessage(analytics.error)}</p>
          <button className="button button--quiet" onClick={() => void analytics.refetch()} type="button">Retry analytics</button>
        </div>
      ) : null}
      {analytics.data && scope ? (
        <>
          <div className="metric-grid" aria-label="Assigned teaching scope">
            <article className="metric-card"><span>Assigned classrooms</span><strong>{scope.assigned_classrooms}</strong></article>
            <article className="metric-card"><span>Assigned subjects</span><strong>{scope.assigned_subjects}</strong></article>
            <article className="metric-card"><span>Timetable slots</span><strong>{scope.timetable_slots}</strong></article>
          </div>
          <AttendanceAnalyticsPanel overview={analytics.data} days={days} onDaysChange={setDays} />
        </>
      ) : null}
      <div className="card-grid">
        <Link className="action-card" to="/teacher/attendance/manual"><strong>Manual attendance</strong><span>Record a whole class at once</span></Link>
        <Link className="action-card" to="/teacher/attendance/recognition"><strong>Recognition attendance</strong><span>Camera or image workflow</span></Link>
        <Link className="action-card" to="/teacher/reports"><strong>Reports</strong><span>Attendance, defaulters, leaderboard, and exports</span></Link>
        <Link className="action-card" to="/teacher/announcements"><strong>Announcements</strong><span>Read school notices</span></Link>
      </div>
    </section>
  );
}
