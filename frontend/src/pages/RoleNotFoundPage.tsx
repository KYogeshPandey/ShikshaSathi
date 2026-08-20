import { Link } from "react-router-dom";
import type { UserRole } from "../types/auth";
import { homePathForRole } from "../routes/config";

interface RoleNotFoundPageProps {
  role: UserRole;
}

export function RoleNotFoundPage({ role }: RoleNotFoundPageProps) {
  return (
    <section className="content-card page-stack">
      <p className="eyebrow">Route unavailable</p>
      <h1>Page not available</h1>
      <p>This page is not available in your current workspace.</p>
      <Link className="text-link" to={homePathForRole(role)}>
        Return to overview
      </Link>
    </section>
  );
}
