import React, { useEffect, useState } from "react";
import axios from "axios";

function Attendance({ token, onLogout }) {
  const [list, setList] = useState([]);
  const [form, setForm] = useState({ student_id: "", classroom_id: "", date: "", status: "present" });

  // Attendance GET
  useEffect(() => {
    async function getAttendance() {
      const jwt = token || localStorage.getItem("erpToken");
      if (!jwt) return;
      try {
        const res = await axios.get('http://localhost:5000/api/v1/attendance/', {
          headers: { Authorization: `Bearer ${jwt}` }
        });
        setList(res.data.data);
      } catch (err) {
        if (err.response && err.response.status === 401) {
          alert("Session expired, login again!");
          localStorage.removeItem('erpToken');
          if (onLogout) onLogout();
        }
      }
    }
    getAttendance();
  }, [token, onLogout]);

  // Attendance ADD
  const handleSubmit = async (e) => {
    e.preventDefault();
    const jwt = token || localStorage.getItem("erpToken");
    try {
      await axios.post('http://localhost:5000/api/v1/attendance/', form, {
        headers: { Authorization: `Bearer ${jwt}` }
      });
      alert("Attendance added");
      setForm({ student_id: "", classroom_id: "", date: "", status: "present" });
      // Refresh list
      const res = await axios.get('http://localhost:5000/api/v1/attendance/', {
        headers: { Authorization: `Bearer ${jwt}` }
      });
      setList(res.data.data);
    } catch (err) {
      alert("Failed to add! Check data and token.");
    }
  };

  return (
    <div>
      <h2>Attendance List</h2>
      <ul>
        {list.map(a => (
          <li key={a._id}>
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
          <option value="late">Late</option>
        </select>
        <button type="submit">Add</button>
      </form>
    </div>
  );
}

export default Attendance;
