import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/authContext";
import type { RoleRouteDefinition } from "../routes/config";

interface RoleLayoutProps {
  definition: RoleRouteDefinition;
}

export function RoleLayout({ definition }: RoleLayoutProps) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  const handleLogout = async () => {
    setIsLoggingOut(true);
    try {
      await logout();
    } finally {
      navigate("/login", { replace: true });
    }
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div>
          <a className="brand brand--inverse" href={definition.basePath}>
            <span className="brand-mark" aria-hidden="true">S</span>
            <span>ShikshaSathi</span>
          </a>
          <p className="eyebrow sidebar-eyebrow">{definition.role} access</p>
          <nav aria-label={`${definition.role} navigation`} className="role-navigation">
            {definition.navigation.map((item) => (
              <NavLink
                key={item.to}
                className={({ isActive }) =>
                  isActive ? "role-nav-link role-nav-link--active" : "role-nav-link"
                }
                end={item.end}
                to={item.to}
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
        <p className="workspace-label">Secure school workspace</p>
      </aside>

      <div className="shell-content">
        <header className="topbar">
          <div>
            <p className="eyebrow">ShikshaSathi</p>
            <p className="workspace-title">{definition.title}</p>
          </div>
          <div className="identity-actions">
            <div className="identity">
              <span className="identity-name">{user?.full_name}</span>
              <span className="identity-email">{user?.email}</span>
            </div>
            <button
              className="button button--quiet"
              disabled={isLoggingOut}
              onClick={handleLogout}
              type="button"
            >
              {isLoggingOut ? "Signing out…" : "Sign out"}
            </button>
          </div>
        </header>

        <main className="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
