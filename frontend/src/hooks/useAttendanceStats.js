// frontend/src/hooks/useAttendanceStats.js
import { useEffect, useState, useCallback } from "react";
import { fetchAttendanceStats } from "../api/api";

export default function useAttendanceStats({
  classroomId = "",
  studentId = "",
  from = "",
  to = "",
  subject = "",
}) {
  const [stats, setStats] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Params build helper
  const buildParams = useCallback(() => {
    const params = {};
    if (classroomId) params.classroom_id = classroomId;
    if (studentId) params.student_id = studentId;
    if (from) params.from = from;
    if (to) params.to = to;
    if (subject) params.subject = subject;
    return params;
  }, [classroomId, studentId, from, to, subject]);

  // Fetch stats
  const fetchStats = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetchAttendanceStats(buildParams());
      setStats(res.data.data || []);
    } catch (err) {
      setStats([]);
      setError(
        err.response?.data?.message ||
          err.message ||
          "Could not fetch attendance stats."
      );
    } finally {
      setLoading(false);
    }
  }, [buildParams]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  // Expose reload for UI manual triggers
  return { stats, loading, error, reload: fetchStats };
}
