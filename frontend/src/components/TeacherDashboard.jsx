import React, { useEffect, useState } from "react";
import axios from "axios";

export default function TeacherDashboard({ token }) {
  const [classes, setClasses] = useState([]);
  const [selectedClass, setSelectedClass] = useState("");
  const [attendance, setAttendance] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // ✅ Get token from localStorage if not passed as prop
  const authToken = token || localStorage.getItem("token");

  // Load all classes
  useEffect(() => {
    if (!authToken) return;
    setError("");
    axios.get("/api/v1/classrooms/", { 
      headers: { Authorization: "Bearer " + authToken } 
    })
    .then(res => setClasses(res.data.data || []))
    .catch(() => setError("Could not fetch your classes!"));
  }, [authToken]);

  // Fetch attendance of selected class
  useEffect(() => {
    if (!selectedClass || !authToken) { setAttendance([]); return; }
    setLoading(true); 
    setError("");
    axios.get(`/api/v1/attendance/stats?classroom_id=${selectedClass}`, { 
      headers: { Authorization: "Bearer " + authToken }
    })
    .then(res => setAttendance(res.data.data || []))
    .catch(() => setError("Could not fetch attendance for this class!"))
    .finally(() => setLoading(false));
  }, [selectedClass, authToken]);

  // CSV Export
  function exportToCSV(data, fileName = "attendance.csv") {
    if (!data?.length) return;
    const keys = Object.keys(data[0]);
    const rows = [
      keys.join(","),
      ...data.map(row => keys.map(k => JSON.stringify(row[k] ?? "")).join(","))
    ];
    const blob = new Blob([rows.join("\n")], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = fileName;
    a.click();
  }

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <h2 className="text-2xl font-bold mb-4 text-blue-800">Teacher Dashboard</h2>

      {error && <div className="bg-red-100 text-red-800 px-4 py-2 rounded mb-3">{error}</div>}

      {/* Class Selector */}
      <div className="mb-6 flex gap-4 items-center">
        <label htmlFor="selectClass" className="font-semibold">Select Class:</label>
        <select id="selectClass" className="border rounded px-3 py-1"
          value={selectedClass}
          onChange={e => setSelectedClass(e.target.value)}
        >
          <option value="">-- Select --</option>
          {classes.map(cls => <option key={cls._id} value={cls._id}>{cls.name}</option>)}
        </select>
        {attendance.length > 0 && (
          <button className="ml-4 bg-blue-600 text-white px-4 py-1 rounded" onClick={() => exportToCSV(attendance)}>
            Export Attendance CSV
          </button>
        )}
      </div>

      {/* Attendance Table */}
      {loading && <div className="text-blue-700 animate-pulse">Loading...</div>}
      {attendance.length > 0 && (
        <div className="bg-white p-6 rounded shadow">
          <table className="w-full text-center">
            <thead>
              <tr className="bg-gray-50">
                <th className="py-2">Student ID</th>
                <th className="py-2">Present</th>
                <th className="py-2">Absent</th>
                <th className="py-2">Attendance %</th>
              </tr>
            </thead>
            <tbody>
              {attendance.map(s => (
                <tr key={s.student_id}>
                  <td className="py-2">{s.student_id}</td>
                  <td>{s.present_days}</td>
                  <td>{s.absent_days}</td>
                  <td>{((s.attendance_percent || 0).toFixed(2))}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Mark Attendance Button (future stub) */}
      <div className="mt-8 flex flex-col gap-2 items-start">
        <button className="bg-green-700 text-white px-4 py-2 rounded hover:bg-green-800" disabled>
          Mark/Approve Today's Attendance (demo)
        </button>
        <span className="text-xs text-gray-400">*You can enable attendance marking integration here.</span>
      </div>
    </div>
  );
}
