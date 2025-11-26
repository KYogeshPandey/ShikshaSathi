import React, { useEffect, useState } from "react";
import { fetchClassrooms, createClassroom, updateClassroom, deleteClassroom } from "../../api/api";

const emptyForm = {
  name: "",
  standard: "",
  section: "",
  label: "",
  teacher: "",
};

export default function ClassroomsPage() {
  const [classrooms, setClassrooms] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState(null);

  function resetMessages() {
    setError("");
    setSuccess("");
  }

  async function loadClassrooms() {
    resetMessages();
    setLoading(true);
    try {
      const res = await fetchClassrooms();
      setClassrooms(res.data.data || []);
    } catch (err) {
      setError("Could not load classrooms.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadClassrooms();
  }, []);

  function handleChange(e) {
    const { name, value } = e.target;
    setForm((f) => ({ ...f, [name]: value }));
  }

  function startCreate() {
    resetMessages();
    setEditingId(null);
    setForm(emptyForm);
  }

  function startEdit(cls) {
    resetMessages();
    setEditingId(cls._id);
    setForm({
      name: cls.name || "",
      standard: cls.standard || "",
      section: cls.section || "",
      label: cls.label || cls.name || "",
      teacher: cls.teacher || "",
    });
  }

  async function handleSubmit(e) {
    e.preventDefault();
    resetMessages();
    if (!form.name.trim()) {
      setError("Class name is required.");
      return;
    }

    setSaving(true);
    try {
      const payload = {
        name: form.name.trim(),
        standard: form.standard.trim() || undefined,
        section: form.section.trim() || undefined,
        label: form.label.trim() || form.name.trim(),
        teacher: form.teacher.trim() || undefined,
      };

      if (editingId) {
        await updateClassroom(editingId, payload);
        setSuccess("Classroom updated.");
      } else {
        await createClassroom(payload);
        setSuccess("Classroom created.");
      }

      setForm(emptyForm);
      setEditingId(null);
      await loadClassrooms();
    } catch (err) {
      setError(
        err.response?.data?.message || "Failed to save classroom. Check console."
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id) {
    resetMessages();
    if (!window.confirm("Delete this classroom?")) return;
    try {
      await deleteClassroom(id);
      setSuccess("Classroom deleted.");
      await loadClassrooms();
    } catch (err) {
      setError(
        err.response?.data?.message || "Failed to delete classroom. Check console."
      );
    }
  }

  return (
    <div className="bg-white/90 border border-slate-100 rounded-xl shadow-sm p-5">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800">
            Classes &amp; Sections
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Manage classrooms, standards and sections for your institute.
          </p>
        </div>
        <button
          type="button"
          onClick={startCreate}
          className="bg-emerald-600 text-white text-sm px-4 py-2 rounded-lg shadow hover:bg-emerald-700 transition"
        >
          {editingId ? "Create New Class" : "Add Class"}
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

      {/* Form */}
      <form
        onSubmit={handleSubmit}
        className="mb-5 grid grid-cols-1 md:grid-cols-5 gap-3 items-end bg-slate-50 border border-slate-200 rounded-lg p-3"
      >
        <div className="flex flex-col">
          <label className="text-[11px] text-slate-500 mb-1">Name *</label>
          <input
            name="name"
            value={form.name}
            onChange={handleChange}
            className="border border-slate-300 rounded-md px-2 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="10th A"
            required
          />
        </div>
        <div className="flex flex-col">
          <label className="text-[11px] text-slate-500 mb-1">Standard</label>
          <input
            name="standard"
            value={form.standard}
            onChange={handleChange}
            className="border border-slate-300 rounded-md px-2 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="10"
          />
        </div>
        <div className="flex flex-col">
          <label className="text-[11px] text-slate-500 mb-1">Section</label>
          <input
            name="section"
            value={form.section}
            onChange={handleChange}
            className="border border-slate-300 rounded-md px-2 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="A"
          />
        </div>
        <div className="flex flex-col">
          <label className="text-[11px] text-slate-500 mb-1">Label</label>
          <input
            name="label"
            value={form.label}
            onChange={handleChange}
            className="border border-slate-300 rounded-md px-2 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="10th A"
          />
        </div>
        <div className="flex flex-col">
          <label className="text-[11px] text-slate-500 mb-1">Class Teacher</label>
          <input
            name="teacher"
            value={form.teacher}
            onChange={handleChange}
            className="border border-slate-300 rounded-md px-2 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="teacher1"
          />
        </div>
        <div className="md:col-span-5 flex justify-end mt-1">
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
              ? "Update Class"
              : "Create Class"}
          </button>
        </div>
      </form>

      {/* List */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-center">
          <thead>
            <tr className="bg-slate-100 text-slate-600">
              <th className="py-2 px-2">Name</th>
              <th className="py-2 px-2">Standard</th>
              <th className="py-2 px-2">Section</th>
              <th className="py-2 px-2">Label</th>
              <th className="py-2 px-2">Teacher</th>
              <th className="py-2 px-2">Students</th>
              <th className="py-2 px-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {classrooms.map((cls) => (
              <tr key={cls._id || cls.name} className="border-b border-slate-100">
                <td className="py-2 px-2">{cls.name}</td>
                <td className="py-2 px-2">{cls.standard || "-"}</td>
                <td className="py-2 px-2">{cls.section || "-"}</td>
                <td className="py-2 px-2">{cls.label || "-"}</td>
                <td className="py-2 px-2">{cls.teacher || "-"}</td>
                <td className="py-2 px-2">
                  {Array.isArray(cls.student_ids) ? cls.student_ids.length : 0}
                </td>
                <td className="py-2 px-2 space-x-2">
                  <button
                    type="button"
                    onClick={() => startEdit(cls)}
                    className="text-xs text-indigo-600 hover:text-indigo-800 underline"
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(cls._id)}
                    className="text-xs text-red-600 hover:text-red-800 underline"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {!classrooms.length && !loading && (
              <tr>
                <td colSpan={7} className="py-4 text-slate-400">
                  No classrooms found. Create your first class above.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        {loading && (
          <div className="py-3 text-center text-slate-500 text-sm">
            Loading classrooms…
          </div>
        )}
      </div>
    </div>
  );
}
