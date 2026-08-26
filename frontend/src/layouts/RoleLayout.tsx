import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/authContext";
import { AppIcon, type AppIconName } from "../components/AppIcon";
import type { RoleRouteDefinition } from "../routes/config";

interface RoleLayoutProps {
  definition: RoleRouteDefinition;
}

const navigationIcons: Record<string, AppIconName> = {
  Announcements: "announcements",
  Assignments: "assignments",
  "Bulk imports": "imports",
  Classrooms: "classrooms",
  "Classes & timetable": "calendar",
  "Manual attendance": "attendance",
  "My attendance": "attendance",
  Overview: "dashboard",
  Recognition: "recognition",
  "Recovery planner": "recovery",
  Reports: "reports",
  Students: "students",
  Subjects: "subjects",
  Teachers: "teachers",
  Timetable: "calendar",
  "Weekly timetable": "calendar",
};

const workspaceLabels = {
  admin: "Admin workspace",
  student: "Student portal",
  teacher: "Teacher workspace",
} as const;

function initials(name?: string): string {
  const parts = name?.trim().split(/\s+/).filter(Boolean) ?? [];
  if (!parts.length) return "SS";
  return `${parts[0][0] ?? ""}${parts.length > 1 ? parts.at(-1)?.[0] ?? "" : ""}`.toUpperCase();
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
          <p className="eyebrow sidebar-eyebrow">{workspaceLabels[definition.role]}</p>
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
                <AppIcon className="role-nav-icon" name={navigationIcons[item.label] ?? "dashboard"} />
                <span>{item.label}</span>
              </NavLink>
            ))}
          </nav>
        </div>
        <div className="sidebar-assurance">
          <AppIcon name="shield" size={17} />
          <div>
            <strong>Protected workspace</strong>
            <span>Role-scoped access</span>
          </div>
        </div>
      </aside>

      <div className="shell-content">
        <header className="topbar">
          <div>
            <p className="eyebrow">ShikshaSathi</p>
            <p className="workspace-title">{definition.title}</p>
          </div>
          <div className="identity-actions">
            <span className="identity-avatar" aria-hidden="true">{initials(user?.full_name)}</span>
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
