import React, { useEffect, useState } from "react";
import { fetchAttendanceStats, saveBulkAttendance } from "../../api/api"; // Use api.js for future proofing

function Attendance({ token, onLogout }) {
  const [list, setList] = useState([]);
  const [form, setForm] = useState({ student_id: "", classroom_id: "", date: "", status: "present" });
  const [loading, setLoading] = useState(false);

  // GET attendance (uses api.js for consistency)
  async function getAttendance() {
    setLoading(true);
    try {
      const res = await fetchAttendanceStats(); // No params = fetch all
      setList(res.data.data || []);
    } catch (err) {
      if (err.response && err.response.status === 401 && onLogout) {
        alert("Session expired, login again!"); onLogout();
      }
    }
    setLoading(false);
  }

  useEffect(() => { getAttendance(); }, []);

  // ADD attendance
  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await saveBulkAttendance([{ ...form }]); // Use single-record as bulk
      alert("Attendance added");
      setForm({ student_id: "", classroom_id: "", date: "", status: "present" });
      getAttendance();
    } catch (err) {
      alert("Failed to add! Check data.");
    }
  };

  return (
    <div>
      <h2>Attendance List</h2>
      {loading && <div>Loading...</div>}
      <ul>
        {list.map(a => (
          <li key={a._id || [a.student_id, a.date].join("-")}>
            {a.date}: Student {a.student_id} - {a.status} (Class {a.classroom_id})
          </li>
        ))}
      </ul>
      <h3>Add Attendance</h3>
      <form onSubmit={handleSubmit}>
        <input placeholder="Student ID" value={form.student_id} onChange={e => setForm(f => ({ ...f, student_id: e.target.value }))} required />
        <input placeholder="Classroom ID" value={form.classroom_id} onChange={e => setForm(f => ({ ...f, classroom_id: e.target.value }))} required />
        <input placeholder="YYYY-MM-DD" value={form.date} onChange={e => setForm(f => ({ ...f, date: e.target.value }))} required />
        <select value={form.status} onChange={e => setForm(f => ({ ...f, status: e.target.value }))}>
          <option value="present">Present</option>
          <option value="absent">Absent</option>
        </select>
        <button type="submit">Add</button>
      </form>
    </div>
  );
}
export default Attendance;
