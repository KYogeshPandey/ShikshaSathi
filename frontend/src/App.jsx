import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import AdminRoutes from "./routes/AdminRoutes";
import TeacherRoutes from "./routes/TeacherRoutes";
import StudentRoutes from "./routes/StudentRoutes";
import Login from "./pages/Auth/LoginPage";
import ProtectedRoute from "./routes/ProtectedRoute";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public Routes */}
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<Navigate to="/login" />} />

        {/* Role Based Routes with Protection */}
        
        {/* Admin Section */}
        <Route 
          path="/admin/*" 
          element={
            <ProtectedRoute role="admin">
              <AdminRoutes />
            </ProtectedRoute>
          } 
        />

        {/* Teacher Section */}
        <Route 
          path="/teacher/*" 
          element={
            <ProtectedRoute role="teacher">
              <TeacherRoutes />
            </ProtectedRoute>
          } 
        />

        {/* Student Section */}
        <Route 
          path="/student/*" 
          element={
            <ProtectedRoute role="student">
              <StudentRoutes />
            </ProtectedRoute>
          } 
        />

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/login" />} />
      </Routes>
    </BrowserRouter>
  );
}
