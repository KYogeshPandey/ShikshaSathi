// frontend/src/api/api.js
import axios from "axios";

// .env wali URL setup
const API_URL = process.env.REACT_APP_API_URL || "http://localhost:5000";

// Common axios instance
export const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
});

// Attach token if exists
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
export const fetchStudents = (params = {}) =>
  api.get("/students/admin", { params });

export const createStudent = (data) => api.post("/students/admin", data);

export const updateStudent = (id, data) =>
  api.put(`/students/admin/${id}`, data);

export const deleteStudent = (id) => api.delete(`/students/admin/${id}`);

export const bulkMoveStudents = (studentIds, newClassroomId) =>
  api.post("/students/admin/bulk-move", {
    student_ids: studentIds,
    new_classroom_id: newClassroomId,
  });

// ---------- Teachers ----------
export const fetchTeachers = () => api.get("/teachers/");

export const createTeacher = (data) => api.post("/teachers/", data);

export const updateTeacher = (id, data) =>
  api.put(`/teachers/${id}`, data);

export const deleteTeacher = (id) => api.delete(`/teachers/${id}`);

export const assignTeacherClassroom = (teacherId, classroomId) =>
  api.post(`/teachers/${teacherId}/assign_classroom`, {
    classroom_id: classroomId,
  });

export const removeTeacherClassroom = (teacherId, classroomId) =>
  api.post(`/teachers/${teacherId}/remove_classroom`, {
    classroom_id: classroomId,
  });

// ---------- Classrooms ----------
export const fetchClassrooms = () => api.get("/classrooms/");

// --- FIXED: Added Missing Classroom Functions ---
export const createClassroom = (data) => api.post("/classrooms/", data);

export const updateClassroom = (id, data) =>
  api.put(`/classrooms/${id}`, data);

export const deleteClassroom = (id) => api.delete(`/classrooms/${id}`);
// -------------------------------------------------

// ---------- Subjects ----------
export const fetchSubjects = (params = {}) =>
  api.get("/subjects/", { params });

export const createSubject = (data) => api.post("/subjects/", data);

export const updateSubject = (id, data) =>
  api.put(`/subjects/${id}`, data);

export const deleteSubject = (id, hard = false) =>
  api.delete(`/subjects/${id}?hard=${hard ? "true" : "false"}`);

// ---------- Attendance Analytics ----------
export const fetchAttendanceStats = (params = {}) =>
  api.get("/attendance/stats", { params });

export const fetchMyStats = () => api.get("/attendance/mystats");

export const saveBulkAttendance = (records) =>
  api.post("/attendance/manual", records);

// ---------- Attendance Report/Leaderboard ----------
export const fetchAttendanceReport = (params = {}) =>
  api.get("/reports/report", { params });

export const fetchClassroomLeaderboard = (params = {}) =>
  api.get("/reports/classroom_leaderboard", { params });

// ---------- API aggregate export (optional) ----------

const apiService = {
  loginRequest,

  // students
  fetchStudents,
  createStudent,
  updateStudent,
  deleteStudent,
  bulkMoveStudents,

  // teachers
  fetchTeachers,
  createTeacher,
  updateTeacher,
  deleteTeacher,
  assignTeacherClassroom,
  removeTeacherClassroom,

  // classrooms
  fetchClassrooms,
  createClassroom, // Added here too
  updateClassroom, // Added here too
  deleteClassroom, // Added here too

  // subjects
  fetchSubjects,
  createSubject,
  updateSubject,
  deleteSubject,

  // attendance & reports
  fetchAttendanceStats,
  fetchMyStats,
  saveBulkAttendance,
  fetchAttendanceReport,
  fetchClassroomLeaderboard,
};

export default apiService;
