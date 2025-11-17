// frontend/src/pages/Student/StudentDashboard.jsx
import React, { useEffect, useState } from "react";
import { api } from "../../api/api";

export default function StudentDashboard({ token, userName }) {
  const [profile, setProfile] = useState({});
  const [attendance, setAttendance] = useState([]);
  const [schedule, setSchedule] = useState([]);
  const [notices, setNotices] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Profile fetch
  useEffect(() => {
    setError("");
    api
      .get("/students/me")
      .then((res) => setProfile(res.data.data || {}))
      .catch(() => setError("Student profile not found"));
  }, []);

  // Attendance summary fetch
  useEffect(() => {
    setLoading(true);
    api
      .get("/attendance/mystats")
      .then((res) => setAttendance(res.data.data || []))
      .catch(() => setError("Attendance data error"))
      .finally(() => setLoading(false));
  }, []);

  // Schedule & notices (demo static)
  useEffect(() => {
    setSchedule([
      { day: "Mon", subject: "Maths", time: "9:00-10:00" },
      { day: "Mon", subject: "Science", time: "10:00-11:00" },
      { day: "Tue", subject: "English", time: "9:00-10:00" },
    ]);
    setNotices([
      {
        title: "Sports Day",
        message: "Prepare for sports events on Dec 5.",
      },
      {
        title: "Exam Timetable",
        message: "Final exams from Dec 10-22.",
      },
    ]);
  }, []);

  const presentCount = attendance.filter((a) => a.status === "present").length;
  const absentCount = attendance.filter((a) => a.status === "absent").length;
  const totalDays = attendance.length;
  const presentPercent =
    totalDays === 0 ? 0 : (presentCount / totalDays) * 100;

  return (
    <div className="min-h-screen bg-gradient-to-br from-green-50 via-emerald-50 to-slate-50 p-6">
      {/* Header */}
      <div className="mb-6">
        <h2 className="text-3xl font-extrabold mb-1 text-emerald-800 tracking-tight">
          Hi {profile.name || userName || "Student"} 👋
        </h2>
        <p className="text-sm text-emerald-700">
          Here&apos;s your attendance snapshot, timetable and latest notices.
        </p>
      </div>

      {error && (
        <div className="bg-red-50 text-red-800 px-4 py-2 rounded mb-4 text-sm border border-red-200">
          {error}
        </div>
      )}

      {/* Top summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-white rounded-xl shadow-sm p-4 border border-emerald-100">
          <div className="text-[11px] text-slate-500 uppercase tracking-wide mb-1">
            Class
          </div>
          <div className="text-xl font-bold text-emerald-800">
            {profile.className || "--"}
          </div>
        </div>
        <div className="bg-white rounded-xl shadow-sm p-4 border border-emerald-100">
          <div className="text-[11px] text-slate-500 uppercase tracking-wide mb-1">
            Roll No
          </div>
          <div className="text-xl font-bold text-emerald-800">
            {profile.rollNumber || profile.roll_no || "--"}
          </div>
        </div>
        <div className="bg-emerald-50 rounded-xl shadow-sm p-4 border border-emerald-200">
          <div className="text-[11px] text-emerald-700 uppercase tracking-wide mb-1">
            Present Days
          </div>
          <div className="text-xl font-bold text-emerald-900">{presentCount}</div>
        </div>
        <div className="bg-red-50 rounded-xl shadow-sm p-4 border border-red-100">
          <div className="text-[11px] text-red-700 uppercase tracking-wide mb-1">
            Absent Days
          </div>
          <div className="text-xl font-bold text-red-500">{absentCount}</div>
        </div>
      </div>

      {/* Attendance + schedule */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        {/* Attendance table */}
        <div className="bg-white rounded-xl shadow-sm p-4 border border-slate-100">
          <div className="flex items-center justify-between mb-2">
            <div className="font-semibold text-slate-700">
              Recent Attendance
            </div>
            <div className="text-xs text-emerald-700 font-semibold">
              Overall: {presentPercent.toFixed(1)}%
            </div>
          </div>
          {loading ? (
            <div className="text-emerald-600 animate-pulse text-sm">
              Loading...
            </div>
          ) : (
            <div className="max-h-64 overflow-y-auto">
              <table className="w-full text-center text-sm">
                <thead>
                  <tr className="bg-slate-50">
                    <th className="py-1">Date</th>
                    <th className="py-1">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {attendance.map((row, idx) => (
                    <tr key={idx} className="border-b border-slate-50">
                      <td className="py-1">{row.date}</td>
                      <td className="py-1">
                        <span
                          className={
                            row.status === "present"
                              ? "text-emerald-600 font-semibold"
                              : "text-red-500 font-semibold"
                          }
                        >
                          {row.status
                            ? row.status.charAt(0).toUpperCase() +
                              row.status.slice(1)
                            : "--"}
                        </span>
                      </td>
                    </tr>
                  ))}
                  {attendance.length === 0 && (
                    <tr>
                      <td
                        colSpan={2}
                        className="text-slate-400 text-center py-3 text-sm"
                      >
                        No records!
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Timetable */}
        <div className="bg-white rounded-xl shadow-sm p-4 border border-slate-100">
          <div className="font-semibold mb-2 text-slate-700">
            Today&apos;s Timetable
          </div>
          <table className="w-full text-center text-sm">
            <thead>
              <tr className="bg-slate-50">
                <th className="py-1">Day</th>
                <th className="py-1">Subject</th>
                <th className="py-1">Time</th>
              </tr>
            </thead>
            <tbody>
              {schedule.map((row, idx) => (
                <tr key={idx} className="border-b border-slate-50">
                  <td className="py-1">{row.day}</td>
                  <td className="py-1">{row.subject}</td>
                  <td className="py-1">{row.time}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Monthly analytics placeholder */}
      <div className="bg-white rounded-xl shadow-sm p-4 mb-6 border border-slate-100">
        <div className="font-semibold mb-2 text-slate-700">
          Monthly Attendance Graph
        </div>
        <div className="italic text-slate-400 text-sm py-3">
          (Coming soon: calendar heatmap for your monthly attendance.)
        </div>
      </div>

      {/* Notices */}
      <div className="bg-white rounded-xl shadow-sm p-4 border border-slate-100">
        <div className="font-semibold mb-2 text-slate-700">
          Important Notices
        </div>
        <ul className="space-y-2 text-sm">
          {notices.map((item, idx) => (
            <li
              key={idx}
              className="border border-slate-100 rounded-lg px-3 py-2 bg-slate-50"
            >
              <div className="font-semibold text-slate-800 text-sm">
                {item.title}
              </div>
              <div className="text-slate-600 text-xs">{item.message}</div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
