import { Link } from "react-router-dom";
import { useAuth } from "../auth/authContext";
import { homePathForRole } from "../routes/config";

export function UnauthorizedPage() {
  const { user } = useAuth();
  const destination = user ? homePathForRole(user.role) : "/login";

  return (
    <main className="centered-page">
      <section className="status-card">
        <p className="eyebrow">Access blocked</p>
        <h1>This workspace is assigned to another role.</h1>
        <p>Your account is signed in, but it cannot open the requested role area.</p>
        <Link className="button button--primary" to={destination}>
          Go to my workspace
        </Link>
      </section>
    </main>
  );
}
