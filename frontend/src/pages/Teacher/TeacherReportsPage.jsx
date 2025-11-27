import React, { useEffect, useState } from "react";
import { fetchMyClasses, fetchAttendanceStats, fetchDefaultersList } from "../../api/api";
import DefaulterListTable from "../../components/Teacher/DefaulterListTable";
import ExportPDFButton from "../../components/ExportPDFButton"; 
import Loader from "../../components/common/loader";

export default function TeacherReportsPage() {
  const [classes, setClasses] = useState([]);
  const [selectedClass, setSelectedClass] = useState("");
  const [stats, setStats] = useState(null);
  const [defaulters, setDefaulters] = useState([]);
  const [loading, setLoading] = useState(false);

  // Load Classes
  useEffect(() => {
    fetchMyClasses().then(res => {
        setClasses(res.data || []);
        if(res.data?.length > 0) setSelectedClass(res.data[0]._id);
    });
  }, []);

  // Load Report Data when class changes
  useEffect(() => {
    if(!selectedClass) return;
    setLoading(true);
    
    Promise.all([
        fetchAttendanceStats({ classroom_id: selectedClass }),
        fetchDefaultersList(selectedClass) // < 75% logic handled in backend or here
    ]).then(([statsRes, defaultersRes]) => {
        setStats(statsRes.data); // Summary Stats
        // If backend doesn't have explicit defaulter API, filter from stats here
        const allStats = statsRes.data?.data || [];
        const lowAttendance = allStats.filter(s => s.attendance_percent < 75);
        setDefaulters(lowAttendance);
    }).finally(() => setLoading(false));

  }, [selectedClass]);

  return (
    <div className="p-6 bg-gray-50 min-h-screen">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-800">Class Reports</h1>
        <select 
            className="border p-2 rounded bg-white shadow-sm"
            value={selectedClass}
            onChange={e => setSelectedClass(e.target.value)}
        >
            {classes.map(c => <option key={c._id} value={c._id}>{c.name}</option>)}
        </select>
      </div>

      {loading ? <Loader /> : (
        <>
           {/* Summary Cards */}
           <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
              <div className="bg-blue-50 p-4 rounded-lg border border-blue-100 text-center">
                  <h3 className="text-blue-800 text-sm font-bold">Total Students</h3>
                  <p className="text-2xl font-bold text-blue-900 mt-1">{defaulters.length + (stats?.data?.length || 0) - defaulters.length}</p>
              </div>
              <div className="bg-green-50 p-4 rounded-lg border border-green-100 text-center">
                  <h3 className="text-green-800 text-sm font-bold">Average Attendance</h3>
                  <p className="text-2xl font-bold text-green-900 mt-1">
                    {/* Calc Average */}
                    {stats?.data?.length 
                        ? (stats.data.reduce((acc, curr) => acc + curr.attendance_percent, 0) / stats.data.length).toFixed(1) 
                        : 0}%
                  </p>
              </div>
              <div className="bg-red-50 p-4 rounded-lg border border-red-100 text-center">
                  <h3 className="text-red-800 text-sm font-bold">Defaulters (&lt;75%)</h3>
                  <p className="text-2xl font-bold text-red-600 mt-1">{defaulters.length}</p>
              </div>
           </div>

           {/* Action Bar */}
           <div className="flex justify-end mb-4">
                <ExportPDFButton 
                    targetId="report-content" 
                    fileName={`Report_${classes.find(c=>c._id===selectedClass)?.name}`} 
                />
           </div>

           {/* Printable Area */}
           <div id="report-content" className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
                <h2 className="text-lg font-bold mb-4 border-b pb-2">
                    Defaulter List (Below 75%)
                </h2>
                <DefaulterListTable students={defaulters} />
                
                {/* Full Attendance Table (Optional, or shown below) */}
                <h2 className="text-lg font-bold mt-8 mb-4 border-b pb-2">
                    Full Class Attendance
                </h2>
                <div className="overflow-x-auto">
                    <table className="w-full text-sm text-left">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="p-2">Student</th>
                                <th className="p-2">Total Days</th>
                                <th className="p-2">Present</th>
                                <th className="p-2">Absent</th>
                                <th className="p-2">Percentage</th>
                            </tr>
                        </thead>
                        <tbody>
                            {stats?.data?.map(s => (
                                <tr key={s.student_id} className="border-b">
                                    <td className="p-2 font-medium">{s.name || s.student_id}</td>
                                    <td className="p-2">{s.total_days}</td>
                                    <td className="p-2 text-green-600">{s.present_days}</td>
                                    <td className="p-2 text-red-600">{s.absent_days}</td>
                                    <td className="p-2 font-bold">
                                        {s.attendance_percent.toFixed(1)}%
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
           </div>
        </>
      )}
    </div>
  );
}
