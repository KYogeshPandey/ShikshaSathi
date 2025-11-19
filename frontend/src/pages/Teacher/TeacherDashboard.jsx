// frontend/src/pages/Teacher/TeacherDashboard.jsx
import React, { useEffect, useState } from "react";
import { api } from "../../api/api";
import AttendancePage from "../Teacher/AttendancePage";

function exportToCSV(data, fileName = "attendance.csv") {
  if (!data?.length) return;
  const keys = Object.keys(data[0]);
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

export default function TeacherDashboard() {
  const [mode, setMode] = useState("overview"); // "overview" or "attendance"

  const [classes, setClasses] = useState([]);
  const [selectedClass, setSelectedClass] = useState("");
  const [attendance, setAttendance] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // ---- Hooks always at top ----
  // Load all classes assigned to teacher (currently same as all classrooms)
  useEffect(() => {
    setError("");
    api
      .get("/classrooms/")
      .then((res) => setClasses(res.data.data || []))
      .catch(() => setError("Could not fetch your classes!"));
  }, []);

  // Fetch attendance of selected class
  useEffect(() => {
    if (!selectedClass) {
      setAttendance([]);
      return;
    }
    setLoading(true);
    setError("");
    api
      .get("/attendance/stats", {
        params: { classroom_id: selectedClass },
      })
      .then((res) => setAttendance(res.data.data || []))
      .catch(() => setError("Could not fetch attendance for this class!"))
      .finally(() => setLoading(false));
  }, [selectedClass]);

  const totalStudents = attendance.length;
  const avgPercent =
    totalStudents === 0
      ? 0
      : attendance.reduce((a, b) => a + (b.attendance_percent || 0), 0) /
        totalStudents;

  // ---- Conditional render (after hooks) ----
  if (mode === "attendance") {
    return <AttendancePage onBack={() => setMode("overview")} />;
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-emerald-50 via-sky-50 to-slate-50 p-6">
      {/* Header */}
      <div className="mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h2 className="text-3xl font-extrabold text-emerald-800 tracking-tight">
            Teacher Dashboard
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            Quickly review class-wise attendance and export reports.
          </p>
        </div>
        <div className="flex flex-col md:flex-row gap-3 items-center">
          <div className="bg-white/80 backdrop-blur px-4 py-2 rounded-full shadow-sm text-xs text-slate-600 flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-emerald-500" />
            <span>Focus: Live class attendance overview</span>
          </div>
          <button
            type="button"
            onClick={() => setMode("attendance")}
            className="bg-emerald-600 text-white text-xs md:text-sm px-4 py-2 rounded-full shadow hover:bg-emerald-700 transition"
          >
            Mark Today&apos;s Attendance
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 text-red-800 border border-red-200 px-4 py-2 rounded mb-4 text-sm">
          {error}
        </div>
      )}

      {/* Class selector & summary */}
      <div className="bg-white/90 backdrop-blur border border-slate-100 rounded-xl shadow-sm p-4 mb-6 flex flex-col md:flex-row md:items-center gap-4">
        <div className="flex flex-col">
          <span className="text-xs text-slate-500 mb-1">Select Class</span>
          <select
            className="border border-slate-200 rounded-lg px-3 py-2 bg-slate-50 focus:outline-none focus:ring-2 focus:ring-emerald-500"
            value={selectedClass}
            onChange={(e) => setSelectedClass(e.target.value)}
          >
            <option value="">-- Choose class --</option>
            {classes.map((cls) => (
              <option key={cls._id || cls.name} value={cls._id || cls.name}>
                {cls.name}
              </option>
            ))}
          </select>
        </div>

        <div className="flex-1 grid grid-cols-2 md:grid-cols-3 gap-3 text-center">
          <div className="bg-emerald-50 rounded-lg py-3 border border-emerald-100">
            <div className="text-[11px] text-emerald-700 font-semibold uppercase tracking-wide">
              Students
            </div>
            <div className="text-xl font-bold text-emerald-900">
              {totalStudents}
            </div>
          </div>
          <div className="bg-sky-50 rounded-lg py-3 border border-sky-100">
            <div className="text-[11px] text-sky-700 font-semibold uppercase tracking-wide">
              Avg Attendance
            </div>
            <div className="text-xl font-bold text-sky-900">
              {avgPercent.toFixed(1)}%
            </div>
          </div>
          <div className="bg-amber-50 rounded-lg py-3 border border-amber-100 col-span-2 md:col-span-1">
            <div className="text-[11px] text-amber-700 font-semibold uppercase tracking-wide">
              Selected Class
            </div>
            <div className="text-xs text-slate-700 truncate">
              {selectedClass
                ? classes.find((c) => c._id === selectedClass)?.name ||
                  selectedClass
                : "None"}
            </div>
          </div>
        </div>

        {attendance.length > 0 && (
          <button
            className="md:ml-auto bg-emerald-600 text-white px-4 py-2 rounded-lg text-sm shadow hover:bg-emerald-700 transition disabled:bg-slate-400"
            onClick={() => exportToCSV(attendance)}
          >
            Export CSV
          </button>
        )}
      </div>

      {/* Attendance table */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-100 p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-slate-700">
            Class Attendance Snapshot
          </h3>
          {loading && (
            <span className="text-emerald-600 text-xs animate-pulse">
              Loading latest data…
            </span>
          )}
        </div>

        {attendance.length === 0 ? (
          <div className="text-center text-slate-400 text-sm py-6">
            {selectedClass
              ? "No attendance records found for this class yet."
              : "Choose a class to view attendance."}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-center text-sm">
              <thead>
                <tr className="bg-slate-50 text-slate-600">
                  <th className="py-2">Student ID</th>
                  <th className="py-2">Present</th>
                  <th className="py-2">Absent</th>
                  <th className="py-2">Attendance %</th>
                </tr>
              </thead>
              <tbody>
                {attendance.map((s) => (
                  <tr key={s.student_id}>
                    <td className="py-2 border-b border-slate-50">
                      {s.student_id}
                    </td>
                    <td className="py-2 border-b border-slate-50">
                      {s.present_days}
                    </td>
                    <td className="py-2 border-b border-slate-50">
                      {s.absent_days}
                    </td>
                    <td className="py-2 border-b border-slate-50">
                      {(s.attendance_percent || 0).toFixed(2)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
