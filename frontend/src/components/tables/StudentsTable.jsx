import React, { useEffect, useState } from "react";
import axios from "axios";

function Students({ token, onLogout }) {
  const [students, setStudents] = useState([]);

  useEffect(() => {
    async function getStudents() {
      const jwt = token || localStorage.getItem("erpToken");
      if (!jwt) return;
      try {
        const res = await axios.get('http://localhost:5000/api/v1/students/', {
          headers: { Authorization: `Bearer ${jwt}` }
        });
        setStudents(res.data.data);
      } catch (err) {
        if (err.response && err.response.status === 401) {
          alert("Session expired, please login again...");
          localStorage.removeItem('erpToken');
          if (onLogout) onLogout(); // App.js me token reset karo
        }
      }
    }
    getStudents();
  }, [token, onLogout]);

  return (
    <div>
      <h2>All Students</h2>
      <ul>
        {students.map(s => (
          <li key={s._id}>{s.name} ({s.roll_no})</li>
        ))}
      </ul>
    </div>
  );
}

export default Students;
