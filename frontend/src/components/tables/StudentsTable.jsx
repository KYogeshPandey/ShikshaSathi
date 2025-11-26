import React, { useEffect, useState } from "react";
import { fetchStudents } from "../../api/api";

function Students({ token, onLogout }) {
  const [students, setStudents] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    async function getStudents() {
      setLoading(true);
      try {
        const res = await fetchStudents();
        setStudents(res.data.data || []);
      } catch (err) {
        if (err.response && err.response.status === 401 && onLogout) {
          alert("Session expired, please login again...");
          onLogout();
        }
      }
      setLoading(false);
    }
    getStudents();
  }, [onLogout]);

  return (
    <div>
      <h2>All Students</h2>
      {loading && <div>Loading...</div>}
      <ul>
        {students.map(s => (
          <li key={s._id}>{s.name} ({s.roll_no})</li>
        ))}
      </ul>
    </div>
  );
}
export default Students;
