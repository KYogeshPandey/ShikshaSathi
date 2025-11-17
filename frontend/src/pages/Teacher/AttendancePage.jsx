// frontend/src/pages/Teacher/AttendancePage.jsx
import React, { useEffect, useState } from "react";
import { api, saveBulkAttendance } from "../../api/api";

export default function AttendancePage() {
  const [classes, setClasses] = useState([]);
  const [selectedClass, setSelectedClass] = useState("");
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [students, setStudents] = useState([]);
  const [statusMap, setStatusMap] = useState({});
  const [loadingStudents, setLoadingStudents] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  // Load all classes
  useEffect(() => {
    api
      .get("/classrooms/")
      .then((res) => setClasses(res.data.data || []))
      .catch(() => setMessage("Could not fetch classes"));
  }, []);

  // Load students for selected class (demo: /students/ filter UI-level)
  useEffect(() => {
    if (!selectedClass) {
      setStudents([]);
      setStatusMap({});
      return;
    }
    setLoadingStudents(true);
    setMessage("");
    api
      .get("/students/", {
        // future: params: { classroom_id: selectedClass }
      })
      .then((res) => {
        const list = (res.data.data || []).filter(
          (s) => !s.classroom_id || s.classroom_id === selectedClass,
        );
        setStudents(list);
        const initial = {};
        list.forEach((s) => {
          initial[s._id || s.roll_no || s.rollNumber || s.username] = "present";
        });
        setStatusMap(initial);
      })
      .catch(() => setMessage("Could not fetch students for this class"))
      .finally(() => setLoadingStudents(false));
  }, [selectedClass]);

  function toggleStatus(studentKey) {
    setStatusMap((prev) => ({
      ...prev,
      [studentKey]: prev[studentKey] === "present" ? "absent" : "present",
    }));
  }

  async function handleSave() {
    if (!selectedClass || !date || students.length === 0) return;
    setSaving(true);
    setMessage("");

    const payload = students.map((s) => {
      const key = s._id || s.roll_no || s.rollNumber || s.username;
      return {
        student_id: key,
        classroom_id: selectedClass,
        date,
        status: statusMap[key] || "present",
      };
    });

    try {
      const res = await saveBulkAttendance(payload);
      const saved = res.data?.saved ?? payload.length;
      setMessage(`✅ Attendance saved for ${saved} records.`);
    } catch (err) {
      console.error("❌ Error saving attendance:", err);
      setMessage(
        err.response?.data?.message ||
          "Failed to save attendance. Please try again.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-sky-50 via-emerald-50 to-slate-50 p-6">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h2 className="text-3xl font-extrabold text-sky-900 tracking-tight">
              Mark Attendance
            </h2>
            <p className="text-sm text-slate-600 mt-1">
              Select a class and date, then toggle students as present / absent.
            </p>
          </div>
          <div className="bg-white/80 backdrop-blur px-4 py-2 rounded-full shadow-sm text-xs text-slate-600 flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-sky-500" />
            <span>Manual marking · Saved to database</span>
          </div>
        </div>

        {message && (
          <div className="mb-4 text-xs md:text-sm bg-amber-50 border border-amber-200 text-amber-800 px-4 py-2 rounded">
            {message}
          </div>
        )}

        {/* Filters */}
        <div className="bg-white rounded-xl shadow-sm border border-slate-100 p-4 mb-6 flex flex-wrap gap-4 items-center">
          <div className="flex flex-col">
            <span className="text-xs text-slate-500 mb-1">Class</span>
            <select
              className="border border-slate-200 rounded-lg px-3 py-2 bg-slate-50 focus:outline-none focus:ring-2 focus:ring-sky-500"
              value={selectedClass}
              onChange={(e) => setSelectedClass(e.target.value)}
            >
              <option value="">-- Choose class --</option>
              {classes.map((cls) => (
                <option key={cls._id || cls.name} value={cls._id || cls.name}>
                  {cls.name}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col">
            <span className="text-xs text-slate-500 mb-1">Date</span>
            <input
              type="date"
              className="border border-slate-200 rounded-lg px-3 py-2 bg-slate-50 focus:outline-none focus:ring-2 focus:ring-sky-500"
              value={date}
              onChange={(e) => setDate(e.target.value)}
            />
          </div>

          <div className="mt-4 md:mt-6 text-xs text-slate-500">
            {students.length > 0 && (
              <span>
                {students.length} students loaded · Click on a row to toggle
                status.
              </span>
            )}
          </div>
        </div>

        {/* Students list */}
        <div className="bg-white rounded-xl shadow-sm border border-slate-100 p-4">
          <div className="flex items-center justify-between mb-2">
            <div className="font-semibold text-slate-700">
              {selectedClass ? "Students in selected class" : "No class selected"}
            </div>
            <button
              className="bg-sky-600 text-white text-sm px-4 py-2 rounded-lg shadow hover:bg-sky-700 transition disabled:bg-slate-400"
              onClick={handleSave}
              disabled={
                !selectedClass || !date || students.length === 0 || saving
              }
            >
              {saving ? "Saving..." : "Save Attendance"}
            </button>
          </div>

          {loadingStudents ? (
            <div className="text-sky-600 text-sm animate-pulse">
              Loading students…
            </div>
          ) : students.length === 0 ? (
            <div className="text-slate-400 text-sm py-4">
              {selectedClass
                ? "No students found for this class."
                : "Choose a class to load students."}
            </div>
          ) : (
            <div className="max-h-80 overflow-y-auto">
              <table className="w-full text-sm text-center">
                <thead>
                  <tr className="bg-slate-50 text-slate-600">
                    <th className="py-2">#</th>
                    <th className="py-2">Student</th>
                    <th className="py-2">Roll</th>
                    <th className="py-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {students.map((s, idx) => {
                    const key = s._id || s.roll_no || s.rollNumber || s.username;
                    const status = statusMap[key] || "present";
                    const isPresent = status === "present";
                    return (
                      <tr
                        key={key}
                        className="border-b border-slate-50 cursor-pointer hover:bg-slate-50"
                        onClick={() => toggleStatus(key)}
                      >
                        <td className="py-2">{idx + 1}</td>
                        <td className="py-2">
                          {s.name || s.username || s.student_id || "Student"}
                        </td>
                        <td className="py-2">
                          {s.roll_no || s.rollNumber || "--"}
                        </td>
                        <td className="py-2">
                          <span
                            className={
                              "px-3 py-1 rounded-full text-xs font-semibold " +
                              (isPresent
                                ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                                : "bg-red-50 text-red-600 border border-red-200")
                            }
                          >
                            {isPresent ? "Present" : "Absent"}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          <div className="mt-3 text-[11px] text-slate-400">
            Status toggle karne ke baad &quot;Save Attendance&quot; dabao – data
            ab MongoDB me persist ho raha hai aur dashboards isi collection se
            read kar sakte hain.
          </div>
        </div>
      </div>
    </div>
  );
}
