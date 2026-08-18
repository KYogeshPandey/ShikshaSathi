import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/authContext";
import { LoadingScreen } from "../components/LoadingScreen";

export function AuthenticatedRoute() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return <LoadingScreen />;
  }
  if (status === "unauthenticated") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}
