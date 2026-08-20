import { useQuery } from "@tanstack/react-query";
import { academicsApi } from "../api/academics";
import { apiErrorMessage } from "../api/errorMessage";
import { queryKeys } from "../api/queryKeys";
import { SlowRequestNotice } from "../components/SlowRequestNotice";

export function TeacherSchedulePage() {
  const classrooms = useQuery({ queryKey: queryKeys.classrooms, queryFn: () => academicsApi.listClassrooms() });
  const subjects = useQuery({ queryKey: queryKeys.subjects, queryFn: () => academicsApi.listSubjects() });
  const timetable = useQuery({ queryKey: queryKeys.timetable, queryFn: () => academicsApi.listTimetable() });
  const error = classrooms.error ?? subjects.error ?? timetable.error;
  return (
    <section className="page-stack">
      <div className="page-heading"><p className="eyebrow">Teaching scope</p><h1>My classes and timetable</h1><p>These records reflect your active teaching assignments.</p></div>
      {classrooms.isPending || subjects.isPending || timetable.isPending ? <p className="empty-state">Loading your teaching scope...</p> : null}
      {classrooms.isPending || subjects.isPending || timetable.isPending ? <SlowRequestNotice /> : null}
      {error ? <p className="error-message" role="alert">{apiErrorMessage(error)}</p> : null}
      <div className="card-grid">
        <div className="table-card"><h2>Classrooms</h2>{classrooms.data?.items.length === 0 ? <p className="empty-state">No classrooms assigned.</p> : null}<ul className="plain-list">{classrooms.data?.items.map((item) => <li key={item.id}><strong>{item.name}</strong><span>{item.code}</span></li>)}</ul></div>
        <div className="table-card"><h2>Subjects</h2>{subjects.data?.items.length === 0 ? <p className="empty-state">No subjects assigned.</p> : null}<ul className="plain-list">{subjects.data?.items.map((item) => <li key={item.id}><strong>{item.name}</strong><span>{item.code}</span></li>)}</ul></div>
      </div>
      <div className="table-card"><div className="table-card__header"><h2>Timetable</h2>{timetable.data ? <span>{timetable.data.total} slots</span> : null}</div>{timetable.data?.items.length === 0 ? <p className="empty-state">No timetable entries assigned.</p> : null}{timetable.data?.items.length ? <div className="table-scroll" role="region" aria-label="Assigned timetable" tabIndex={0}><table><thead><tr><th>Day</th><th>Time</th><th>Classroom</th><th>Subject</th></tr></thead><tbody>{timetable.data.items.map((item) => <tr key={item.id}><td>{item.day_of_week}</td><td>{item.start_time}-{item.end_time}</td><td>{item.classroom_id}</td><td>{item.subject_id}</td></tr>)}</tbody></table></div> : null}</div>
    </section>
  );
}
