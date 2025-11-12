import React, { useEffect, useState } from "react";
import { getStudents, getTeachers, getClassrooms, getTodayAttendance } from "../api/api";

export default function Dashboard({ token }) {
  const [stats, setStats] = useState({
    totalStudents: "--",
    totalTeachers: "--",
    totalClassrooms: "--",
    todaysAttendance: "--"
  });

  useEffect(() => {
    // Fetch stats from API
    async function fetchStats() {
      try {
        const sRes = await getStudents(token);   // expects {data: [...]}
        const tRes = await getTeachers(token);
        const cRes = await getClassrooms(token);
        const aRes = await getTodayAttendance(token);

        setStats({
          totalStudents: sRes.data.data.length,
          totalTeachers: tRes.data.data.length,
          totalClassrooms: cRes.data.data.length,
          todaysAttendance: aRes.data?.data?.attendance_percent + "%", // adjust as per your API response
        });
      } catch (err) {
        // Error handle
      }
    }
    fetchStats();
  }, [token]);

  return (
    <div style={{ padding: "2rem" }}>
      <h2>Dashboard</h2>
      <div style={{ display: "flex", gap: "2rem" }}>
        <div style={{ background: "#e3e3e3", padding: "1rem", borderRadius: "8px" }}>
          <h3>Total Students</h3>
          <p>{stats.totalStudents}</p>
        </div>
        <div style={{ background: "#e3e3e3", padding: "1rem", borderRadius: "8px" }}>
          <h3>Total Teachers</h3>
          <p>{stats.totalTeachers}</p>
        </div>
        <div style={{ background: "#e3e3e3", padding: "1rem", borderRadius: "8px" }}>
          <h3>Total Classrooms</h3>
          <p>{stats.totalClassrooms}</p>
        </div>
        <div style={{ background: "#d3ffe3", padding: "1rem", borderRadius: "8px" }}>
          <h3>Today's Attendance</h3>
          <p>{stats.todaysAttendance}</p>
        </div>
      </div>
    </div>
  );
}
