import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import TeacherStatsCards from "../../components/Teacher/TeacherStatsCards";
import { fetchMyStats, fetchMySchedule, fetchNoticeFeed } from "../../api/api";
import Loader from "../../components/common/loader";

export default function TeacherDashboard() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({});
  const [schedule, setSchedule] = useState([]);
  const [notices, setNotices] = useState([]);

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    try {
      setLoading(true);
      // Load Stats, Schedule, and Notices in parallel
      const [statsRes, scheduleRes, noticesRes] = await Promise.all([
        fetchMyStats().catch(() => ({ data: { totalClasses: 0, pendingAttendance: 0, lowAttendanceCount: 0 } })),
        fetchMySchedule().catch(() => ({ data: [] })),
        fetchNoticeFeed().catch(() => ({ data: [] })),
      ]);
      
      setStats(statsRes.data);
      // Show only today's remaining classes or first few upcoming
      setSchedule(scheduleRes.data ? scheduleRes.data.slice(0, 5) : []);
      setNotices(noticesRes.data ? noticesRes.data.slice(0, 4) : []);
    } catch (err) {
      console.error("Dashboard Load Error", err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <Loader />;

  return (
    <div className="p-6 bg-gray-50 min-h-screen">
      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-800">Teacher Dashboard</h1>
          <p className="text-gray-500 mt-1">Welcome back! Here's your daily overview.</p>
        </div>
        <div className="mt-4 md:mt-0 flex gap-3">
            <button 
                onClick={() => navigate("/teacher/attendance")}
                className="bg-emerald-600 text-white px-5 py-2 rounded-lg shadow hover:bg-emerald-700 transition font-medium"
            >
                Mark Attendance
            </button>
            <button 
                onClick={() => navigate("/teacher/reports")}
                className="bg-blue-600 text-white px-5 py-2 rounded-lg shadow hover:bg-blue-700 transition font-medium"
            >
                View Reports
            </button>
        </div>
      </div>
      
      {/* 1. Quick Stats Widgets */}
      <TeacherStatsCards stats={stats} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mt-8">
        
        {/* 2. Today's Schedule Widget */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100 bg-blue-50 flex justify-between items-center">
            <h2 className="text-lg font-bold text-blue-800">Today's Schedule</h2>
            <span className="text-xs font-medium text-blue-600 bg-blue-100 px-2 py-1 rounded">Upcoming</span>
          </div>
          
          <div className="p-4">
            {schedule.length > 0 ? (
              <ul className="space-y-3">
                {schedule.map((slot) => (
                  <li key={slot._id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border-l-4 border-blue-400 hover:bg-blue-50 transition">
                    <div>
                      <p className="font-bold text-gray-800">{slot.subject?.name || "Unknown Subject"}</p>
                      <p className="text-xs text-gray-500 font-medium mt-1">
                        {slot.classroom?.name} • {slot.classroom?.standard} {slot.classroom?.section}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-blue-700 font-bold text-sm">{slot.start_time}</p>
                      <p className="text-xs text-gray-400">{slot.end_time}</p>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="text-center py-8">
                <div className="bg-blue-50 w-12 h-12 rounded-full flex items-center justify-center mx-auto mb-3 text-blue-400">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                </div>
                <p className="text-gray-500 text-sm">No classes scheduled for today.</p>
              </div>
            )}
          </div>
          <div className="bg-gray-50 px-6 py-3 border-t border-gray-100 text-center">
            <button onClick={() => navigate("/teacher/timetable")} className="text-sm text-blue-600 font-medium hover:underline">View Full Timetable →</button>
          </div>
        </div>

        {/* 3. Notice Board Widget */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100 bg-purple-50 flex justify-between items-center">
            <h2 className="text-lg font-bold text-purple-800">Notice Board</h2>
            <button onClick={() => navigate("/teacher/announcements")} className="text-xs bg-purple-100 text-purple-700 px-2 py-1 rounded hover:bg-purple-200 transition">+ New</button>
          </div>
          
          <div className="p-4">
            {notices.length > 0 ? (
              <ul className="space-y-3">
                {notices.map((notice) => (
                  <li key={notice._id} className="p-3 border border-gray-100 rounded-lg hover:shadow-sm transition cursor-pointer">
                    <div className="flex justify-between items-start mb-1">
                        <h4 className="font-bold text-gray-800 text-sm line-clamp-1">{notice.title}</h4>
                        <span className="text-[10px] text-gray-400 whitespace-nowrap ml-2">
                            {new Date(notice.created_at).toLocaleDateString()}
                        </span>
                    </div>
                    <p className="text-xs text-gray-600 line-clamp-2">{notice.content}</p>
                    <div className="mt-2 flex items-center gap-2">
                        <div className="w-4 h-4 rounded-full bg-purple-100 text-purple-600 flex items-center justify-center text-[8px] font-bold">
                            {notice.posted_by_name?.[0] || "T"}
                        </div>
                        <p className="text-[10px] text-gray-400">Posted by: {notice.posted_by_name}</p>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="text-center py-8">
                 <div className="bg-purple-50 w-12 h-12 rounded-full flex items-center justify-center mx-auto mb-3 text-purple-400">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                    </svg>
                </div>
                <p className="text-gray-500 text-sm">No active notices right now.</p>
              </div>
            )}
          </div>
           <div className="bg-gray-50 px-6 py-3 border-t border-gray-100 text-center">
            <button onClick={() => navigate("/teacher/announcements")} className="text-sm text-purple-600 font-medium hover:underline">View All Notices →</button>
          </div>
        </div>

      </div>
    </div>
  );
}
