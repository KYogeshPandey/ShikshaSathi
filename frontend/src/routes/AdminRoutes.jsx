// frontend/src/routes/AdminRoutes.jsx
import { Routes, Route } from "react-router-dom";
import ProtectedRoute from "./ProtectedRoute";
import AdminDashboard from "../pages/Admin/AdminDashboard";
import AdminLayout from "../layout/AdminLayout"; // agar nahi hai to simple wrapper bana sakte ho

export default function AdminRoutes() {
  return (
    <ProtectedRoute role="admin">
      <AdminLayout>
        <Routes>
          <Route path="/" element={<AdminDashboard />} />
          {/* future admin pages yahi add karna */}
        </Routes>
      </AdminLayout>
    </ProtectedRoute>
  );
}
