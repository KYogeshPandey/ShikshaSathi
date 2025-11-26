import React, { useEffect, useState } from "react";
import { fetchClassrooms, createClassroom } from "../../api/api";

function Classrooms({ token, onLogout }) {
  const [list, setList] = useState([]);
  const [form, setForm] = useState({ name: "", code: "" });
  const [loading, setLoading] = useState(false);

  useEffect(() => { getClassrooms(); }, []);
  async function getClassrooms() {
    setLoading(true);
    try {
      const res = await fetchClassrooms();
      setList(res.data.data || []);
    } catch (err) {
      if (err.response && err.response.status === 401 && onLogout) {
        alert("Session expired, login again!"); onLogout();
      }
    }
    setLoading(false);
  }

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await createClassroom(form);
      alert("Classroom added");
      setForm({ name: "", code: "" });
      getClassrooms();
    } catch {
      alert("Failed to add! Check data.");
    }
  };

  return (
    <div>
      <h2>Classrooms List</h2>
      {loading && <div>Loading...</div>}
      <ul>
        {list.map(c => (
          <li key={c._id}>{c.code} — {c.name}</li>
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
