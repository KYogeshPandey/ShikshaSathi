import { useQuery } from "@tanstack/react-query";
import { academicsApi } from "../api/academics";
import { apiErrorMessage } from "../api/errorMessage";
import { queryKeys } from "../api/queryKeys";
import { SlowRequestNotice } from "../components/SlowRequestNotice";

export function StudentTimetablePage() {
  const classrooms = useQuery({
    queryKey: queryKeys.classrooms,
    queryFn: () => academicsApi.listClassrooms(),
  });
  const subjects = useQuery({
    queryKey: queryKeys.subjects,
    queryFn: () => academicsApi.listSubjects(),
  });
  const timetable = useQuery({
    queryKey: queryKeys.timetable,
    queryFn: () => academicsApi.listTimetable(),
  });
  const classroomNames = new Map(
    classrooms.data?.items.map((classroom) => [classroom.id, classroom.name]) ?? [],
  );
  const subjectNames = new Map(
    subjects.data?.items.map((subject) => [subject.id, subject.name]) ?? [],
  );
  const pending = classrooms.isPending || subjects.isPending || timetable.isPending;
  const error = classrooms.error ?? subjects.error ?? timetable.error;

  return (
    <section className="page-stack">
      <div className="page-heading">
        <p className="eyebrow">Your schedule</p>
        <h1>Weekly timetable</h1>
        <p>Review the active classes scheduled for your current classroom.</p>
      </div>
      {pending ? <p className="empty-state">Loading your weekly timetable…</p> : null}
      {pending ? <SlowRequestNotice /> : null}
      {error ? <p className="error-message" role="alert">{apiErrorMessage(error)}</p> : null}
      <div className="table-card">
        <div className="table-card__header"><h2>Class schedule</h2>{timetable.data ? <span>{timetable.data.total} scheduled classes</span> : null}</div>
        {timetable.data?.items.length === 0 ? <p className="empty-state">No active timetable entries are available.</p> : null}
        {timetable.data?.items.length ? (
          <div aria-label="Student weekly timetable" className="table-scroll" role="region" tabIndex={0}>
            <table>
              <thead><tr><th>Day</th><th>Time</th><th>Subject</th><th>Classroom</th></tr></thead>
              <tbody>
                {timetable.data.items.map((entry) => (
                  <tr key={entry.id}>
                    <td>{entry.day_of_week[0].toUpperCase() + entry.day_of_week.slice(1)}</td>
                    <td>{entry.start_time.slice(0, 5)}–{entry.end_time.slice(0, 5)}</td>
                    <td>{subjectNames.get(entry.subject_id) ?? "Assigned subject"}</td>
                    <td>{classroomNames.get(entry.classroom_id) ?? "Your classroom"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    </section>
  );
}
