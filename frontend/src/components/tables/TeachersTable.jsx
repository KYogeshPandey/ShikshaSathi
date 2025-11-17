import React, { useEffect, useState } from "react";
import axios from "axios";

function Teachers({ token, onLogout }) {
  const [teachers, setTeachers] = useState([]);

  useEffect(() => {
    async function getTeachers() {
      const jwt = token || localStorage.getItem("erpToken");
      if (!jwt) return;
      try {
        const res = await axios.get('http://localhost:5000/api/v1/teachers/', {
          headers: { Authorization: `Bearer ${jwt}` }
        });
        setTeachers(res.data.data);
      } catch (err) {
        if (err.response && err.response.status === 401) {
          alert("Session expired, login again!");
          localStorage.removeItem('erpToken');
          if (onLogout) onLogout();
        }
      }
    }
    getTeachers();
  }, [token, onLogout]);

  return (
    <div>
      <h2>All Teachers</h2>
      <ul>
        {teachers.map(t => (
          <li key={t._id}>{t.name} ({t.email})</li>
        ))}
      </ul>
    </div>
  );
}

export default Teachers;
