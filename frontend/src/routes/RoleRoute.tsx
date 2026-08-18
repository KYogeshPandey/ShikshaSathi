import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../auth/authContext";
import type { UserRole } from "../types/auth";

interface RoleRouteProps {
  role: UserRole;
}

export function RoleRoute({ role }: RoleRouteProps) {
  const { user } = useAuth();

  if (!user) {
    return <Navigate to="/login" replace />;
  }
  if (user.role !== role) {
    return <Navigate to="/unauthorized" replace />;
  }
  return <Outlet />;
}
