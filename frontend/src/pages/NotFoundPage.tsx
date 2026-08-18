import { Link } from "react-router-dom";
import { useAuth } from "../auth/authContext";
import { homePathForRole } from "../routes/config";

export function NotFoundPage() {
  const { user } = useAuth();
  const destination = user ? homePathForRole(user.role) : "/login";

  return (
    <main className="centered-page">
      <section className="status-card">
        <p className="eyebrow">404</p>
        <h1>That page does not exist.</h1>
        <Link className="button button--primary" to={destination}>
          Return to ShikshaSathi
        </Link>
      </section>
    </main>
  );
}
