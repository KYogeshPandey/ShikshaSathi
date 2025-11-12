import React, { useEffect, useState } from "react";
import axios from "axios";

function Classrooms({ token, onLogout }) {
  const [list, setList] = useState([]);
  const [form, setForm] = useState({ name: "", code: "" });

  // GET classrooms
  useEffect(() => {
    async function getClassrooms() {
      const jwt = token || localStorage.getItem("erpToken");
      if (!jwt) return;
      try {
        const res = await axios.get('http://localhost:5000/api/v1/classrooms/', {
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
    getClassrooms();
  }, [token, onLogout]);

  // ADD classroom
  const handleSubmit = async (e) => {
    e.preventDefault();
    const jwt = token || localStorage.getItem("erpToken");
    try {
      await axios.post('http://localhost:5000/api/v1/classrooms/', form, {
        headers: { Authorization: `Bearer ${jwt}` }
      });
      alert("Classroom added");
      setForm({ name: "", code: "" });
      // Refresh list
      const res = await axios.get('http://localhost:5000/api/v1/classrooms/', {
        headers: { Authorization: `Bearer ${jwt}` }
      });
      setList(res.data.data);
    } catch {
      alert("Failed to add! Check data and JWT.");
    }
  };

  return (
    <div>
      <h2>Classrooms List</h2>
      <ul>
        {list.map(c => (
          <li key={c._id}>
            {c.code} — {c.name}
          </li>
        ))}
      </ul>
      <h3>Add Classroom</h3>
      <form onSubmit={handleSubmit}>
        <input placeholder="Classroom Name" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} required />
        <input placeholder="Classroom Code" value={form.code} onChange={e => setForm(f => ({ ...f, code: e.target.value }))} required />
        <button type="submit">Add</button>
      </form>
    </div>
  );
}

export default Classrooms;
