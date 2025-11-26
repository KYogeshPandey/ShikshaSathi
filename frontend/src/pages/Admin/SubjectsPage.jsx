// frontend/src/pages/Admin/SubjectsPage.jsx
import React, { useEffect, useState } from "react";
import {
  fetchSubjects,
  createSubject,
  updateSubject,
  deleteSubject,
  fetchClassrooms,
} from "../../api/api";

const emptyForm = {
  name: "",
  code: "",
  standard: "",
  description: "",
  subject_type: "core",
  is_elective: false,
  classroom_ids: [],
};

export default function SubjectsPage() {
  const [subjects, setSubjects] = useState([]);
  const [classrooms, setClassrooms] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState(null);

  const [search, setSearch] = useState("");
  const [filterStandard, setFilterStandard] = useState("");
  const [filterClassroomId, setFilterClassroomId] = useState("");

  function resetMessages() {
    setError("");
    setSuccess("");
  }

  async function loadBaseData() {
    resetMessages();
    setLoading(true);
    try {
      const [subRes, clsRes] = await Promise.all([
        fetchSubjects({
          standard: filterStandard || undefined,
          classroom_id: filterClassroomId || undefined,
        }),
        fetchClassrooms(),
      ]);
      setSubjects(subRes.data.data || []);
      setClassrooms(clsRes.data.data || []);
    } catch (err) {
      setError("Could not fetch subjects or classes");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadBaseData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterStandard, filterClassroomId]);

  function handleFormChange(e) {
    const { name, value, type, checked } = e.target;
    if (type === "checkbox") {
      setForm((f) => ({ ...f, [name]: checked }));
    } else {
      setForm((f) => ({ ...f, [name]: value }));
    }
  }

  function toggleClassroomAssignment(classroomId) {
    setForm((f) => {
      let arr = Array.isArray(f.classroom_ids) ? [...f.classroom_ids] : [];
      if (arr.includes(classroomId)) arr = arr.filter((id) => id !== classroomId);
      else arr.push(classroomId);
      return { ...f, classroom_ids: arr };
    });
  }

  function startCreate() {
    resetMessages();
    setEditingId(null);
    setForm(emptyForm);
  }

  function startEdit(sub) {
    resetMessages();
    setEditingId(sub._id);
    setForm({
      name: sub.name || "",
      code: sub.code || "",
      standard: sub.standard || "",
      description: sub.description || "",
      subject_type: sub.subject_type || "core",
      is_elective: !!sub.is_elective,
      classroom_ids: Array.isArray(sub.classroom_ids) ? sub.classroom_ids : [],
    });
  }

  async function handleSubmit(e) {
    e.preventDefault();
    resetMessages();
    if (!form.name.trim()) {
      setError("Subject name is required.");
      return;
    }
    setSaving(true);

    try {
      const payload = {
        ...form,
        name: form.name.trim(),
        code: form.code.trim() || undefined,
        standard: form.standard.trim() || undefined,
        description: form.description.trim() || undefined,
        classroom_ids: form.classroom_ids || [],
        subject_type: form.subject_type || "core",
        is_elective: !!form.is_elective,
      };

      if (editingId) {
        await updateSubject(editingId, payload);
        setSuccess("Subject updated.");
      } else {
        await createSubject(payload);
        setSuccess("Subject created.");
      }

      setForm(emptyForm);
      setEditingId(null);
      await loadBaseData();
    } catch (err) {
      setError(
        err.response?.data?.message || "Failed to save subject. Check console."
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id) {
    resetMessages();
    if (!window.confirm("Delete this subject?")) return;
    try {
      await deleteSubject(id);
      setSuccess("Subject deleted.");
      await loadBaseData();
    } catch (err) {
      setError(
        err.response?.data?.message || "Failed to delete subject. Check console."
      );
    }
  }

  const filteredSubjects = subjects.filter((s) => {
    const searchQuery = search.trim().toLowerCase();
    if (!searchQuery) return true;
    return (
      (s.name || "").toLowerCase().includes(searchQuery) ||
      (s.code || "").toLowerCase().includes(searchQuery) ||
      (s.standard || "").toLowerCase().includes(searchQuery)
    );
  });

  const standardsList = Array.from(new Set(subjects.map((s) => s.standard).filter(Boolean)));

  return (
    <div className="bg-white/90 border border-slate-100 rounded-xl shadow-sm p-5">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800">Subjects</h2>
          <p className="text-xs text-slate-500 mt-1">
            Manage subject masters, mapping, and elective/core configuration.
          </p>
        </div>
        <button
          type="button"
          onClick={startCreate}
          className="bg-emerald-600 text-white text-sm px-4 py-2 rounded-lg shadow hover:bg-emerald-700 transition"
        >
          {editingId ? "Create New Subject" : "Add Subject"}
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
      <div className="mb-4 flex flex-col md:flex-row gap-3 items-start md:items-end">
        <div className="flex gap-2 items-center">
          <label className="text-[11px] text-slate-500">Standard</label>
          <select
            value={filterStandard}
            onChange={(e) => setFilterStandard(e.target.value)}
            className="border border-slate-300 rounded-md px-2 py-1.5 text-xs bg-white"
          >
            <option value="">All</option>
            {standardsList.map((std) => (
              <option key={std} value={std}>
                {std}
              </option>
            ))}
          </select>
        </div>
        <div className="flex gap-2 items-center">
          <label className="text-[11px] text-slate-500">Filter by Class</label>
          <select
            value={filterClassroomId}
            onChange={(e) => setFilterClassroomId(e.target.value)}
            className="border border-slate-300 rounded-md px-2 py-1.5 text-xs bg-white"
          >
            <option value="">All</option>
            {classrooms.map((cls) => (
              <option key={cls._id || cls.name} value={cls._id || cls.name}>
                {cls.label || cls.name}
              </option>
            ))}
          </select>
        </div>
        <div className="flex-1 flex gap-2">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name/code/standard"
            className="flex-1 border border-slate-300 rounded-md px-2 py-1.5 text-xs bg-white"
          />
        </div>
      </div>

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
            onChange={handleFormChange}
            className="border border-slate-300 rounded-md px-2 py-1.5 text-sm bg-white"
            required
            placeholder="Subject Name"
          />
        </div>
        <div className="flex flex-col">
          <label className="text-[11px] text-slate-500 mb-1">Code</label>
          <input
            name="code"
            value={form.code}
            onChange={handleFormChange}
            className="border border-slate-300 rounded-md px-2 py-1.5 text-sm bg-white"
            placeholder="MATH_X"
          />
        </div>
        <div className="flex flex-col">
          <label className="text-[11px] text-slate-500 mb-1">Standard/Class</label>
          <input
            name="standard"
            value={form.standard}
            onChange={handleFormChange}
            className="border border-slate-300 rounded-md px-2 py-1.5 text-sm bg-white"
            placeholder="10"
          />
        </div>
        <div className="flex flex-col">
          <label className="text-[11px] text-slate-500 mb-1">Subject Type</label>
          <select
            name="subject_type"
            value={form.subject_type}
            onChange={handleFormChange}
            className="border border-slate-300 rounded-md px-2 py-1.5 text-sm bg-white"
          >
            <option value="core">Core</option>
            <option value="elective">Elective</option>
          </select>
        </div>
        <div className="flex flex-col">
          <label className="text-[11px] text-slate-500 mb-1">Elective?</label>
          <input
            type="checkbox"
            name="is_elective"
            checked={form.is_elective}
            onChange={handleFormChange}
            className="mr-2"
          />
        </div>
        <div className="md:col-span-5 flex flex-col mt-1">
          <label className="text-[11px] text-slate-500 mb-1">Description</label>
          <textarea
            name="description"
            value={form.description}
            onChange={handleFormChange}
            rows={1}
            className="border border-slate-300 rounded-md px-2 py-1.5 text-sm bg-white"
            placeholder="Subject description"
          />
        </div>
        <div className="md:col-span-5 flex flex-col">
          <label className="text-[11px] text-slate-500 mb-1">Classes mapped</label>
          <div className="flex flex-wrap gap-2">
            {classrooms.map((cls) => (
              <label key={cls._id || cls.name} className="flex items-center text-xs">
                <input
                  type="checkbox"
                  checked={
                    (form.classroom_ids || []).includes(cls._id) ||
                    (form.classroom_ids || []).includes(cls.name)
                  }
                  onChange={() => toggleClassroomAssignment(cls._id || cls.name)}
                  className="mr-1"
                />
                {cls.label || cls.name}
              </label>
            ))}
          </div>
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
              ? "Update Subject"
              : "Create Subject"}
          </button>
        </div>
      </form>

      {/* Subjects Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs md:text-sm text-center">
          <thead>
            <tr className="bg-slate-100 text-slate-600">
              <th className="py-2 px-2">Name</th>
              <th className="py-2 px-2">Code</th>
              <th className="py-2 px-2">Standard</th>
              <th className="py-2 px-2">Type</th>
              <th className="py-2 px-2">Elective</th>
              <th className="py-2 px-2">Classes Mapped</th>
              <th className="py-2 px-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredSubjects.map((s) => (
              <tr key={s._id} className="border-b border-slate-100">
                <td className="py-2 px-2">{s.name}</td>
                <td className="py-2 px-2">{s.code || "-"}</td>
                <td className="py-2 px-2">{s.standard || "-"}</td>
                <td className="py-2 px-2">{s.subject_type || "-"}</td>
                <td className="py-2 px-2">
                  {s.is_elective ? (
                    <span className="px-2 py-0.5 rounded-full bg-yellow-50 text-yellow-700 border border-yellow-200">
                      Yes
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-500 border border-slate-200">
                      No
                    </span>
                  )}
                </td>
                <td className="py-2 px-2">
                  {(s.classroom_ids || [])
                    .map(
                      (cid) =>
                        classrooms.find((c) => c._id === cid || c.name === cid)
                          ?.label || cid
                    )
                    .join(", ") || "-"}
                </td>
                <td className="py-2 px-2">
                  <button
                    type="button"
                    onClick={() => startEdit(s)}
                    className="text-indigo-600 hover:text-indigo-800 underline text-xs"
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(s._id)}
                    className="ml-2 text-red-600 hover:text-red-800 underline text-xs"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {!filteredSubjects.length && !loading && (
              <tr>
                <td colSpan={7} className="py-4 text-slate-400">
                  No subjects found. Create your first subject above.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        {loading && (
          <div className="py-3 text-center text-slate-500 text-sm">
            Loading subjects…
          </div>
        )}
      </div>
    </div>
  );
}
