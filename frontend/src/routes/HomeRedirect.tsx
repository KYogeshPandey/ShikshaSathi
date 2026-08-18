import { Navigate } from "react-router-dom";
import { useAuth } from "../auth/authContext";
import { LoadingScreen } from "../components/LoadingScreen";
import { homePathForRole } from "./config";

export function HomeRedirect() {
  const { status, user } = useAuth();
  if (status === "loading") return <LoadingScreen />;
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={homePathForRole(user.role)} replace />;
}
