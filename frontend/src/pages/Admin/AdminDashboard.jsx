// frontend/src/pages/Admin/AdminDashboard.jsx
import React, { useEffect, useState } from "react";
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
import { api } from "../../api/api";

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

export default function AdminDashboard() {
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

  // ----- Load class list -----
  useEffect(() => {
    setError("");
    api
      .get("/classrooms/")
      .then((res) => setClasses(res.data.data || []))
      .catch(() => setError("Could not fetch classes"));
  }, []);

  // ----- Load subjects for selected class -----
  useEffect(() => {
    if (!classroom) {
      setSubjects([]);
      return;
    }
    api
      .get(`/classrooms/${encodeURIComponent(classroom)}`)
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

  function buildStatsParams() {
    const params = {};
    if (classroom) params.classroom_id = classroom;
    if (dateRange.from) params.from = dateRange.from;
    if (dateRange.to) params.to = dateRange.to;
    return params;
  }

  function fetchStats() {
    setLoading(true);
    setError("");
    api
      .get("/attendance/stats", { params: buildStatsParams() })
      .then((res) => setStats(res.data.data || []))
      .catch(() => setError("Could not fetch analytics"))
      .finally(() => setLoading(false));
  }

  function fetchLeaderboard() {
    if (!classroom) {
      setLeaderboard([]);
      return;
    }
    const params = buildStatsParams();

    api
      .get("/attendance/stats", { params })
      .then((res) => {
        const sorted = (res.data.data || [])
          .slice()
          .sort(
            (a, b) => (b.attendance_percent || 0) - (a.attendance_percent || 0),
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
    const params = {
      classroom_id: classroom,
      subject,
    };
    if (dateRange.from) params.from = dateRange.from;
    if (dateRange.to) params.to = dateRange.to;

    api
      .get("/attendance/subject_stats", { params })
      .then((res) => setSubjectStats(res.data.data || []))
      .catch((err) => {
        console.warn("subject_stats API not implemented or failed", err);
        setSubjectStats([]);
      });
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
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-indigo-50 to-slate-100 p-6">
      {/* Top strip */}
      <div className="mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-extrabold text-slate-800 tracking-tight">
            Admin Analytics Dashboard
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Live overview of class-wise attendance, trends and top performers.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs md:text-sm text-slate-500 bg-white/60 backdrop-blur shadow-sm px-3 py-2 rounded-full">
          <span className="inline-block w-2 h-2 rounded-full bg-emerald-500 mr-1" />
          Backend status:{" "}
          <span className="font-semibold text-emerald-600">Online</span>
        </div>
      </div>

      {error && (
        <div className="mb-4 bg-red-50 text-red-800 border border-red-200 px-4 py-2 rounded text-center font-semibold">
          {error}
        </div>
      )}

      {/* Filters */}
      <div className="bg-white/80 backdrop-blur border border-slate-100 rounded-xl shadow-sm p-4 mb-6 flex flex-wrap items-center gap-4">
        <div className="flex flex-col">
          <span className="text-xs text-slate-500 mb-1">Class</span>
          <select
            className="px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 focus:outline-none focus:ring-2 focus:ring-indigo-500"
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
        </div>

        <div className="flex flex-col">
          <span className="text-xs text-slate-500 mb-1">From</span>
          <input
            type="date"
            className="px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            value={dateRange.from}
            onChange={(e) =>
              setDateRange((r) => ({ ...r, from: e.target.value }))
            }
          />
        </div>

        <div className="flex flex-col">
          <span className="text-xs text-slate-500 mb-1">To</span>
          <input
            type="date"
            className="px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            value={dateRange.to}
            onChange={(e) =>
              setDateRange((r) => ({ ...r, to: e.target.value }))
            }
          />
        </div>

        <button
          className="mt-4 md:mt-6 bg-indigo-600 text-white px-4 py-2 rounded-lg shadow hover:bg-indigo-700 transition disabled:bg-slate-400 ml-auto"
          onClick={() => exportToCSV(stats, "attendance.csv")}
          disabled={!stats.length}
        >
          Export Attendance CSV
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <div className="bg-white/90 backdrop-blur shadow-sm rounded-xl p-4 text-center border border-slate-100">
          <div className="text-xs font-semibold text-slate-500 mb-1">
            Total Students
          </div>
          <div className="text-3xl font-extrabold text-indigo-700">{total}</div>
        </div>
        <div className="bg-white/90 backdrop-blur shadow-sm rounded-xl p-4 text-center border border-slate-100">
          <div className="text-xs font-semibold text-slate-500 mb-1">
            Present
          </div>
          <div className="text-3xl font-extrabold text-emerald-500">
            {totalPresent}
          </div>
        </div>
        <div className="bg-white/90 backdrop-blur shadow-sm rounded-xl p-4 text-center border border-slate-100">
          <div className="text-xs font-semibold text-slate-500 mb-1">
            Absent
          </div>
          <div className="text-3xl font-extrabold text-red-400">
            {totalAbsent}
          </div>
        </div>
        <div className="bg-white/90 backdrop-blur shadow-sm rounded-xl p-4 text-center border border-slate-100">
          <div className="text-xs font-semibold text-slate-500 mb-1">
            Overall Rate
          </div>
          <div className="text-3xl font-extrabold text-amber-500">
            {overallRate.toFixed(2)}%
          </div>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-8">
        {/* Pie + Legend */}
        <div className="bg-white rounded-xl shadow-sm p-4 flex flex-col md:flex-row items-center border border-slate-100">
          <div className="flex-1">
            <div className="mb-2 font-semibold text-slate-700">
              Attendance Distribution
            </div>
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
          <div className="ml-6 flex flex-col items-start space-y-2 border-l pl-4">
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
                <span className="text-sm text-slate-700 font-semibold">
                  {item.name}: {item.value}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Bar chart */}
        <div className="bg-white rounded-xl shadow-sm p-4 border border-slate-100">
          <div className="mb-2 font-semibold text-slate-700">
            Student-wise Attendance
          </div>
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
      <div className="bg-white rounded-xl shadow-sm p-6 mb-8 flex border border-slate-100">
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
      <div className="bg-white border border-slate-100 rounded-xl shadow-sm p-4 mb-8">
        <div className="mb-2 flex items-center gap-4">
          <span className="font-semibold text-slate-700">
            Subject-wise Analytics
          </span>
          <select
            className="border border-slate-200 px-2 py-1 rounded-lg bg-slate-50 focus:outline-none focus:ring-2 focus:ring-indigo-500"
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
            className="bg-indigo-600 text-white px-3 py-1 rounded-lg"
          >
            Fetch
          </button>
          <button
            className="ml-2 bg-blue-500 text-white px-3 py-1 rounded-lg"
            onClick={() => exportToCSV(subjectStats, "subjectwise.csv")}
            disabled={!subjectStats.length}
          >
            Export Subject CSV
          </button>
        </div>
        {subjectStats.length > 0 && (
          <table className="w-full text-center mt-2 text-sm">
            <thead>
              <tr className="bg-slate-100">
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
          <div className="text-gray-400 mt-2 text-sm">No data…</div>
        )}
      </div>

      {/* Leaderboard */}
      <div className="bg-white border border-slate-100 rounded-xl shadow-sm p-4 mb-8">
        <div className="font-semibold mb-2 text-slate-700">
          Top Performers (Attendance %)
        </div>
        <table className="w-full text-center text-sm">
          <thead>
            <tr className="bg-slate-100">
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
