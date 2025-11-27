import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { fetchClassDetails, uploadStudentPhoto } from "../../api/api";
import Loader from "../../components/common/loader";

export default function ClassDetailsPage() {
  const { id } = useParams();
  const [classData, setClassData] = useState(null);
  const [students, setStudents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(null); // ID of student being uploaded

  useEffect(() => {
    fetchClassDetails(id)
      .then((res) => {
        setClassData(res.data.classroom);
        setStudents(res.data.students);
      })
      .finally(() => setLoading(false));
  }, [id]);

  const handlePhotoUpload = async (studentId, file) => {
    if (!file) return;
    const formData = new FormData();
    formData.append("photo", file);

    try {
      setUploading(studentId);
      await uploadStudentPhoto(studentId, formData);
      alert("Photo uploaded successfully!");
      // Refresh list or update local state ideally
    } catch (err) {
      alert("Failed to upload photo");
    } finally {
      setUploading(null);
    }
  };

  if (loading) return <Loader />;

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-2">{classData?.name} - Students</h1>
      <p className="text-gray-500 mb-6">Manage students and photos for this class.</p>

      <div className="bg-white shadow rounded-lg overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Roll No</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Action</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {students.map((student) => (
              <tr key={student._id}>
                <td className="px-6 py-4 whitespace-nowrap">
                  <div className="flex items-center">
                    <div className="flex-shrink-0 h-10 w-10">
                      {/* Placeholder or Actual Image */}
                      <div className="h-10 w-10 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 font-bold">
                        {student.name.charAt(0)}
                      </div>
                    </div>
                    <div className="ml-4">
                      <div className="text-sm font-medium text-gray-900">{student.name}</div>
                    </div>
                  </div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {student.roll_number || "N/A"}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                  <label className="text-blue-600 hover:text-blue-900 cursor-pointer">
                    {uploading === student._id ? "Uploading..." : "Update Photo"}
                    <input 
                      type="file" 
                      className="hidden" 
                      accept="image/*"
                      onChange={(e) => handlePhotoUpload(student._id, e.target.files[0])}
                    />
                  </label>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
