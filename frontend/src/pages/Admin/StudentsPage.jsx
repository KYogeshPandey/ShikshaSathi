// frontend/src/pages/Admin/StudentsPage.jsx
import React, { useEffect, useMemo, useState } from "react";
import {
  fetchStudents,
  createStudent,
  updateStudent,
  deleteStudent,
  bulkMoveStudents,
  fetchClassrooms,
  fetchAttendanceStats,
} from "../../api/api";

const emptyForm = {
  name: "",
  roll_no: "",
  classroom_id: "",
  email: "",
};

export default function StudentsPage() {
  const [students, setStudents] = useState([]);
  const [classrooms, setClassrooms] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState(null);

  const [filterClassroomId, setFilterClassroomId] = useState("");
  const [search, setSearch] = useState("");

  const [selectedIds, setSelectedIds] = useState([]);
  const [bulkTargetClassroomId, setBulkTargetClassroomId] = useState("");

  const [activeStudent, setActiveStudent] = useState(null);
  const [attendanceSummary, setAttendanceSummary] = useState(null);
  const [attendanceLoading, setAttendanceLoading] = useState(false);

  function resetMessages() {
    setError("");
    setSuccess("");
  }

  async function loadBaseData() {
    resetMessages();
    setLoading(true);
    try {
      const [stuRes, clsRes] = await Promise.all([
        fetchStudents({
          classroom_id: filterClassroomId || undefined,
          q: search || undefined,
        }),
        fetchClassrooms(),
      ]);
      setStudents(stuRes.data.data || []);
      setClassrooms(clsRes.data.data || []);
    } catch (err) {
      console.error("Error loading students/classes", err);
      setError("Could not load students or classes.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadBaseData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterClassroomId]);

  // search ko client side pe bhi apply kar lete hain, backend q support na bhi kare to
  const filteredStudents = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return students;
    return students.filter((s) => {
      const name = String(s.name || "").toLowerCase();
      const roll = String(s.roll_no || "").toLowerCase();
      const email = String(s.email || "").toLowerCase();
      return (
        name.includes(q) ||
        roll.includes(q) ||
        email.includes(q)
      );
    });
  }, [students, search]);

  function handleFormChange(e) {
    const { name, value } = e.target;
    setForm((f) => ({ ...f, [name]: value }));
  }

  function startCreate() {
    resetMessages();
    setEditingId(null);
    setForm(emptyForm);
  }

  function startEdit(stu) {
    resetMessages();
    setEditingId(stu._id);
    setForm({
      name: stu.name || "",
      roll_no: stu.roll_no || "",
      classroom_id: stu.classroom_id || "",
      email: stu.email || "",
    });
  }

  async function handleSubmit(e) {
    e.preventDefault();
    resetMessages();

    if (!form.name.trim() || !form.roll_no.trim() || !form.classroom_id) {
      setError("Name, Roll No and Class are required.");
      return;
    }

    setSaving(true);
    try {
      const payload = {
        name: form.name.trim(),
        roll_no: form.roll_no.trim(),
        classroom_id: form.classroom_id,
        email: form.email.trim() || undefined,
      };

      if (editingId) {
        await updateStudent(editingId, payload);
        setSuccess("Student updated.");
      } else {
        await createStudent(payload);
        setSuccess("Student created.");
      }

      setForm(emptyForm);
      setEditingId(null);
      await loadBaseData();
    } catch (err) {
      console.error("Error saving student", err);
      setError(
        err.response?.data?.message || "Failed to save student. Check console."
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id) {
    resetMessages();
    if (!window.confirm("Delete / deactivate this student?")) return;
    try {
      await deleteStudent(id);
      setSuccess("Student deleted.");
      await loadBaseData();
      if (activeStudent && activeStudent._id === id) {
        setActiveStudent(null);
        setAttendanceSummary(null);
      }
    } catch (err) {
      console.error("Error deleting student", err);
      setError(
        err.response?.data?.message || "Failed to delete student. Check console."
      );
    }
  }

  function toggleSelect(id) {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  function toggleSelectAll() {
    const allIds = filteredStudents.map((s) => s._id);
    const allSelected = allIds.every((id) => selectedIds.includes(id));
    if (allSelected) {
      setSelectedIds((prev) => prev.filter((id) => !allIds.includes(id)));
    } else {
      setSelectedIds(Array.from(new Set([...selectedIds, ...allIds])));
    }
  }

  async function handleBulkMove() {
    resetMessages();
    if (!selectedIds.length) {
      setError("Select at least one student to move.");
      return;
    }
    if (!bulkTargetClassroomId) {
      setError("Select target class for bulk move.");
      return;
    }
    if (
      !window.confirm(
        `Move ${selectedIds.length} student(s) to selected class?`
      )
    ) {
      return;
    }
    try {
      await bulkMoveStudents(selectedIds, bulkTargetClassroomId);
      setSuccess("Students moved to new class.");
      setSelectedIds([]);
      setBulkTargetClassroomId("");
      await loadBaseData();
    } catch (err) {
      console.error("Error in bulk move", err);
      setError(
        err.response?.data?.message || "Failed to move students. Check console."
      );
    }
  }

  async function openStudentDetails(stu) {
    setActiveStudent(stu);
    setAttendanceSummary(null);
    setAttendanceLoading(true);
    try {
      // simple approach: stats ko classroom_id se lao aur roll_no/student_id se filter karo
      const res = await fetchAttendanceStats({
        classroom_id: stu.classroom_id,
      });
      const stats = res.data.data || [];
      const match =
        stats.find(
          (x) =>
            x.student_id === stu.roll_no || x.student_id === stu._id
        ) || null;
      setAttendanceSummary(match);
    } catch (err) {
      console.error("Error loading attendance summary", err);
    } finally {
      setAttendanceLoading(false);
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

  return (
    <div className="bg-white/90 border border-slate-100 rounded-xl shadow-sm p-5 flex flex-col lg:flex-row gap-4">
      {/* Left: main list and actions */}
      <div className="flex-1 min-w-0">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-4">
          <div>
            <h2 className="text-xl font-bold text-slate-800">Students</h2>
            <p className="text-xs text-slate-500 mt-1">
              Manage student records, enrollment and quick promotion between classes.
            </p>
          </div>
          <button
            type="button"
            onClick={startCreate}
            className="bg-emerald-600 text-white text-sm px-4 py-2 rounded-lg shadow hover:bg-emerald-700 transition"
          >
            {editingId ? "Create New Student" : "Add Student"}
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

        {/* Filters + bulk move bar */}
        <div className="mb-4 flex flex-col lg:flex-row gap-3 items-start lg:items-end">
          <div className="flex gap-2 items-center">
            <label className="text-[11px] text-slate-500">Class filter</label>
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
              placeholder="Search by name, roll no, email"
              className="flex-1 border border-slate-300 rounded-md px-2 py-1.5 text-xs bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <div className="flex flex-wrap gap-2 items-center">
            <select
              value={bulkTargetClassroomId}
              onChange={(e) => setBulkTargetClassroomId(e.target.value)}
              className="border border-slate-300 rounded-md px-2 py-1.5 text-xs bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="">Move selected to…</option>
              {classOptions.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={handleBulkMove}
              className="bg-indigo-600 text-white text-xs px-3 py-1.5 rounded-md shadow hover:bg-indigo-700 disabled:bg-slate-400"
              disabled={!selectedIds.length || !bulkTargetClassroomId}
            >
              Move ({selectedIds.length})
            </button>
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
              placeholder="Student Name"
              required
            />
          </div>

          <div className="flex flex-col">
            <label className="text-[11px] text-slate-500 mb-1">Roll No *</label>
            <input
              name="roll_no"
              value={form.roll_no}
              onChange={handleFormChange}
              className="border border-slate-300 rounded-md px-2 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="S001"
              required
            />
          </div>

          <div className="flex flex-col">
            <label className="text-[11px] text-slate-500 mb-1">Class *</label>
            <select
              name="classroom_id"
              value={form.classroom_id}
              onChange={handleFormChange}
              className="border border-slate-300 rounded-md px-2 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
              required
            >
              <option value="">Select class</option>
              {classOptions.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col">
            <label className="text-[11px] text-slate-500 mb-1">Email</label>
            <input
              name="email"
              value={form.email}
              onChange={handleFormChange}
              className="border border-slate-300 rounded-md px-2 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="student@example.com"
            />
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
                ? "Update Student"
                : "Create Student"}
            </button>
          </div>
        </form>

        {/* Students table */}
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead>
              <tr className="bg-slate-100 text-slate-600">
                <th className="py-2 px-2">
                  <input
                    type="checkbox"
                    onChange={toggleSelectAll}
                    checked={
                      filteredStudents.length > 0 &&
                      filteredStudents.every((s) => selectedIds.includes(s._id))
                    }
                  />
                </th>
                <th className="py-2 px-2">Name</th>
                <th className="py-2 px-2">Roll No</th>
                <th className="py-2 px-2">Class</th>
                <th className="py-2 px-2">Email</th>
                <th className="py-2 px-2 text-center">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredStudents.map((stu) => (
                <tr
                  key={stu._id}
                  className="border-b border-slate-100 hover:bg-slate-50"
                >
                  <td className="py-2 px-2">
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(stu._id)}
                      onChange={() => toggleSelect(stu._id)}
                    />
                  </td>
                  <td
                    className="py-2 px-2 cursor-pointer text-indigo-700"
                    onClick={() => openStudentDetails(stu)}
                  >
                    {stu.name}
                  </td>
                  <td className="py-2 px-2">{stu.roll_no}</td>
                  <td className="py-2 px-2">
                    {classOptions.find((c) => c.id === stu.classroom_id)?.label ||
                      "-"}
                  </td>
                  <td className="py-2 px-2">{stu.email || "-"}</td>
                  <td className="py-2 px-2 text-center space-x-2">
                    <button
                      type="button"
                      onClick={() => startEdit(stu)}
                      className="text-xs text-indigo-600 hover:text-indigo-800 underline"
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDelete(stu._id)}
                      className="text-xs text-red-600 hover:text-red-800 underline"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
              {!filteredStudents.length && !loading && (
                <tr>
                  <td colSpan={6} className="py-4 text-slate-400 text-center">
                    No students found. Create your first student above.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          {loading && (
            <div className="py-3 text-center text-slate-500 text-sm">
              Loading students…
            </div>
          )}
        </div>
      </div>

      {/* Right: Student 360° mini panel */}
      <div className="w-full lg:w-80 border border-slate-100 bg-slate-50 rounded-xl p-3">
        <h3 className="text-sm font-semibold text-slate-700 mb-2">
          Student 360° mini
        </h3>
        {!activeStudent && (
          <p className="text-xs text-slate-500">
            Select a student from the list to view profile and attendance summary.
          </p>
        )}
        {activeStudent && (
          <div className="space-y-3">
            <div className="bg-white border border-slate-200 rounded-lg p-3">
              <div className="text-sm font-semibold text-slate-800">
                {activeStudent.name}
              </div>
              <div className="text-[11px] text-slate-500">
                Roll: {activeStudent.roll_no}
              </div>
              <div className="text-[11px] text-slate-500">
                Class:{" "}
                {classOptions.find((c) => c.id === activeStudent.classroom_id)
                  ?.label || "-"}
              </div>
              <div className="text-[11px] text-slate-500">
                Email: {activeStudent.email || "-"}
              </div>
            </div>

            <div className="bg-white border border-slate-200 rounded-lg p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-semibold text-slate-700">
                  Attendance summary
                </span>
                {attendanceLoading && (
                  <span className="text-[10px] text-slate-400">Loading…</span>
                )}
              </div>
              {!attendanceSummary && !attendanceLoading && (
                <p className="text-[11px] text-slate-500">
                  No summarized attendance found for this student/class.
                </p>
              )}
              {attendanceSummary && (
                <div className="text-[11px] text-slate-600 space-y-1">
                  <div>
                    Present days:{" "}
                    <span className="font-semibold">
                      {attendanceSummary.present_days}
                    </span>
                  </div>
                  <div>
                    Absent days:{" "}
                    <span className="font-semibold">
                      {attendanceSummary.absent_days}
                    </span>
                  </div>
                  <div>
                    Overall %:{" "}
                    <span className="font-semibold">
                      {attendanceSummary.attendance_percent?.toFixed?.(1) ??
                        attendanceSummary.attendance_percent}
                      %
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
