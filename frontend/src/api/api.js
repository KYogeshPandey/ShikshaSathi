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

// ================= AUTH =================
export const loginRequest = (data) => api.post("/auth/login", data);


// ================= TEACHER SPECIFIC =================
// 1. Get Logged in Teacher's assigned classes
export const fetchMyClasses = () => api.get("/teachers/me/classes");

// 2. Get specific class details (students + basic info)
export const fetchClassDetails = (classId) => api.get(`/classrooms/${classId}/details`);

// 3. Timetable
export const fetchMySchedule = () => api.get("/timetable/my-schedule");
export const addTimetableEntry = (data) => api.post("/timetable/", data);

// 4. Announcements
export const sendNotice = (data) => api.post("/announcements/send", data);
export const fetchMyNotices = () => api.get("/announcements/history");
export const fetchNoticeFeed = () => api.get("/announcements/feed");

// 5. Attendance Operations
export const fetchMyStats = () => api.get("/attendance/mystats");
export const fetchDailyAttendance = (classroomId, date) => 
  api.get("/attendance/daily", { params: { classroom_id: classroomId, date } });

export const updateAttendanceRecord = (attendanceId, data) => 
  api.put(`/attendance/${attendanceId}`, data);

// 6. Reports
export const fetchDefaultersList = (classroomId) => 
  api.get(`/reports/defaulters`, { params: { classroom_id: classroomId, threshold: 75 } });

// 7. Photo Upload
export const uploadStudentPhoto = (studentId, formData) => 
  api.post(`/students/${studentId}/photo`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });


// ================= ADMIN / COMMON =================

// ---------- Students ----------
export const fetchStudents = (params = {}) => api.get("/students/admin", { params });
export const createStudent = (data) => api.post("/students/admin", data);
export const updateStudent = (id, data) => api.put(`/students/admin/${id}`, data);
export const deleteStudent = (id) => api.delete(`/students/admin/${id}`);
export const bulkMoveStudents = (studentIds, newClassroomId) =>
  api.post("/students/admin/bulk-move", {
    student_ids: studentIds,
    new_classroom_id: newClassroomId,
  });

// ---------- Teachers ----------
export const fetchTeachers = () => api.get("/teachers/");
export const createTeacher = (data) => api.post("/teachers/", data);
export const updateTeacher = (id, data) => api.put(`/teachers/${id}`, data);
export const deleteTeacher = (id) => api.delete(`/teachers/${id}`);
export const assignTeacherClassroom = (teacherId, classroomId) =>
  api.post(`/teachers/${teacherId}/assign_classroom`, { classroom_id: classroomId });
export const removeTeacherClassroom = (teacherId, classroomId) =>
  api.post(`/teachers/${teacherId}/remove_classroom`, { classroom_id: classroomId });

// ---------- Classrooms ----------
export const fetchClassrooms = () => api.get("/classrooms/");
export const createClassroom = (data) => api.post("/classrooms/", data);
export const updateClassroom = (id, data) => api.put(`/classrooms/${id}`, data);
export const deleteClassroom = (id) => api.delete(`/classrooms/${id}`);

// ---------- Subjects ----------
export const fetchSubjects = (params = {}) => api.get("/subjects/", { params });
export const createSubject = (data) => api.post("/subjects/", data);
export const updateSubject = (id, data) => api.put(`/subjects/${id}`, data);
export const deleteSubject = (id, hard = false) =>
  api.delete(`/subjects/${id}?hard=${hard ? "true" : "false"}`);

// ---------- Attendance Analytics ----------
export const fetchAttendanceStats = (params = {}) => api.get("/attendance/stats", { params });
export const saveBulkAttendance = (records) => api.post("/attendance/manual", records);

// ---------- Reports ----------
export const fetchAttendanceReport = (params = {}) => api.get("/reports/report", { params });
export const fetchClassroomLeaderboard = (params = {}) => api.get("/reports/classroom_leaderboard", { params });


const apiService = {
  api,
  loginRequest,

  // Teacher Specific
  fetchMyClasses,
  fetchClassDetails,
  fetchMySchedule,
  addTimetableEntry,
  sendNotice,
  fetchMyNotices,
  fetchNoticeFeed,
  fetchMyStats,
  fetchDailyAttendance,
  updateAttendanceRecord,
  fetchDefaultersList,
  uploadStudentPhoto,

  // Students
  fetchStudents,
  createStudent,
  updateStudent,
  deleteStudent,
  bulkMoveStudents,

  // Teachers
  fetchTeachers,
  createTeacher,
  updateTeacher,
  deleteTeacher,
  assignTeacherClassroom,
  removeTeacherClassroom,

  // Classrooms
  fetchClassrooms,
  createClassroom,
  updateClassroom,
  deleteClassroom,

  // Subjects
  fetchSubjects,
  createSubject,
  updateSubject,
  deleteSubject,

  // Attendance & Reports
  fetchAttendanceStats,
  saveBulkAttendance,
  fetchAttendanceReport,
  fetchClassroomLeaderboard,
};

export default apiService;
