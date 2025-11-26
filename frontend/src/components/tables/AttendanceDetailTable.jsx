import React from "react";

/*
  props:
    data: [
      { date: "2025-11-01", status: "present", remarks: "..." },
      ...
    ],
    loading: boolean
    error: string
    student: object (optional, for panel above table)
    classroom: object (optional)
    exportCSV: function (optional, for CSV button)
*/
export default function AttendanceDetailTable({
  data = [],
  loading = false,
  error = "",
  student = null,
  classroom = null,
  exportCSV,
}) {
  return (
    <div className="bg-white/90 border border-slate-100 rounded-xl shadow-sm p-5">
      <div className="mb-2 flex flex-wrap justify-between items-center">
        <div>
          <div className="text-lg font-bold text-slate-700">
            Daily Attendance Detail
          </div>
          <div className="text-xs text-slate-400 mt-0.5">
            {student?.name && <>Student: <span className="font-semibold">{student.name}</span> | </>}
            {classroom?.label && <>Class: <span className="font-semibold">{classroom.label}</span></>}
          </div>
        </div>
        {exportCSV && (
          <button
            onClick={exportCSV}
            className="bg-indigo-600 text-white text-xs px-3 py-1 rounded shadow hover:bg-indigo-700"
          >
            Export CSV
          </button>
        )}
      </div>
      {error && <div className="mb-2 text-red-600 text-xs">{error}</div>}
      {loading ? (
        <div className="py-6 text-indigo-500 text-center font-semibold animate-pulse">Loading…</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-center">
            <thead>
              <tr className="bg-slate-100 text-slate-600">
                <th className="py-2 px-2">Date</th>
                <th className="py-2 px-2">Status</th>
                <th className="py-2 px-2">Remarks</th>
              </tr>
            </thead>
            <tbody>
              {data.length === 0 && (
                <tr>
                  <td className="py-5 text-slate-400" colSpan={3}>No attendance records found…</td>
                </tr>
              )}
              {data.map((rec, i) => (
                <tr key={i} className={`border-b last:border-none ${rec.status === "absent" ? "bg-red-50" : rec.status === "present" ? "bg-emerald-50" : ""}`}>
                  <td className="py-1 px-2">{rec.date}</td>
                  <td className={`py-1 px-2 font-bold ${rec.status === "absent" ? "text-red-500" : "text-emerald-600"}`}>
                    {rec.status?.charAt(0).toUpperCase() + rec.status?.slice(1) || "-"}
                  </td>
                  <td className="py-1 px-2">{rec.remarks || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
