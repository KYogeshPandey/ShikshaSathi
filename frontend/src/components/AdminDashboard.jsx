import React, { useEffect, useState } from "react";
import axios from "axios";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from "recharts";
import CalendarHeatmap from "react-calendar-heatmap";
import "react-calendar-heatmap/dist/styles.css";

const COLORS = ["#34D399", "#F87171", "#FBBF24", "#60A5FA"];

function exportToCSV(data, fileName = "export.csv") {
  if (!data?.length) return;
  const keys = Object.keys(data[0] || {});
  const rows = [
    keys.join(","),
    ...data.map((row) => keys.map((k) => JSON.stringify(row[k] ?? "")).join(",")),
  ];
  const blob = new Blob([rows.join("\n")], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = fileName;
  a.click();
}

export default function AdminDashboard({ token }) {
  const [classes, setClasses] = useState([]);
  const [classroom, setClassroom] = useState("");
  const [dateRange, setDateRange] = useState({ from: "", to: "" });
  const [stats, setStats] = useState([]);
  const [loading, setLoading] = useState(false);
  const [leaderboard, setLeaderboard] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [subject, setSubject] = useState("");
  const [subjectStats, setSubjectStats] = useState([]);
  const [error, setError] = useState("");

  // ✅ Get token from localStorage if not passed as prop
  const authToken = token || localStorage.getItem("token");

  // ----- Load class list -----
  useEffect(() => {
    if (!authToken) return;
    setError("");
    axios
      .get("/api/v1/classrooms/")
      .then((res) => setClasses(res.data.data || []))
      .catch(() => setError("Could not fetch classes"));
  }, [authToken]);

  // ----- Load subjects for selected class -----
  useEffect(() => {
    if (!classroom) {
      setSubjects([]);
      return;
    }
    axios
      .get(`/api/v1/classrooms/${encodeURIComponent(classroom)}`)
      .then((res) => setSubjects(res.data.data?.subjects || []))
      .catch(() => setSubjects([]));
  }, [classroom]);

  // ----- Fetch stats when filters change -----
  useEffect(() => {
    fetchStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classroom, dateRange.from, dateRange.to]);

  // ----- Fetch leaderboard -----
  useEffect(() => {
    fetchLeaderboard();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classroom, dateRange.from, dateRange.to]);

  function buildStatsUrl() {
    let url = "/api/v1/attendance/stats?";
    if (classroom) url += `classroom_id=${encodeURIComponent(classroom)}&`;
    if (dateRange.from) url += `from=${dateRange.from}&`;
    if (dateRange.to) url += `to=${dateRange.to}`;
    return url;
  }

  function fetchStats() {
    setLoading(true);
    setError("");
    axios
      .get(buildStatsUrl())
      .then((res) => setStats(res.data.data || []))
      .catch(() => setError("Could not fetch analytics"))
      .finally(() => setLoading(false));
  }

  function fetchLeaderboard() {
    if (!classroom) {
      setLeaderboard([]);
      return;
    }
    let url = `/api/v1/attendance/stats?classroom_id=${encodeURIComponent(
      classroom
    )}`;
    if (dateRange.from) url += `&from=${dateRange.from}`;
    if (dateRange.to) url += `&to=${dateRange.to}`;

    axios
      .get(url)
      .then((res) => {
        const sorted = (res.data.data || [])
          .slice()
          .sort(
            (a, b) => (b.attendance_percent || 0) - (a.attendance_percent || 0)
          );
        setLeaderboard(sorted.slice(0, 5));
      })
      .catch(() => setLeaderboard([]));
  }

  function fetchSubjectStats() {
    if (!classroom || !subject) {
      setSubjectStats([]);
      return;
    }
    let url = `/api/v1/attendance/subject_stats?classroom_id=${encodeURIComponent(
      classroom
    )}&subject=${encodeURIComponent(subject)}`;
    if (dateRange.from) url += `&from=${dateRange.from}`;
    if (dateRange.to) url += `&to=${dateRange.to}`;

    axios
      .get(url)
      .then((res) => setSubjectStats(res.data.data || []))
      .catch(() => setSubjectStats([]));
  }

  const total = stats.length;
  const totalPresent = stats.reduce((a, b) => a + (b.present_days || 0), 0);
  const totalAbsent = stats.reduce((a, b) => a + (b.absent_days || 0), 0);
  const overallRate =
    totalPresent + totalAbsent === 0
      ? 0
      : (totalPresent / (totalPresent + totalAbsent)) * 100;

  const pieData = [
    { name: "Present", value: totalPresent },
    { name: "Absent", value: totalAbsent },
  ];

  const heatmapData = stats
    .filter((s) => s.date)
    .map((s) => ({
      date: s.date,
      count: s.present_days || 0,
    }));

  return (
    <div className="p-6">
      {error && (
        <div className="mb-4 bg-red-100 text-red-800 border border-red-200 px-4 py-2 rounded text-center font-semibold">
          {error}
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4 mb-5">
        <select
          className="px-3 py-2 rounded border shadow"
          value={classroom}
          onChange={(e) => setClassroom(e.target.value)}
        >
          <option value="">All Classes</option>
          {classes.map((cls) => (
            <option key={cls._id || cls.name} value={cls._id || cls.name}>
              {cls.name}
            </option>
          ))}
        </select>

        <input
          type="date"
          className="px-2 py-1 border rounded"
          value={dateRange.from}
          onChange={(e) =>
            setDateRange((r) => ({ ...r, from: e.target.value }))
          }
        />
        <input
          type="date"
          className="px-2 py-1 border rounded"
          value={dateRange.to}
          onChange={(e) => setDateRange((r) => ({ ...r, to: e.target.value }))
          }
        />
        <button
          className="bg-blue-600 text-white px-4 py-2 rounded shadow hover:bg-blue-800 ml-5"
          onClick={() => exportToCSV(stats, "attendance.csv")}
          disabled={!stats.length}
        >
          Export CSV
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <div className="bg-white shadow rounded p-5 text-center">
          <div className="text-xs font-bold text-gray-500 mb-1">
            Total Students
          </div>
          <div className="text-3xl font-bold text-indigo-700">{total}</div>
        </div>
        <div className="bg-white shadow rounded p-5 text-center">
          <div className="text-xs font-bold text-gray-500 mb-1">Present</div>
          <div className="text-3xl text-green-600">{totalPresent}</div>
        </div>
        <div className="bg-white shadow rounded p-5 text-center">
          <div className="text-xs font-bold text-gray-500 mb-1">Absent</div>
          <div className="text-3xl text-red-400">{totalAbsent}</div>
        </div>
        <div className="bg-white shadow rounded p-5 text-center">
          <div className="text-xs font-bold text-gray-500 mb-1">
            Overall Rate
          </div>
          <div className="text-3xl text-yellow-600">
            {overallRate.toFixed(2)}%
          </div>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-8">
        {/* Pie + Legend */}
        <div className="bg-white rounded shadow p-4 flex flex-col md:flex-row items-center">
          <div className="flex-1">
            <div className="mb-2 font-semibold">Attendance Pie</div>
            <ResponsiveContainer width="100%" height={180}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={40}
                  outerRadius={60}
                  fill="#8884d8"
                  dataKey="value"
                  label
                >
                  {pieData.map((entry, index) => (
                    <Cell
                      key={`pie-slice-${entry.name}`}
                      fill={COLORS[index % COLORS.length]}
                    />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="ml-8 flex flex-col items-start space-y-2 border-l pl-4">
            {pieData.map((item, idx) => (
              <div key={`pie-legend-${item.name}`} className="flex items-center">
                <span
                  style={{
                    background: COLORS[idx],
                    display: "inline-block",
                    width: 14,
                    height: 14,
                    borderRadius: 3,
                    marginRight: 7,
                  }}
                />
                <span className="text-sm text-gray-700 font-bold">
                  {item.name}: {item.value}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Bar chart */}
        <div className="bg-white rounded shadow p-4">
          <div className="mb-2 font-semibold">Bar Chart (Student-wise)</div>
          <ResponsiveContainer
            width="100%"
            minWidth={220}
            minHeight={120}
            height={220}
          >
            <BarChart data={stats}>
              <XAxis
                dataKey="student_id"
                label={{
                  value: "Student ID",
                  position: "insideBottom",
                  offset: -2,
                }}
              />
              <YAxis
                label={{
                  value: "Classes",
                  angle: -90,
                  position: "insideLeft",
                  offset: -4,
                }}
              />
              <Tooltip
                formatter={(val, name) => [
                  val,
                  name === "present_days" ? "Present" : "Absent",
                ]}
              />
              <Legend
                formatter={(value) =>
                  value === "present_days" ? "Present" : "Absent"
                }
              />
              <Bar dataKey="present_days" fill="#34D399" name="Present" />
              <Bar dataKey="absent_days" fill="#F87171" name="Absent" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Heatmap */}
      <div className="bg-white rounded shadow p-6 mb-8 flex">
        <div
          style={{
            minWidth: 140,
            maxWidth: 170,
            margin: "0 16px 0 0",
            display: "flex",
            justifyContent: "flex-start",
          }}
        >
          <CalendarHeatmap
            startDate={dateRange.from || "2025-11-01"}
            endDate={dateRange.to || "2025-11-30"}
            values={heatmapData}
            classForValue={(value) =>
              !value
                ? "color-empty"
                : value.count > 10
                ? "color-github-4"
                : value.count > 5
                ? "color-github-3"
                : value.count > 0
                ? "color-github-2"
                : "color-github-1"
            }
          />
        </div>
      </div>

      {/* Subject-wise */}
      <div className="bg-white border rounded shadow p-4 mb-8">
        <div className="mb-2 flex items-center gap-4">
          <span className="font-semibold">Subject-wise Analytics</span>
          <select
            className="border px-2 py-1 rounded"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
          >
            <option value="">All Subjects</option>
            {subjects.map((sub) => (
              <option key={sub} value={sub}>
                {sub}
              </option>
            ))}
          </select>
          <button
            onClick={fetchSubjectStats}
            className="bg-indigo-600 text-white px-3 py-1 rounded"
          >
            Fetch
          </button>
          <button
            className="ml-2 bg-blue-500 text-white px-3 py-1 rounded"
            onClick={() => exportToCSV(subjectStats, "subjectwise.csv")}
            disabled={!subjectStats.length}
          >
            Export Subject CSV
          </button>
        </div>
        {subjectStats.length > 0 && (
          <table className="w-full text-center mt-2">
            <thead>
              <tr className="bg-gray-100">
                <th className="py-1">Student ID</th>
                <th className="py-1">Present</th>
                <th className="py-1">Absent</th>
                <th className="py-1">%</th>
              </tr>
            </thead>
            <tbody>
              {subjectStats.map((row) => (
                <tr key={row.student_id}>
                  <td className="py-1">{row.student_id}</td>
                  <td className="py-1">{row.present_days}</td>
                  <td className="py-1">{row.absent_days}</td>
                  <td className="py-1">
                    {(row.attendance_percent || 0).toFixed(2)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {subjectStats.length === 0 && (
          <div className="text-gray-400 mt-2">No data…</div>
        )}
      </div>

      {/* Leaderboard */}
      <div className="bg-white border rounded shadow p-4 mb-8">
        <div className="font-semibold mb-2">
          Top Performers (Attendance %)
        </div>
        <table className="w-full text-center">
          <thead>
            <tr className="bg-gray-100">
              <th className="py-1">#</th>
              <th className="py-1">Student ID</th>
              <th className="py-1">Present</th>
              <th className="py-1">Absent</th>
              <th className="py-1">%</th>
            </tr>
          </thead>
          <tbody>
            {leaderboard.map((row, idx) => (
              <tr key={row.student_id || idx}>
                <td className="py-1">{idx + 1}</td>
                <td className="py-1">{row.student_id}</td>
                <td className="py-1">{row.present_days}</td>
                <td className="py-1">{row.absent_days}</td>
                <td className="py-1">
                  {(row.attendance_percent || 0).toFixed(2)}%
                </td>
              </tr>
            ))}
            {leaderboard.length === 0 && (
              <tr>
                <td colSpan={5} className="text-gray-400 py-2">
                  No data…
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {loading && (
        <div className="my-4 flex justify-center">
          <span className="text-blue-700 animate-pulse font-semibold">
            Loading...
          </span>
        </div>
      )}
    </div>
  );
}
