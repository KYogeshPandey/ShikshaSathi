import React, { useEffect, useState } from "react";
import { fetchMyClasses, fetchClassDetails, fetchDailyAttendance, saveBulkAttendance } from "../../api/api";
import Loader from "../../components/common/loader";

function getStudentKey(s, index) {
  return s._id || s.student_id || s.roll_no || `student-${index}`;
}

export default function AttendancePage({ onBack }) {
  const [classes, setClasses] = useState([]);
  const [selectedClass, setSelectedClass] = useState("");
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [students, setStudents] = useState([]);
  
  // Status and Remarks Map
  const [statusMap, setStatusMap] = useState({});
  const [remarksMap, setRemarksMap] = useState({});
  
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [isUpdateMode, setIsUpdateMode] = useState(false);

  // 1. Load Teacher's Classes
  useEffect(() => {
    fetchMyClasses()
      .then((res) => {
        setClasses(res.data || []);
        if(res.data?.length > 0) setSelectedClass(res.data[0]._id);
      })
      .catch(() => setMessage("Could not fetch classes"));
  }, []);

  // 2. Load Data (Students + Existing Attendance)
  useEffect(() => {
    if (!selectedClass || !date) {
      setStudents([]);
      setStatusMap({});
      setRemarksMap({});
      return;
    }

    setLoading(true);
    setMessage("");
    
    // Parallel Fetch: Class details (Students) + Daily Attendance (Existing)
    Promise.all([
        fetchClassDetails(selectedClass),
        fetchDailyAttendance(selectedClass, date)
    ])
    .then(([classRes, attendanceRes]) => {
        // 1. Set Student List
        const studentList = classRes.data.students || [];
        setStudents(studentList);

        // 2. Process Existing Attendance
        const existingRecords = attendanceRes.data || [];
        setIsUpdateMode(existingRecords.length > 0);

        const newStatusMap = {};
        const newRemarksMap = {};

        studentList.forEach((s, idx) => {
            const key = getStudentKey(s, idx);
            // Check if record exists for this student
            const record = existingRecords.find(r => r.student_id === s._id);
            
            if (record) {
                newStatusMap[key] = record.status; // Use saved status
                newRemarksMap[key] = record.remarks || "";
            } else {
                newStatusMap[key] = "present"; // Default
                newRemarksMap[key] = "";
            }
        });

        setStatusMap(newStatusMap);
        setRemarksMap(newRemarksMap);
    })
    .catch((err) => {
        console.error(err);
        setMessage("Error loading data. Please try again.");
    })
    .finally(() => setLoading(false));

  }, [selectedClass, date]);

  // Toggle Status
  const toggleStatus = (studentKey) => {
    setStatusMap((prev) => ({
      ...prev,
      [studentKey]: prev[studentKey] === "present" ? "absent" : "present",
    }));
  };

  // Handle Remarks Change
  const handleRemarkChange = (studentKey, text) => {
    setRemarksMap((prev) => ({ ...prev, [studentKey]: text }));
  };

  // Submit Logic
  async function handleSave() {
    if (!selectedClass || !date || students.length === 0) return;
    setSaving(true);
    setMessage("");

    const payload = students.map((s, idx) => {
      const key = getStudentKey(s, idx);
      return {
        student_id: s._id, // Always use Mongo ID for consistency
        classroom_id: selectedClass,
        date,
        status: statusMap[key] || "present",
        remarks: remarksMap[key] || ""
      };
    });

    try {
      const res = await saveBulkAttendance(payload);
      const count = res.data?.saved || res.data?.modifiedCount || payload.length;
      setMessage(isUpdateMode ? `✅ Updated attendance for ${count} students.` : `✅ Marked attendance for ${count} students.`);
      setIsUpdateMode(true); // Now it's in update mode
    } catch (err) {
      console.error("Save error:", err);
      setMessage("Failed to save. Please check connection.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
            <div>
                <h1 className="text-2xl font-bold text-gray-800">
                    {isUpdateMode ? "Update Attendance" : "Mark Attendance"}
                </h1>
                <p className="text-gray-500 text-sm">
                    {isUpdateMode ? "Edit existing records for this date." : "Mark attendance for a new date."}
                </p>
            </div>
            {onBack && (
                 <button onClick={onBack} className="text-blue-600 text-sm hover:underline">
                    ← Back to Dashboard
                 </button>
            )}
        </div>

        {/* Controls */}
        <div className="bg-white p-4 rounded-lg shadow-sm border flex gap-4 mb-6 flex-wrap items-end">
            <div>
                <label className="block text-xs text-gray-500 mb-1">Class</label>
                <select 
                    className="border rounded p-2 min-w-[200px]"
                    value={selectedClass}
                    onChange={(e) => setSelectedClass(e.target.value)}
                >
                    {classes.map(c => <option key={c._id} value={c._id}>{c.name}</option>)}
                </select>
            </div>
            <div>
                <label className="block text-xs text-gray-500 mb-1">Date</label>
                <input 
                    type="date" 
                    className="border rounded p-2"
                    value={date}
                    onChange={(e) => setDate(e.target.value)}
                />
            </div>
            <div className="ml-auto">
                 <button
                    onClick={handleSave}
                    disabled={saving || loading || students.length === 0}
                    className={`px-6 py-2 rounded text-white font-bold shadow ${
                        saving ? "bg-gray-400" : isUpdateMode ? "bg-orange-500 hover:bg-orange-600" : "bg-emerald-600 hover:bg-emerald-700"
                    }`}
                >
                    {saving ? "Saving..." : isUpdateMode ? "Update Records" : "Submit"}
                </button>
            </div>
        </div>

        {/* Message Banner */}
        {message && (
             <div className={`p-3 rounded mb-4 text-sm ${message.includes("Failed") ? "bg-red-50 text-red-700" : "bg-green-50 text-green-700"}`}>
                {message}
             </div>
        )}

        {/* Table */}
        {loading ? <Loader /> : students.length === 0 ? (
            <div className="text-center text-gray-400 py-10 bg-white rounded shadow">No students found or no class selected.</div>
        ) : (
            <div className="bg-white rounded-lg shadow overflow-hidden">
                <table className="w-full text-sm text-left">
                    <thead className="bg-gray-100 text-gray-600 uppercase text-xs">
                        <tr>
                            <th className="px-6 py-3">Student</th>
                            <th className="px-6 py-3 text-center">Status</th>
                            <th className="px-6 py-3">Remarks</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                        {students.map((s, idx) => {
                            const key = getStudentKey(s, idx);
                            const isPresent = statusMap[key] === "present";
                            return (
                                <tr key={key} className={`hover:bg-gray-50 transition ${!isPresent ? "bg-red-50" : ""}`}>
                                    <td className="px-6 py-4 font-medium text-gray-700">
                                        {s.name}
                                        <div className="text-xs text-gray-400 font-normal">{s.roll_number || "No Roll No"}</div>
                                    </td>
                                    <td className="px-6 py-4 text-center">
                                        <button 
                                            onClick={() => toggleStatus(key)}
                                            className={`px-4 py-1 rounded-full text-xs font-bold border transition ${
                                                isPresent 
                                                ? "bg-emerald-100 text-emerald-700 border-emerald-200 hover:bg-emerald-200" 
                                                : "bg-red-100 text-red-700 border-red-200 hover:bg-red-200"
                                            }`}
                                        >
                                            {isPresent ? "PRESENT" : "ABSENT"}
                                        </button>
                                    </td>
                                    <td className="px-6 py-4">
                                        <input 
                                            type="text" 
                                            placeholder="Reason (Optional)"
                                            className="w-full border-b border-transparent focus:border-blue-500 bg-transparent outline-none text-gray-600 placeholder-gray-300"
                                            value={remarksMap[key] || ""}
                                            onChange={(e) => handleRemarkChange(key, e.target.value)}
                                        />
                                    </td>
                                </tr>
                            )
                        })}
                    </tbody>
                </table>
            </div>
        )}
      </div>
    </div>
  );
}
