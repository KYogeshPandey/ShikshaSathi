import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { analyticsApi } from "../api/analytics";
import { apiErrorMessage } from "../api/errorMessage";
import { queryKeys } from "../api/queryKeys";
import { AttendanceAnalyticsPanel } from "../components/AttendanceAnalyticsPanel";
import { SlowRequestNotice } from "../components/SlowRequestNotice";
import type { AnalyticsWindowDays } from "../types/domain";

export function StudentDashboard() {
  const [days, setDays] = useState<AnalyticsWindowDays>(7);
  const analytics = useQuery({
    queryKey: queryKeys.analyticsOverview(days),
    queryFn: () => analyticsApi.getOverview(days),
  });
  const student = analytics.data?.student_context;

  return (
    <section className="page-stack">
      <div className="page-heading">
        <p className="eyebrow">Student overview</p>
        <h1>Student portal</h1>
        <p>Understand your own recent attendance and open detailed records or announcements.</p>
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
      <div className="card-grid">
        <Link className="action-card" to="/student/attendance"><strong>My attendance</strong><span>Summary, filters, and records</span></Link>
        <Link className="action-card" to="/student/announcements"><strong>Announcements</strong><span>Notices available to you</span></Link>
      </div>
    </section>
  );
}
