import axios from 'axios';

const API_BASE = "http://localhost:5000/api/v1";

export const login = (data) => axios.post(`${API_BASE}/login`, data); // <-- Yeh export missing tha

export const getStudents = (token) => axios.get(`${API_BASE}/students/`, { headers: { Authorization: "Bearer " + token } });
export const getTeachers = (token) => axios.get(`${API_BASE}/teachers/`, { headers: { Authorization: "Bearer " + token } });
export const getClassrooms = (token) => axios.get(`${API_BASE}/classrooms/`, { headers: { Authorization: "Bearer " + token } });
export const getTodayAttendance = (token) => axios.get(`${API_BASE}/report?month=2025-11`, { headers: { Authorization: "Bearer " + token } });
