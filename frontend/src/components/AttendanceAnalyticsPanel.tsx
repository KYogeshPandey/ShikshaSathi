import type {
  AnalyticsOverview,
  AnalyticsTrendPoint,
  AnalyticsWindowDays,
} from "../types/domain";
import {
  attendanceInsight,
  formatAttendancePercentage,
} from "../lib/attendanceAnalytics";

interface AttendanceAnalyticsPanelProps {
  overview: AnalyticsOverview;
  days: AnalyticsWindowDays;
  onDaysChange: (days: AnalyticsWindowDays) => void;
}

const dateFormatter = new Intl.DateTimeFormat("en-US", {
  day: "numeric",
  month: "short",
  timeZone: "UTC",
});
const dateWithYearFormatter = new Intl.DateTimeFormat("en-US", {
  day: "numeric",
  month: "short",
  timeZone: "UTC",
  year: "numeric",
});

function parseDate(value: string): Date {
  return new Date(`${value}T00:00:00Z`);
}

function formatDate(value: string): string {
  return dateFormatter.format(parseDate(value));
}

function formatPeriod(dateFrom: string, dateTo: string): string {
  return `${formatDate(dateFrom)}–${dateWithYearFormatter.format(parseDate(dateTo))}`;
}

function AttendanceTrendChart({
  points,
  description,
}: {
  points: AnalyticsTrendPoint[];
  description: string;
}) {
  const chartLeft = 42;
  const chartWidth = 642;
  const chartBottom = 180;
  const chartHeight = 156;
  const step = chartWidth / points.length;
  const barWidth = Math.max(5, step * 0.56);
  const labelIndexes = new Set([0, Math.floor((points.length - 1) / 2), points.length - 1]);

  return (
    <figure className="attendance-trend">
      <svg
        aria-labelledby="attendance-trend-title attendance-trend-description"
        className="attendance-trend__svg"
        role="img"
        viewBox="0 0 700 222"
      >
        <title id="attendance-trend-title">Daily attendance rate</title>
        <desc id="attendance-trend-description">{description}</desc>
        <g aria-hidden="true">
          {[100, 50, 0].map((rate) => {
            const y = chartBottom - (rate / 100) * chartHeight;
            return (
              <g key={rate}>
                <line className="attendance-trend__gridline" x1={chartLeft} x2="688" y1={y} y2={y} />
                <text className="attendance-trend__axis-label" x="35" y={y + 4} textAnchor="end">
                  {rate}%
                </text>
              </g>
            );
          })}
          {points.map((point, index) => {
            const x = chartLeft + index * step + (step - barWidth) / 2;
            const barHeight = (point.attendance_percentage / 100) * chartHeight;
            const labelX = chartLeft + index * step + step / 2;
            return (
              <g key={point.attendance_date}>
                {point.total_count > 0 ? (
                  <rect
                    className="attendance-trend__bar"
                    height={Math.max(barHeight, 2)}
                    rx="3"
                    width={barWidth}
                    x={x}
                    y={chartBottom - Math.max(barHeight, 2)}
                  />
                ) : (
                  <circle
                    className="attendance-trend__no-data"
                    cx={labelX}
                    cy={chartBottom}
                    r={points.length === 7 ? 3 : 2}
                  />
                )}
                {labelIndexes.has(index) ? (
                  <text
                    className="attendance-trend__date-label"
                    textAnchor={index === 0 ? "start" : index === points.length - 1 ? "end" : "middle"}
                    x={index === 0 ? chartLeft : index === points.length - 1 ? 688 : labelX}
                    y="211"
                  >
                    {formatDate(point.attendance_date)}
                  </text>
                ) : null}
              </g>
            );
          })}
        </g>
      </svg>
      <figcaption>
        Teal bars show attendance for days with marked records; gray dots mean no attendance was
        marked that day.
      </figcaption>
    </figure>
  );
}

export function AttendanceAnalyticsPanel({
  overview,
  days,
  onDaysChange,
}: AttendanceAnalyticsPanelProps) {
  const insight = attendanceInsight(overview);
  const hasMarkedData = overview.trend.some((point) => point.total_count > 0);
  const periodLabel = formatPeriod(overview.period.date_from, overview.period.date_to);

  return (
    <section aria-labelledby="attendance-analytics-title" className="table-card analytics-panel">
      <div className="analytics-panel__header">
        <div>
          <p className="eyebrow">Attendance analytics</p>
          <h2 id="attendance-analytics-title">Recent attendance trend</h2>
          <p>{periodLabel} · daily marked records</p>
        </div>
        <div aria-label="Attendance period" className="analytics-period" role="group">
          {([7, 30] as const).map((windowDays) => (
            <button
              aria-pressed={days === windowDays}
              className={`analytics-period__button${days === windowDays ? " analytics-period__button--active" : ""}`}
              key={windowDays}
              onClick={() => onDaysChange(windowDays)}
              type="button"
            >
              Last {windowDays} days
            </button>
          ))}
        </div>
      </div>

      <dl className="analytics-summary" aria-label="Attendance summary">
        <div><dt>Attendance</dt><dd>{formatAttendancePercentage(overview.attendance.attendance_percentage)}</dd></div>
        <div><dt>Present</dt><dd>{overview.attendance.present_count}</dd></div>
        <div><dt>Absent</dt><dd>{overview.attendance.absent_count}</dd></div>
        <div><dt>Marked records</dt><dd>{overview.attendance.total_count}</dd></div>
      </dl>

      <p className="analytics-insight">{insight}</p>
      <p className="analytics-definition">
        Attendance = present ÷ all marked records. Missing or unmarked records are excluded, not
        counted as absent.
      </p>

      {hasMarkedData ? (
        <AttendanceTrendChart points={overview.trend} description={`${periodLabel}. ${insight}`} />
      ) : (
        <p className="empty-state">No attendance data is available for this period.</p>
      )}

      <details className="analytics-details">
        <summary>View daily attendance values</summary>
        <div aria-label="Daily attendance values" className="table-scroll" role="region" tabIndex={0}>
          <table>
            <thead><tr><th>Date</th><th>Marked</th><th>Present</th><th>Absent</th><th>Attendance</th></tr></thead>
            <tbody>
              {overview.trend.map((point) => (
                <tr key={point.attendance_date}>
                  <td>{formatDate(point.attendance_date)}</td>
                  <td>{point.total_count}</td>
                  <td>{point.present_count}</td>
                  <td>{point.absent_count}</td>
                  <td>{point.total_count > 0 ? formatAttendancePercentage(point.attendance_percentage) : "No marked records"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}
