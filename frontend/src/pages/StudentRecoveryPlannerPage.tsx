import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { attendanceApi } from "../api/attendance";
import { apiErrorMessage } from "../api/errorMessage";
import { queryKeys } from "../api/queryKeys";
import { SlowRequestNotice } from "../components/SlowRequestNotice";
import type {
  AttendancePlanStatus,
  AttendanceRecoveryPlanRequest,
} from "../types/domain";

function localIsoDate(offsetDays = 0): string {
  const value = new Date();
  value.setDate(value.getDate() + offsetDays);
  const offset = value.getTimezoneOffset() * 60_000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 10);
}

function formatDate(value: string | null): string {
  if (!value) return "Not available";
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

function planStatusLabel(status: AttendancePlanStatus): string {
  return {
    safe: "At or above target",
    recovery_possible: "Recovery possible",
    tight_recovery: "Tight recovery",
    not_reachable: "Not reachable by deadline",
  }[status];
}

function plannerMessage(
  status: AttendancePlanStatus,
  target: number,
  classesRequired: number | null,
  classesRemaining: number,
  deadline: string,
  projectedMax: number,
): string {
  if (status === "safe") return `Your attendance is currently at or above the ${target}% target.`;
  if (status === "not_reachable") {
    return `${target}% cannot be reached before ${formatDate(deadline)}. Attend all ${classesRemaining} remaining scheduled classes. Maximum projected attendance: ${projectedMax.toFixed(1)}%.`;
  }
  if (status === "tight_recovery") {
    return `Attend the next ${classesRequired ?? 0} scheduled classes before the deadline. Avoid further absences.`;
  }
  return `Attend the next ${classesRequired ?? 0} scheduled classes to reach ${target}%.`;
}

export function StudentRecoveryPlannerPage() {
  const [target, setTarget] = useState("75");
  const [deadline, setDeadline] = useState(localIsoDate(30));
  const [subjectId, setSubjectId] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [appliedPlan, setAppliedPlan] = useState<AttendanceRecoveryPlanRequest>({
    target_percentage: 75,
    deadline: localIsoDate(30),
  });
  const planner = useQuery({
    queryKey: queryKeys.attendanceRecoveryPlan(appliedPlan),
    queryFn: () => attendanceApi.getRecoveryPlan(appliedPlan),
  });

  const calculatePlan = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const parsedTarget = Number(target);
    if (!Number.isFinite(parsedTarget) || parsedTarget <= 0 || parsedTarget > 100) {
      setFormError("Target attendance must be greater than 0 and at most 100%.");
      return;
    }
    if (!deadline || deadline < localIsoDate()) {
      setFormError("Plan until must be today or a future date.");
      return;
    }
    setFormError(null);
    const nextPlan = {
      target_percentage: parsedTarget,
      deadline,
      subject_id: subjectId || undefined,
    };
    const unchanged = JSON.stringify(nextPlan) === JSON.stringify(appliedPlan);
    setAppliedPlan(nextPlan);
    if (unchanged) void planner.refetch();
  };

  return (
    <section className="page-stack">
      <div className="page-heading">
        <p className="eyebrow">Decision support</p>
        <h1>Attendance Recovery Planner</h1>
        <p>Estimate the scheduled classes needed to reach an overall or subject attendance target.</p>
      </div>
      {planner.isPending ? <p className="empty-state">Preparing your recovery plan…</p> : null}
      {planner.isPending ? <SlowRequestNotice /> : null}
      {planner.error ? (
        <div className="error-message" role="alert">
          <p>{apiErrorMessage(planner.error)}</p>
          <button className="button button--quiet" onClick={() => void planner.refetch()} type="button">Retry planner</button>
        </div>
      ) : null}
      {planner.data ? (
        <section aria-labelledby="recovery-planner-title" className="form-card planner-card">
          <div className="planner-card__heading">
            <div><p className="eyebrow">Your plan</p><h2 id="recovery-planner-title">Target and deadline</h2></div>
            <span className={`planner-status planner-status--${planner.data.status}`}>{planStatusLabel(planner.data.status)}</span>
          </div>
          <form onSubmit={calculatePlan} noValidate>
            <div className="form-grid">
              <label className="field"><span>Plan for</span><select value={subjectId} onChange={(event) => setSubjectId(event.target.value)}><option value="">Overall attendance</option>{planner.data.subjects.map((subject) => <option key={subject.subject_id} value={subject.subject_id}>{subject.subject_name}</option>)}</select></label>
              <label className="field"><span>Target attendance</span><input max="100" min="0.1" onChange={(event) => setTarget(event.target.value)} step="0.1" type="number" value={target} /></label>
              <label className="field"><span>Plan until</span><input min={localIsoDate()} onChange={(event) => setDeadline(event.target.value)} type="date" value={deadline} /></label>
            </div>
            <button className="button button--primary" disabled={planner.isFetching} type="submit">{planner.isFetching ? "Calculating…" : "Calculate plan"}</button>
            {formError ? <p className="error-message" role="alert">{formError}</p> : null}
          </form>
          <div aria-live="polite" className="planner-result">
            <p className="planner-result__message">{plannerMessage(planner.data.status, planner.data.target_percentage, planner.data.classes_required, planner.data.scheduled_classes_remaining, planner.data.deadline, planner.data.projected_max_percentage)}</p>
            <dl className="planner-result__grid">
              <div><dt>Current attendance</dt><dd>{planner.data.current.percentage.toFixed(1)}%</dd></div>
              <div><dt>Classes required</dt><dd>{planner.data.classes_required ?? "No finite recovery"}</dd></div>
              <div><dt>Teaching days required</dt><dd>{planner.data.teaching_days_required ?? "Not available"}</dd></div>
              <div><dt>Estimated recovery date</dt><dd>{formatDate(planner.data.recovery_date)}</dd></div>
              <div><dt>{planner.data.reachable ? "Projected attendance" : "Maximum projected attendance"}</dt><dd>{planner.data.projected_attendance_percentage.toFixed(1)}%</dd></div>
              <div><dt>Attendance buffer after recovery</dt><dd>{planner.data.attendance_buffer_classes} scheduled {planner.data.attendance_buffer_classes === 1 ? "class" : "classes"}</dd></div>
            </dl>
            <p className="planner-buffer-note">Assuming you attend all other scheduled classes before the deadline, this buffer remains at or above the selected target.</p>
            <p className="planner-assumption">{planner.data.schedule_assumption} Actual eligibility may depend on your institution’s attendance rules and schedule changes.</p>
          </div>
        </section>
      ) : null}
    </section>
  );
}
