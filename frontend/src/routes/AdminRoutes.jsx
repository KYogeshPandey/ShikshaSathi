// frontend/src/routes/AdminRoutes.jsx
import { Routes, Route, Navigate } from "react-router-dom";
import ProtectedRoute from "./ProtectedRoute";
import AdminLayout from "../layout/AdminLayout";
import AdminDashboard from "../pages/Admin/AdminDashboard";
import StudentsPage from "../pages/Admin/StudentsPage";
import TeachersPage from "../pages/Admin/TeachersPage";
import ClassroomsPage from "../pages/Admin/ClassroomsPage";
import SubjectsPage from "../pages/Admin/SubjectsPage";
import AttendanceDetailPage from "../pages/Admin/AttendanceDetailPage";
import BulkImportPage from "../pages/Admin/BulkImportPage";
import AuditLogPage from "../pages/Admin/AuditLogPage";

// All routes are children of AdminLayout, so sidebar/navbar always visible
export default function AdminRoutes() {
  return (
    <Routes>
      <Route element={
        <ProtectedRoute role="admin">
          <AdminLayout />
        </ProtectedRoute>
      }>
        <Route index element={<AdminDashboard />} />
        <Route path="students" element={<StudentsPage />} />
        <Route path="teachers" element={<TeachersPage />} />
        <Route path="classrooms" element={<ClassroomsPage />} />
        <Route path="subjects" element={<SubjectsPage />} />
        <Route path="attendance" element={<AttendanceDetailPage />} />
        <Route path="bulk-import" element={<BulkImportPage />} />
        <Route path="audit-logs" element={<AuditLogPage />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Route>
    </Routes>
  );
}
