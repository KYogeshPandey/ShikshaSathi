import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { academicsApi } from "../api/academics";
import { apiErrorMessage } from "../api/errorMessage";
import { profilesApi } from "../api/profiles";
import { queryKeys } from "../api/queryKeys";

export function TeacherDashboard() {
  const profile = useQuery({ queryKey: queryKeys.teacherMe, queryFn: profilesApi.getMyTeacherProfile });
  const classrooms = useQuery({ queryKey: queryKeys.classrooms, queryFn: () => academicsApi.listClassrooms() });
  const subjects = useQuery({ queryKey: queryKeys.subjects, queryFn: () => academicsApi.listSubjects() });
  const timetable = useQuery({ queryKey: queryKeys.timetable, queryFn: () => academicsApi.listTimetable() });
  const error = profile.error ?? classrooms.error ?? subjects.error ?? timetable.error;
  return (
    <section className="page-stack">
      <div className="page-heading"><p className="eyebrow">Teacher overview</p><h1>Teacher workspace</h1><p>Your API-authorized teaching scope and attendance tools.</p></div>
      {error ? <p className="error-message" role="alert">{apiErrorMessage(error)}</p> : null}
      <div className="metric-grid"><article className="metric-card"><span>Employee code</span><strong>{profile.data?.employee_code ?? "-"}</strong></article><article className="metric-card"><span>Classrooms</span><strong>{classrooms.data?.total ?? "-"}</strong></article><article className="metric-card"><span>Subjects</span><strong>{subjects.data?.total ?? "-"}</strong></article><article className="metric-card"><span>Timetable slots</span><strong>{timetable.data?.total ?? "-"}</strong></article></div>
      <div className="card-grid"><Link className="action-card" to="/teacher/attendance/manual"><strong>Manual attendance</strong><span>Load roster and save in bulk</span></Link><Link className="action-card" to="/teacher/attendance/recognition"><strong>Recognition attendance</strong><span>Camera or image workflow</span></Link><Link className="action-card" to="/teacher/reports"><strong>Reports</strong><span>Attendance, defaulters, leaderboard, and exports</span></Link><Link className="action-card" to="/teacher/announcements"><strong>Announcements</strong><span>Read school notices</span></Link></div>
    </section>
  );
}
