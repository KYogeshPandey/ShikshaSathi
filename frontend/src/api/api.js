// frontend/src/api/api.js
import axios from "axios";

// Create React App me env vars process.env se aate hain
// e.g. REACT_APP_API_URL=http://localhost:5000
const API_URL = process.env.REACT_APP_API_URL || "http://localhost:5000";

// Common axios instance
export const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
});

// Attach token automatically if present
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ---------- Auth ----------

export const loginRequest = (data) => api.post("/auth/login", data);

// ---------- Students ----------

export const fetchStudents = () => api.get("/students/");

// ---------- Teachers ----------

export const fetchTeachers = () => api.get("/teachers/");

// ---------- Classrooms ----------

export const fetchClassrooms = () => api.get("/classrooms/");

// ---------- Attendance / Report ----------

// Stats for dashboard (optionally with classroom_id, from, to)
export const fetchAttendanceStats = (params = {}) =>
  api.get("/attendance/stats", { params });

// Student own stats
export const fetchMyStats = () => api.get("/attendance/mystats");

// Save bulk attendance (teacher/admin)
export const saveBulkAttendance = (records) =>
  api.post("/attendance/manual", records);

// Export as object if needed
const apiService = {
  loginRequest,
  fetchStudents,
  fetchTeachers,
  fetchClassrooms,
  fetchAttendanceStats,
  fetchMyStats,
  saveBulkAttendance,
};

export default apiService;
