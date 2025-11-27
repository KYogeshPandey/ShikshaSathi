import React from "react";

const StatCard = ({ title, value, color }) => (
  <div className={`bg-white p-4 rounded-lg shadow border-l-4 ${color}`}>
    <h3 className="text-gray-500 text-sm font-medium">{title}</h3>
    <p className="text-2xl font-bold text-gray-800 mt-1">{value}</p>
  </div>
);

export default function TeacherStatsCards({ stats }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
      <StatCard 
        title="Assigned Classes" 
        value={stats?.totalClasses || 0} 
        color="border-blue-500" 
      />
      <StatCard 
        title="Pending Attendance" 
        value={stats?.pendingAttendance || 0} 
        color="border-yellow-500" 
      />
      <StatCard 
        title="Low Attendance Students" 
        value={stats?.lowAttendanceCount || 0} 
        color="border-red-500" 
      />
    </div>
  );
}
