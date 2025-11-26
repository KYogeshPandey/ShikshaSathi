import React, { useEffect, useState } from "react";
import { fetchTeachers } from "../../api/api";

function Teachers({ token, onLogout }) {
  const [teachers, setTeachers] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    async function getTeachers() {
      setLoading(true);
      try {
        const res = await fetchTeachers();
        setTeachers(res.data.data || []);
      } catch (err) {
        if (err.response && err.response.status === 401 && onLogout) {
          alert("Session expired, login again!");
          onLogout();
        }
      }
      setLoading(false);
    }
    getTeachers();
  }, [onLogout]);

  return (
    <div>
      <h2>All Teachers</h2>
      {loading && <div>Loading...</div>}
      <ul>
        {teachers.map(t => (
          <li key={t._id}>{t.name} ({t.email})</li>
        ))}
      </ul>
    </div>
  );
}
export default Teachers;
