import React from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";

// Stats = [{ student_id, present_days, absent_days }]
export default function AttendanceBarChart({ stats = [] }) {
  return (
    <ResponsiveContainer width="100%" height={220} minWidth={220} minHeight={120}>
      <BarChart data={stats}>
        <XAxis dataKey="student_id" label={{ value: "Student ID", position: "insideBottom", offset: -2 }} />
        <YAxis label={{ value: "Classes", angle: -90, position: "insideLeft", offset: -4 }} />
        <Tooltip formatter={(val, name) => [val, name === "present_days" ? "Present" : "Absent"]} />
        <Legend formatter={(value) => (value === "present_days" ? "Present" : "Absent")} />
        <Bar dataKey="present_days" fill="#34D399" name="Present" />
        <Bar dataKey="absent_days" fill="#F87171" name="Absent" />
      </BarChart>
    </ResponsiveContainer>
  );
}
