import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchMyClasses } from "../../api/api";
import Loader from "../../components/common/loader";

export default function MyClassesPage() {
  const [classes, setClasses] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    fetchMyClasses()
      .then((res) => setClasses(res.data))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Loader />;

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6">My Assigned Classes</h1>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {classes.map((cls) => (
          <div 
            key={cls._id} 
            onClick={() => navigate(`/teacher/classes/${cls._id}`)}
            className="bg-white p-6 rounded-lg shadow hover:shadow-lg cursor-pointer transition border-t-4 border-blue-500"
          >
            <h2 className="text-xl font-bold text-gray-800">{cls.name}</h2>
            <p className="text-gray-500 mt-2">Standard: {cls.standard} | Section: {cls.section}</p>
            <div className="mt-4 flex justify-between items-center">
              <span className="text-sm bg-blue-100 text-blue-700 px-2 py-1 rounded">
                {cls.student_ids?.length || 0} Students
              </span>
              <span className="text-blue-600 font-medium text-sm">View Details →</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
