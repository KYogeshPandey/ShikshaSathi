import React, { useEffect, useState } from "react";
import axios from "axios";

export default function StudentDashboard({ token, userName }) {
  const [profile, setProfile] = useState({});
  const [attendance, setAttendance] = useState([]);
  const [schedule, setSchedule] = useState([]);
  const [notices, setNotices] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // ✅ Get token from localStorage if not passed as prop
  const authToken = token || localStorage.getItem("token");

  // Profile fetch
  useEffect(() => {
    if (!authToken) return;
    setError("");
    axios.get("/api/v1/students/me", { 
      headers: { Authorization: "Bearer " + authToken } 
    })
    .then(res => setProfile(res.data.data || {}))
    .catch(() => setError("Student profile not found"));
  }, [authToken]);

  // Attendance summary fetch
  useEffect(() => {
    if (!authToken) return;
    setLoading(true);
    axios.get("/api/v1/attendance/mystats", { 
      headers: { Authorization: "Bearer " + authToken } 
    })
    .then(res => setAttendance(res.data.data || []))
    .catch(() => setError("Attendance data error"))
    .finally(() => setLoading(false));
  }, [authToken]);

  // Schedule & notices (demo)
  useEffect(() => {
    setSchedule([
      { day: "Mon", subject: "Maths", time: "9:00-10:00" },
      { day: "Mon", subject: "Science", time: "10:00-11:00" },
      { day: "Tue", subject: "English", time: "9:00-10:00" }
    ]);
    setNotices([
      { title: "Sports Day", message: "Prepare for sports events on Dec 5." },
      { title: "Exam Timetable", message: "Final exams from Dec 10-22." }
    ]);
  }, []);

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <h2 className="text-2xl font-bold mb-6 text-green-800">
        Welcome {profile.name || userName || "Student"} 🎒
      </h2>

      {error && <div className="bg-red-100 text-red-800 px-4 py-2 rounded mb-2">{error}</div>}

      {/* Student Info */}
      <div className="bg-white rounded shadow p-5 mb-5">
        <div className="font-semibold mb-2">Student Details</div>
        <ul>
          <li><b>Name:</b> {profile.name || userName || "--"}</li>
          <li><b>Class:</b> {profile.className || "--"}</li>
          <li><b>Roll Number:</b> {profile.rollNumber || "--"}</li>
          <li><b>Email:</b> {profile.email || "--"}</li>
        </ul>
      </div>

      {/* Attendances */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
        <div className="bg-white rounded shadow p-4">
          <div className="font-semibold mb-2">Attendance Summary</div>
          {loading
            ? <div className="text-blue-600 animate-pulse">Loading...</div>
            : (
              <table className="w-full text-center">
                <thead>
                  <tr className="bg-gray-50">
                    <th>Date</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {attendance.map((row, idx) => (
                    <tr key={idx}>
                      <td>{row.date}</td>
                      <td>
                        <span className={row.status === "present" ? "text-green-600" : "text-red-500"}>
                          {row.status.charAt(0).toUpperCase() + row.status.slice(1)}
                        </span>
                      </td>
                    </tr>
                  ))}
                  {attendance.length === 0 &&
                    <tr><td colSpan={2} className="text-gray-400 text-center">No records!</td></tr>}
                </tbody>
              </table>
            )}
        </div>
        {/* Timetable */}
        <div className="bg-white rounded shadow p-4">
          <div className="font-semibold mb-2">Class Schedule</div>
          <table className="w-full text-center">
            <thead>
              <tr className="bg-gray-50"><th>Day</th><th>Subject</th><th>Time</th></tr>
            </thead>
            <tbody>
              {schedule.map((row, idx) =>
                <tr key={idx}><td>{row.day}</td><td>{row.subject}</td><td>{row.time}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Monthly attendance heatmap/summary */}
      <div className="bg-white rounded shadow p-5 mb-5">
        <div className="font-semibold mb-2">Monthly Attendance Graph</div>
        <div className="italic text-gray-400 text-sm py-3">
          (COMING SOON: Calendar heatmap/analytics)
        </div>
      </div>

      {/* Notices */}
      <div className="bg-white rounded shadow p-4 mb-5">
        <div className="font-semibold mb-2">Important Notices</div>
        <ul className="list-disc ml-6 text-gray-600">
          {notices.map((item, idx) => (
            <li key={idx}><b>{item.title}:</b> {item.message}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
