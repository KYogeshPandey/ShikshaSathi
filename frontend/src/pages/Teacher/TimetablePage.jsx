import React, { useEffect, useState } from "react";
import { fetchMySchedule } from "../../api/api";
import Loader from "../../components/common/loader";

export default function TimetablePage() {
  const [schedule, setSchedule] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchMySchedule()
      .then((res) => setSchedule(res.data || []))
      .catch((err) => console.error(err))
      .finally(() => setLoading(false));
  }, []);

  // Group by Day for better display
  const daysOrder = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  const groupedSchedule = daysOrder.reduce((acc, day) => {
    acc[day] = schedule.filter(s => s.day === day).sort((a,b) => a.start_time.localeCompare(b.start_time));
    return acc;
  }, {});

  if (loading) return <Loader />;

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6 text-gray-800">My Weekly Schedule</h1>
      
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {daysOrder.map((day) => (
          <div key={day} className="bg-white rounded-xl shadow border border-gray-200 overflow-hidden">
            <div className="bg-gray-100 px-4 py-2 border-b border-gray-200">
              <h3 className="font-bold text-gray-700">{day}</h3>
            </div>
            <div className="p-4 min-h-[100px]">
              {groupedSchedule[day]?.length > 0 ? (
                <ul className="space-y-3">
                  {groupedSchedule[day].map((slot) => (
                    <li key={slot._id} className="flex justify-between items-center p-2 bg-blue-50 rounded border-l-4 border-blue-500">
                      <div>
                        <p className="font-bold text-sm text-blue-900">{slot.subject?.name}</p>
                        <p className="text-xs text-gray-600">{slot.classroom?.name}</p>
                      </div>
                      <div className="text-right">
                        <span className="text-xs font-mono bg-white px-1 rounded border">{slot.start_time}</span>
                        <span className="block text-[10px] text-gray-400 mt-1">to {slot.end_time}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-gray-400 text-sm text-center italic mt-4">No classes</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
