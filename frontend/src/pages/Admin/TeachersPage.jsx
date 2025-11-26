import React, { useEffect, useMemo, useState } from "react";
import {
  fetchTeachers,
  createTeacher,
  updateTeacher,
  deleteTeacher,
  fetchClassrooms,
  assignTeacherClassroom,
  removeTeacherClassroom,
} from "../../api/api";

const emptyForm = {
  name: "",
  email: "",
  phone: "",
  role: "teacher",
};

export default function TeachersPage() {
  const [teachers, setTeachers] = useState([]);
  const [classrooms, setClassrooms] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState(null);
  const [search, setSearch] = useState("");
  const [filterClassroomId, setFilterClassroomId] = useState("");

  function resetMessages() {
    setError("");
    setSuccess("");
  }

  async function loadBaseData() {
    resetMessages();
    setLoading(true);
    try {
      const [tRes, cRes] = await Promise.all([
        fetchTeachers(),
        fetchClassrooms(),
      ]);
      setTeachers(tRes.data.data || tRes.data || []);
      setClassrooms(cRes.data.data || []);
    } catch (err) {
      setError("Could not load teachers or classes.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadBaseData();
  }, []);

  function handleFormChange(e) {
    const { name, value } = e.target;
    setForm((f) => ({ ...f, [name]: value }));
  }

  function startCreate() {
    resetMessages();
    setEditingId(null);
    setForm(emptyForm);
  }

  function startEdit(t) {
    resetMessages();
    setEditingId(t._id);
    setForm({
      name: t.name || "",
      email: t.email || "",
      phone: t.phone || "",
      role: t.role || "teacher",
    });
  }

  async function handleSubmit(e) {
    e.preventDefault();
    resetMessages();

    if (!form.name.trim()) {
      setError("Teacher name is required.");
      return;
    }

    setSaving(true);
    try {
      const payload = {
        name: form.name.trim(),
        email: form.email?.trim() || undefined,
        phone: form.phone?.trim() || undefined,
        role: form.role || "teacher",
      };
      if (editingId) {
        await updateTeacher(editingId, payload);
        setSuccess("Teacher updated.");
      } else {
        await createTeacher(payload);
        setSuccess("Teacher created.");
      }
      setForm(emptyForm);
      setEditingId(null);
      await loadBaseData();
    } catch (err) {
      setError(
        err.response?.data?.message || err.message || "Failed to save teacher."
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id) {
    resetMessages();
    if (!window.confirm("Delete / deactivate this teacher?")) return;
    try {
      await deleteTeacher(id);
      setSuccess("Teacher deleted.");
      await loadBaseData();
    } catch (err) {
      setError(
        err.response?.data?.message || err.message || "Failed to delete teacher."
      );
    }
  }

  const classOptions = useMemo(
    () =>
      classrooms.map((c) => ({
        id: c._id || c.name,
        label: c.label || c.name,
      })),
    [classrooms]
  );

  const filteredTeachers = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (teachers || []).filter((t) => {
      if (filterClassroomId) {
        const assigned = t.assigned_classrooms || [];
        if (!assigned.includes(filterClassroomId)) return false;
      }
      if (!q) return true;
      const name = String(t.name || "").toLowerCase();
      const email = String(t.email || "").toLowerCase();
      const phone = String(t.phone || "").toLowerCase();
      return (
        name.includes(q) ||
        email.includes(q) ||
        phone.includes(q)
      );
    });
  }, [teachers, search, filterClassroomId]);

  async function handleAssignClassroom(teacherId, classroomId) {
    resetMessages();
    try {
      await assignTeacherClassroom(teacherId, classroomId);
      setSuccess("Classroom assigned to teacher.");
      await loadBaseData();
    } catch (err) {
      setError(
        err.response?.data?.message || err.message || "Failed to assign classroom."
      );
    }
  }

  async function handleRemoveClassroom(teacherId, classroomId) {
    resetMessages();
    try {
      await removeTeacherClassroom(teacherId, classroomId);
      setSuccess("Classroom removed from teacher.");
      await loadBaseData();
    } catch (err) {
      setError(
        err.response?.data?.message || err.message || "Failed to remove classroom."
      );
    }
  }

  return (
    <div className="bg-white/90 border border-slate-100 rounded-xl shadow-sm p-5">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800">Teachers</h2>
          <p className="text-xs text-slate-500 mt-1">
            Manage teacher profiles and assign them to classes.
          </p>
        </div>
        <button
          type="button"
          onClick={startCreate}
          className="bg-emerald-600 text-white text-sm px-4 py-2 rounded-lg shadow hover:bg-emerald-700 transition"
        >
          {editingId ? "Create New Teacher" : "Add Teacher"}
        </button>
      </div>

      {error && (
        <div className="mb-3 text-xs md:text-sm bg-red-50 border border-red-200 text-red-700 px-3 py-2 rounded">
          {error}
        </div>
      )}
      {success && (
        <div className="mb-3 text-xs md:text-sm bg-emerald-50 border border-emerald-200 text-emerald-700 px-3 py-2 rounded">
          {success}
        </div>
      )}

      {/* Filters */}
      <div className="mb-4 flex flex-col lg:flex-row gap-3 items-start lg:items-end">
        <div className="flex gap-2 items-center">
          <label className="text-[11px] text-slate-500">Filter by class</label>
          <select
            value={filterClassroomId}
            onChange={(e) => setFilterClassroomId(e.target.value)}
            className="border border-slate-300 rounded-md px-2 py-1.5 text-xs bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="">All</option>
            {classOptions.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex-1 flex gap-2">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name, email, phone"
            className="flex-1 border border-slate-300 rounded-md px-2 py-1.5 text-xs bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
      </div>

      {/* Form */}
      <form
        onSubmit={handleSubmit}
        className="mb-5 grid grid-cols-1 md:grid-cols-4 gap-3 items-end bg-slate-50 border border-slate-200 rounded-lg p-3"
      >
        <div className="flex flex-col">
          <label className="text-[11px] text-slate-500 mb-1">Name *</label>
          <input
            name="name"
            value={form.name}
            onChange={handleFormChange}
            className="border border-slate-300 rounded-md px-2 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="Teacher Name"
            required
          />
        </div>

        <div className="flex flex-col">
          <label className="text-[11px] text-slate-500 mb-1">Email</label>
          <input
            name="email"
            value={form.email}
            onChange={handleFormChange}
            className="border border-slate-300 rounded-md px-2 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="teacher@example.com"
          />
        </div>

        <div className="flex flex-col">
          <label className="text-[11px] text-slate-500 mb-1">Phone</label>
          <input
            name="phone"
            value={form.phone}
            onChange={handleFormChange}
            className="border border-slate-300 rounded-md px-2 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="9876543210"
          />
        </div>

        <div className="flex flex-col">
          <label className="text-[11px] text-slate-500 mb-1">Role</label>
          <select
            name="role"
            value={form.role}
            onChange={handleFormChange}
            className="border border-slate-300 rounded-md px-2 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="teacher">Teacher</option>
            <option value="hod">HOD</option>
            <option value="coordinator">Coordinator</option>
          </select>
        </div>

        <div className="md:col-span-4 flex justify-end mt-1">
          <button
            type="submit"
            disabled={saving}
            className="bg-indigo-600 text-white text-sm px-4 py-2 rounded-lg shadow hover:bg-indigo-700 transition disabled:bg-slate-400"
          >
            {saving
              ? editingId
                ? "Updating..."
                : "Creating..."
              : editingId
              ? "Update Teacher"
              : "Create Teacher"}
          </button>
        </div>
      </form>

      {/* Teachers list */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead>
            <tr className="bg-slate-100 text-slate-600">
              <th className="py-2 px-2">Name</th>
              <th className="py-2 px-2">Email</th>
              <th className="py-2 px-2">Phone</th>
              <th className="py-2 px-2">Role</th>
              <th className="py-2 px-2">Assigned Classes</th>
              <th className="py-2 px-2 text-center">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredTeachers.map((t) => {
              const assigned = t.assigned_classrooms || [];
              return (
                <tr
                  key={t._id}
                  className="border-b border-slate-100 hover:bg-slate-50"
                >
                  <td className="py-2 px-2">{t.name}</td>
                  <td className="py-2 px-2">{t.email || "-"}</td>
                  <td className="py-2 px-2">{t.phone || "-"}</td>
                  <td className="py-2 px-2">{t.role || "teacher"}</td>
                  <td className="py-2 px-2">
                    <div className="flex flex-wrap gap-1">
                      {assigned.length === 0 && (
                        <span className="text-[11px] text-slate-400">
                          No classes
                        </span>
                      )}
                      {assigned.map((cid) => {
                        const cls = classOptions.find((c) => c.id === cid);
                        const label = cls?.label || cid;
                        return (
                          <button
                            key={cid}
                            type="button"
                            onClick={() => handleRemoveClassroom(t._id, cid)}
                            className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200 hover:bg-red-50 hover:text-red-600 hover:border-red-300"
                            title="Click to unassign"
                          >
                            {label} ✕
                          </button>
                        );
                      })}
                    </div>
                    {/* Quick assign dropdown */}
                    {classOptions.length > 0 && (
                      <div className="mt-1">
                        <select
                          className="text-[11px] border border-slate-200 rounded-md px-1.5 py-0.5 bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
                          defaultValue=""
                          onChange={(e) => {
                            const cid = e.target.value;
                            if (!cid) return;
                            handleAssignClassroom(t._id, cid);
                            e.target.value = "";
                          }}
                        >
                          <option value="">Assign to class…</option>
                          {classOptions
                            .filter((c) => !assigned.includes(c.id))
                            .map((c) => (
                              <option key={c.id} value={c.id}>
                                {c.label}
                              </option>
                            ))}
                        </select>
                      </div>
                    )}
                  </td>
                  <td className="py-2 px-2 text-center space-x-2">
                    <button
                      type="button"
                      onClick={() => startEdit(t)}
                      className="text-xs text-indigo-600 hover:text-indigo-800 underline"
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDelete(t._id)}
                      className="text-xs text-red-600 hover:text-red-800 underline"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              );
            })}
            {!filteredTeachers.length && !loading && (
              <tr>
                <td colSpan={6} className="py-4 text-slate-400 text-center">
                  No teachers found. Create your first teacher above.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        {loading && (
          <div className="py-3 text-center text-slate-500 text-sm">
            Loading teachers…
          </div>
        )}
      </div>
    </div>
  );
}
