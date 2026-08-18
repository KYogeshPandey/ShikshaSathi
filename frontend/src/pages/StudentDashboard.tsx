import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { attendanceApi } from "../api/attendance";
import { apiErrorMessage } from "../api/errorMessage";
import { profilesApi } from "../api/profiles";
import { queryKeys } from "../api/queryKeys";

export function StudentDashboard() {
  const profile = useQuery({ queryKey: queryKeys.studentMe, queryFn: profilesApi.getMyStudentProfile });
  const stats = useQuery({ queryKey: [...queryKeys.studentAttendance, "summary"], queryFn: () => attendanceApi.getMyStats() });
  return (
    <section className="page-stack">
      <div className="page-heading"><p className="eyebrow">Student overview</p><h1>Student portal</h1><p>View your own profile, attendance summary, detailed attendance, and announcements.</p></div>
      {profile.error || stats.error ? <p className="error-message" role="alert">{apiErrorMessage(profile.error ?? stats.error)}</p> : null}
      <div className="metric-grid"><article className="metric-card"><span>Roll number</span><strong>{profile.data?.roll_number ?? "-"}</strong></article><article className="metric-card"><span>Total records</span><strong>{stats.data?.total_count ?? "-"}</strong></article><article className="metric-card"><span>Present</span><strong>{stats.data?.present_count ?? "-"}</strong></article><article className="metric-card"><span>Attendance</span><strong>{stats.data ? `${stats.data.attendance_percentage.toFixed(1)}%` : "-"}</strong></article></div>
      <div className="card-grid"><Link className="action-card" to="/student/attendance"><strong>My attendance</strong><span>Summary, filters, and records</span></Link><Link className="action-card" to="/student/announcements"><strong>Announcements</strong><span>Notices available to you</span></Link></div>
    </section>
  );
}
