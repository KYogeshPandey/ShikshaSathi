import React, { useState, useEffect, useCallback } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import AttendanceDetailTable from "../../components/tables/AttendanceDetailTable";
import { api } from "../../api/api";

function getParam(searchParams, key) {
  return searchParams.get(key) || "";
}

// Use: /admin/attendance-detail?student_id=...&classroom_id=...&from=...&to=...
export default function AttendanceDetailPage() {
  const [searchParams] = useSearchParams();
  const [detail, setDetail] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [student, setStudent] = useState(null);
  const [classroom, setClassroom] = useState(null);

  const student_id = getParam(searchParams, "student_id");
  const classroom_id = getParam(searchParams, "classroom_id");
  const from = getParam(searchParams, "from");
  const to = getParam(searchParams, "to");

  // Fetch daily detail & optionally fetch student/class info
  const fetchDetails = useCallback(async () => {
    setLoading(true); setError(""); setDetail([]);
    try {
      const res = await api.get("/attendance/detail", { params: { student_id, classroom_id, from, to } });
      setDetail(res.data.data || []);
      if (student_id) {
        try {
          const sres = await api.get(`/students/admin/${student_id}`);
          setStudent(sres.data.data || null);
        } catch {}
      }
      if (classroom_id) {
        try {
          const cres = await api.get(`/classrooms/${classroom_id}`);
          setClassroom(cres.data.data || null);
        } catch {}
      }
    } catch (err) {
      setError("Failed to fetch attendance detail.");
    } finally {
      setLoading(false);
    }
  }, [student_id, classroom_id, from, to]);

  useEffect(() => { fetchDetails(); }, [fetchDetails]);

  // Export CSV handler
  const exportCSV = async () => {
    try {
      const params = { student_id, classroom_id, from, to };
      const res = await api.get("/attendance/export", { params, responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", "attendance-detail.csv");
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => window.URL.revokeObjectURL(url), 1000);
    } catch {
      alert("CSV export failed.");
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-indigo-50 to-slate-100 p-6">
      <AttendanceDetailTable
        data={detail}
        loading={loading}
        error={error}
        student={student}
        classroom={classroom}
        exportCSV={exportCSV}
      />
    </div>
  );
}
