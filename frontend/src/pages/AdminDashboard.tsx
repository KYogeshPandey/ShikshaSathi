import { Link } from "react-router-dom";

export function AdminDashboard() {
  return (
    <section className="page-stack">
      <div className="page-heading"><p className="eyebrow">Admin overview</p><h1>Administration workspace</h1><p>Manage academic records, assignments, schedules, announcements, and validated bulk imports.</p></div>
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
