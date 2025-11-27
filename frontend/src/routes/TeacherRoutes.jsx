import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import TeacherLayout from '../layout/TeacherLayout'; // 👈 Import Layout

// Pages
import TeacherDashboard from '../pages/Teacher/TeacherDashboard';
import AttendancePage from '../pages/Teacher/AttendancePage';
import MyClassesPage from '../pages/Teacher/MyClassesPage';
import ClassDetailsPage from '../pages/Teacher/ClassDetailsPage';
import TimetablePage from '../pages/Teacher/TimetablePage';
import AnnouncementsPage from '../pages/Teacher/AnnouncementsPage';
import TeacherReportsPage from '../pages/Teacher/TeacherReportsPage';

const TeacherRoutes = () => {
  return (
    <Routes>
      {/* Layout Wrap */}
      <Route element={<TeacherLayout />}>
        <Route path="/" element={<Navigate to="dashboard" replace />} />
        <Route path="dashboard" element={<TeacherDashboard />} />
        <Route path="classes" element={<MyClassesPage />} />
        <Route path="classes/:id" element={<ClassDetailsPage />} />
        <Route path="attendance" element={<AttendancePage />} />
        <Route path="timetable" element={<TimetablePage />} />
        <Route path="announcements" element={<AnnouncementsPage />} />
        <Route path="reports" element={<TeacherReportsPage />} />
      </Route>

      {/* Fallback */}
      <Route path="*" element={<Navigate to="dashboard" replace />} />
    </Routes>
  );
};

export default TeacherRoutes;
