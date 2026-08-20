import { Route, Routes } from "react-router-dom";
import { AdminLayout } from "../layouts/AdminLayout";
import { StudentLayout } from "../layouts/StudentLayout";
import { TeacherLayout } from "../layouts/TeacherLayout";
import { AdminDashboard } from "../pages/AdminDashboard";
import { AdminImportsPage } from "../pages/AdminImportsPage";
import { AnnouncementsPage } from "../pages/AnnouncementsPage";
import { LandingPage } from "../pages/LandingPage";
import { LoginPage } from "../pages/LoginPage";
import { ManualAttendancePage } from "../pages/ManualAttendancePage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { RecognitionAttendancePage } from "../pages/RecognitionAttendancePage";
import { ReportsPage } from "../pages/ReportsPage";
import { RoleNotFoundPage } from "../pages/RoleNotFoundPage";
import { StudentAttendancePage } from "../pages/StudentAttendancePage";
import { StudentDashboard } from "../pages/StudentDashboard";
import { TeacherDashboard } from "../pages/TeacherDashboard";
import { TeacherSchedulePage } from "../pages/TeacherSchedulePage";
import { UnauthorizedPage } from "../pages/UnauthorizedPage";
import {
  AdminAssignmentsPage,
  AdminClassroomsPage,
  AdminStudentsPage,
  AdminSubjectsPage,
  AdminTeachersPage,
  AdminTimetablePage,
} from "../pages/Admin/AdminResourcePages";
import { AuthenticatedRoute } from "../routes/AuthenticatedRoute";
import { RoleRoute } from "../routes/RoleRoute";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/unauthorized" element={<UnauthorizedPage />} />

      <Route element={<AuthenticatedRoute />}>
        <Route element={<RoleRoute role="admin" />}>
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<AdminDashboard />} />
            <Route path="classrooms" element={<AdminClassroomsPage />} />
            <Route path="subjects" element={<AdminSubjectsPage />} />
            <Route path="teachers" element={<AdminTeachersPage />} />
            <Route path="students" element={<AdminStudentsPage />} />
            <Route path="assignments" element={<AdminAssignmentsPage />} />
            <Route path="timetable" element={<AdminTimetablePage />} />
            <Route path="announcements" element={<AnnouncementsPage canManage />} />
            <Route path="imports" element={<AdminImportsPage />} />
            <Route path="reports" element={<ReportsPage />} />
            <Route path="*" element={<RoleNotFoundPage role="admin" />} />
          </Route>
        </Route>

        <Route element={<RoleRoute role="teacher" />}>
          <Route path="/teacher" element={<TeacherLayout />}>
            <Route index element={<TeacherDashboard />} />
            <Route path="schedule" element={<TeacherSchedulePage />} />
            <Route path="attendance/manual" element={<ManualAttendancePage />} />
            <Route path="attendance/recognition" element={<RecognitionAttendancePage />} />
            <Route path="reports" element={<ReportsPage />} />
            <Route path="announcements" element={<AnnouncementsPage />} />
            <Route path="*" element={<RoleNotFoundPage role="teacher" />} />
          </Route>
        </Route>

        <Route element={<RoleRoute role="student" />}>
          <Route path="/student" element={<StudentLayout />}>
            <Route index element={<StudentDashboard />} />
            <Route path="attendance" element={<StudentAttendancePage />} />
            <Route path="announcements" element={<AnnouncementsPage />} />
            <Route path="*" element={<RoleNotFoundPage role="student" />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
