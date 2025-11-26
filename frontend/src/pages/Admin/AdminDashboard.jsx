// frontend/src/pages/Admin/AdminDashboard.jsx
import React, { useEffect, useState } from "react";
import {
  PieChart, Pie, Cell, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Legend,
} from "recharts";
import CalendarHeatmap from "react-calendar-heatmap";
import "react-calendar-heatmap/dist/styles.css";
import {
  fetchClassrooms, fetchSubjects, fetchAttendanceStats,
  fetchStudents, fetchTeachers,
} from "../../api/api";
import ClassroomsPage from "./ClassroomsPage";
import SubjectsPage from "./SubjectsPage";
import StudentsPage from "./StudentsPage";
import TeachersPage from "./TeachersPage";

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
  const [leaderboard, setLeaderboard] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [subjects, setSubjects] = useState([]);
  const [subject, setSubject] = useState("");
  const [subjectStats, setSubjectStats] = useState([]);
  const [activeTab, setActiveTab] = useState("analytics");

  useEffect(() => {
    setError("");
    fetchClassrooms()
      .then((res) => setClasses(res.data.data || []))
      .catch(() => setError("Could not fetch classes"));
  }, []);

  useEffect(() => {
    if (activeTab !== "analytics") return;
    const params = {};
    if (classroom) params.classroom_id = classroom;
    fetchSubjects(params)
      .then((res) => setSubjects(res.data.data || []))
      .catch(() => setSubjects([]));
  }, [activeTab, classroom]);

  useEffect(() => {
    if (activeTab !== "analytics") return;
    fetchStats();
    // eslint-disable-next-line
  }, [classroom, dateRange.from, dateRange.to, activeTab]);

  useEffect(() => {
    if (activeTab !== "analytics") return;
    fetchLeaderboard();
    // eslint-disable-next-line
  }, [classroom, dateRange.from, dateRange.to, activeTab]);

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
    fetchAttendanceStats(buildStatsParams())
      .then((res) => setStats(res.data.data || []))
      .catch(() => setError("Could not fetch analytics"))
      .finally(() => setLoading(false));
  }
  function fetchLeaderboard() {
    if (!classroom) { setLeaderboard([]); return; }
    const params = buildStatsParams();
    fetchAttendanceStats(params)
      .then((res) => {
        const sorted = (res.data.data || []).slice().sort(
          (a, b) => (b.attendance_percent || 0) - (a.attendance_percent || 0)
        );
        setLeaderboard(sorted.slice(0, 5));
      })
      .catch(() => setLeaderboard([]));
  }
  function fetchSubjectStats() {
    if (!classroom || !subject) { setSubjectStats([]); return; }
    const params = { classroom_id: classroom, subject, };
    if (dateRange.from) params.from = dateRange.from;
    if (dateRange.to) params.to = dateRange.to;
    fetchAttendanceStats(params)
      .then((res) => setSubjectStats(res.data.data || []))
      .catch(() => setSubjectStats([]));
  }

  const total = stats.length;
  const totalPresent = stats.reduce((a, b) => a + (b.present_days || 0), 0);
  const totalAbsent = stats.reduce((a, b) => a + (b.absent_days || 0), 0);
  const overallRate = totalPresent + totalAbsent === 0
    ? 0 : (totalPresent / (totalPresent + totalAbsent)) * 100;
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
    <div className="space-y-6">
      {/* Tabs */}
      <div className="mb-4 flex gap-2 border-b border-slate-200">
        {/* ...tab buttons... (as in your code) */}
      </div>

      {activeTab === "analytics" && (
        <>
          {/* Stats Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
            <div className="bg-white rounded-xl p-5 shadow border">
              <div className="text-xs text-slate-500">Total Classes</div>
              <div className="text-2xl font-bold">{classes.length}</div>
            </div>
            <div className="bg-white rounded-xl p-5 shadow border">
              <div className="text-xs text-slate-500">Students</div>
              <div className="text-2xl font-bold">{/* Put dynamic count here */}</div>
            </div>
            {/* More cards... */}
            <div className="bg-white rounded-xl p-5 shadow border">
              <div className="text-xs text-slate-500">Attendance %</div>
              <div className="text-2xl font-bold">{overallRate.toFixed(1)}%</div>
            </div>
          </div>
          {/* Analytic charts, heatmap, leaderboard etc */}
        </>
      )}
      {activeTab === "classes" && <ClassroomsPage />}
      {activeTab === "subjects" && <SubjectsPage />}
      {activeTab === "students" && <StudentsPage />}
      {activeTab === "teachers" && <TeachersPage />}
    </div>
  );
}
