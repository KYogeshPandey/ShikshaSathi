import React from "react";

export default function DefaulterListTable({ students }) {
  if (!students || students.length === 0) {
    return <div className="text-gray-500 text-sm">No defaulters found.</div>;
  }

  return (
    <div className="overflow-x-auto bg-white rounded-lg shadow">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-red-50">
          <tr>
            <th className="px-4 py-2 text-left text-xs font-medium text-red-700 uppercase">Student</th>
            <th className="px-4 py-2 text-left text-xs font-medium text-red-700 uppercase">Class</th>
            <th className="px-4 py-2 text-left text-xs font-medium text-red-700 uppercase">Attendance %</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200">
          {students.map((s) => (
            <tr key={s.student_id}>
              <td className="px-4 py-2 text-sm text-gray-900 font-medium">{s.name}</td>
              <td className="px-4 py-2 text-sm text-gray-500">{s.classroom_name}</td>
              <td className="px-4 py-2 text-sm font-bold text-red-600">{s.attendance_percent}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
