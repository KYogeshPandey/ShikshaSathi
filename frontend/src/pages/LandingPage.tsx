import { useEffect, useRef, useState, type ReactNode } from "react";
import "./landing-page.css";

type IconName =
  | "arrow"
  | "users"
  | "calendar"
  | "chart"
  | "clipboard"
  | "book"
  | "graduation"
  | "check"
  | "download"
  | "shield"
  | "menu"
  | "close";

function Icon({
  name,
  size = 20,
  className = "",
}: {
  name: IconName;
  size?: number;
  className?: string;
}) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.9,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    className,
  };

  const paths: Record<IconName, ReactNode> = {
    arrow: <><path d="M5 12h14" /><path d="m13 6 6 6-6 6" /></>,
    users: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 11h18" /><path d="m9 16 2 2 4-4" /></>,
    chart: <><path d="M3 3v18h18" /><path d="M7 16v-5M12 16V8M17 16V5" /></>,
    clipboard: <><rect x="5" y="4" width="14" height="17" rx="2" /><path d="M9 4.5V3h6v1.5" /><path d="M9 10h6M9 14h6M9 18h4" /></>,
    book: <><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H11v17H6.5A2.5 2.5 0 0 0 4 22Z" /><path d="M20 5.5A2.5 2.5 0 0 0 17.5 3H13v17h4.5A2.5 2.5 0 0 1 20 22Z" /></>,
    graduation: <><path d="m2 10 10-5 10 5-10 5Z" /><path d="M6 12v5c3 2 9 2 12 0v-5" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    download: <><path d="M12 3v12" /><path d="m7 10 5 5 5-5" /><path d="M5 21h14" /></>,
    shield: <><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" /><path d="m9 12 2 2 4-4" /></>,
    menu: <><path d="M4 7h16M4 12h16M4 17h16" /></>,
    close: <><path d="m6 6 12 12M18 6 6 18" /></>,
  };

  return <svg {...common}>{paths[name]}</svg>;
}

const navItems = [
  ["Features", "features"],
  ["Roles", "roles"],
  ["Attendance", "attendance"],
  ["Reports", "reports"],
  ["Technology", "technology"],
] as const;

const features = [
  {
    icon: "users" as const,
    title: "Academic records",
    text: "Manage classrooms, subjects, teachers, students, assignments, and timetables in one connected workspace.",
  },
  {
    icon: "calendar" as const,
    title: "Attendance",
    text: "Record daily attendance, review absences, and keep classroom activity aligned with the school schedule.",
  },
  {
    icon: "chart" as const,
    title: "Reports and exports",
    text: "Review attendance patterns, identify defaulters, and export clear CSV or PDF reports for your team.",
  },
];

const roles = [
  {
    label: "Administrator",
    title: "Run the school with confidence.",
    text: "Manage academics, people, schedules, announcements, imports, and reports from a structured command centre.",
    icon: "clipboard" as const,
  },
  {
    label: "Teacher",
    title: "Keep classroom work moving.",
    text: "See assigned classrooms, follow the timetable, record attendance, and access relevant student records.",
    icon: "book" as const,
  },
  {
    label: "Student",
    title: "Make the school day visible.",
    text: "View attendance, schedules, announcements, and a personal academic view without the noise.",
    icon: "graduation" as const,
  },
];

function Logo() {
  return (
    <a href="#top" className="ss-logo" aria-label="ShikshaSathi home">
      <span className="ss-logo-mark">S</span>
      <span className="ss-logo-text">
        Shiksha<span>Sathi</span>
      </span>
    </a>
  );
}

function DashboardPreview() {
  return (
    <div className="ss-dashboard-wrap" aria-hidden="true">
      <div className="ss-dashboard">
        <div className="ss-dashboard-top">
          <div className="ss-dashboard-brand">
            <span />
            <strong>ShikshaSathi</strong>
          </div>
          <div className="ss-dashboard-labels">
            <span className="ss-badge">Admin workspace</span>
            <small>Illustrative preview</small>
          </div>
        </div>

        <div className="ss-dashboard-body">
          <aside className="ss-dashboard-sidebar">
            <p>Admin access</p>
            {["Overview", "Classrooms", "Teachers", "Timetable", "Reports"].map(
              (item, index) => (
                <span className={index === 0 ? "active" : ""} key={item}>
                  {item}
                </span>
              ),
            )}
          </aside>

          <div className="ss-dashboard-content">
            <p className="ss-dashboard-kicker">Admin overview</p>
            <h3>
              Administration
              <br />
              workspace
            </h3>
            <p className="ss-dashboard-copy">
              Manage academic records, assignments, schedules, announcements,
              and validated bulk imports.
            </p>

            <div className="ss-metric-grid">
              <div className="ss-metric-card">
                <small>Attendance today</small>
                <strong>94.8%</strong>
                <div className="ss-progress">
                  <span />
                </div>
              </div>
              <div className="ss-metric-card">
                <small>Active classes</small>
                <strong>24</strong>
                <em>+3 this term</em>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function LandingPage() {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
        menuButtonRef.current?.focus();
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [menuOpen]);

  return (
    <div id="top" className="ss-landing">
      <nav className="ss-nav" aria-label="Primary navigation">
        <div className="ss-container ss-nav-inner">
          <Logo />

          <div className="ss-nav-links">
            {navItems.map(([label, id]) => (
              <a key={id} href={`#${id}`}>
                {label}
              </a>
            ))}
          </div>

          <div className="ss-nav-actions">
            <a href="/login" className="ss-text-link">
              Sign In
            </a>
            <a href="/login" className="ss-button ss-button-primary">
              Open ShikshaSathi <Icon name="arrow" size={17} />
            </a>
          </div>

          <button
            ref={menuButtonRef}
            type="button"
            className="ss-menu-button"
            aria-expanded={menuOpen}
            aria-controls="ss-mobile-menu"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            onClick={() => setMenuOpen((current) => !current)}
          >
            <Icon name={menuOpen ? "close" : "menu"} size={22} />
          </button>
        </div>

        {menuOpen && (
          <div id="ss-mobile-menu" className="ss-mobile-menu">
            <div className="ss-container">
              {navItems.map(([label, id]) => (
                <a
                  key={id}
                  href={`#${id}`}
                  onClick={() => setMenuOpen(false)}
                >
                  {label}
                </a>
              ))}
              <a
                href="/login"
                className="ss-button ss-button-primary"
                onClick={() => setMenuOpen(false)}
              >
                Open ShikshaSathi
              </a>
            </div>
          </div>
        )}
      </nav>

      <main>
      <section className="ss-container ss-hero">
        <div className="ss-hero-copy">
          <p className="ss-eyebrow">School administration, made practical</p>
          <h1>One workspace for smarter school operations.</h1>
          <p className="ss-lead">
            Manage academics, attendance, schedules, communication, and
            reporting from one secure role-based platform.
          </p>

          <div className="ss-hero-actions">
            <a href="/login" className="ss-button ss-button-primary">
              Open ShikshaSathi <Icon name="arrow" size={17} />
            </a>
            <a href="#features" className="ss-button ss-button-secondary">
              Explore Features
            </a>
          </div>

          <div className="ss-proof">
            <span>
              <Icon name="check" size={16} />
              Role-based access
            </span>
            <span>
              <Icon name="check" size={16} />
              Built for everyday school work
            </span>
          </div>
        </div>

        <DashboardPreview />
      </section>

      <section className="ss-section ss-section-white">
        <div className="ss-container">
          <div className="ss-section-intro">
            <p className="ss-eyebrow">One connected system</p>
            <h2>Everything your school team needs to stay in sync.</h2>
            <p>
              Centralize the work behind a well-run school, without adding
              complexity to the school day.
            </p>
          </div>

          <div id="features" className="ss-feature-grid">
            {features.map((feature) => (
              <article key={feature.title} className="ss-feature-card">
                <span className="ss-icon-box ss-icon-box-soft">
                  <Icon name={feature.icon} />
                </span>
                <h3>{feature.title}</h3>
                <p>{feature.text}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section id="roles" className="ss-section">
        <div className="ss-container ss-role-layout">
          <div className="ss-section-intro">
            <p className="ss-eyebrow">Role-based workspaces</p>
            <h2>The right view for every person.</h2>
            <p>
              Keep responsibilities clear while giving the whole school one
              shared source of truth.
            </p>
          </div>

          <div className="ss-role-list">
            {roles.map((role) => (
              <article key={role.label} className="ss-role-row">
                <span className="ss-icon-box ss-icon-box-navy">
                  <Icon name={role.icon} />
                </span>
                <div>
                  <p className="ss-role-label">{role.label}</p>
                  <h3>{role.title}</h3>
                  <p>{role.text}</p>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section id="attendance" className="ss-section ss-section-muted">
        <div className="ss-container">
          <div className="ss-section-intro">
            <p className="ss-eyebrow">Attendance workflow</p>
            <h2>From classroom activity to a report you can trust.</h2>
          </div>

          <div className="ss-workflow">
            {["Classroom", "Teacher", "Attendance", "Validation", "Reports"].map(
              (item, index) => (
                <div className="ss-workflow-step" key={item}>
                  <div className="ss-workflow-card">
                    <span>{index + 1}</span>
                    <strong>{item}</strong>
                  </div>
                  {index < 4 && (
                    <Icon name="arrow" size={18} className="ss-workflow-arrow" />
                  )}
                </div>
              ),
            )}
          </div>
        </div>
      </section>

      <section id="reports" className="ss-section">
        <div className="ss-container ss-report-layout">
          <div className="ss-section-intro">
            <p className="ss-eyebrow">Reports and analytics</p>
            <h2>See the patterns behind the numbers.</h2>
            <p>
              Monitor attendance rate, students present, defaulters, and trends.
              Export the view your school needs as CSV or PDF.
            </p>

            <div className="ss-export-tags">
              <span>
                <Icon name="download" size={17} /> CSV export
              </span>
              <span>
                <Icon name="download" size={17} /> PDF export
              </span>
            </div>
          </div>

          <div className="ss-report-card">
            <p className="ss-preview-label">Illustrative preview</p>

            <div className="ss-report-head">
              <div>
                <small>Attendance rate</small>
                <strong>94.8%</strong>
              </div>
              <span>+2.4%</span>
            </div>

            <div className="ss-chart" aria-hidden="true">
              {[58, 72, 64, 83, 76, 92, 88].map((height, index) => (
                <div className="ss-bar-column" key={index}>
                  <span style={{ height: `${height}%` }} />
                  <small>{["M", "T", "W", "T", "F", "S", "S"][index]}</small>
                </div>
              ))}
            </div>

            <div className="ss-report-stats">
              <div>
                <small>Present</small>
                <strong>1,284</strong>
              </div>
              <div>
                <small>Defaulters</small>
                <strong>28</strong>
              </div>
              <div>
                <small>This week</small>
                <strong className="positive">On track</strong>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="ss-section ss-section-white">
        <div className="ss-container ss-toolkit">
          <div className="ss-section-intro">
            <p className="ss-eyebrow">Administration toolkit</p>
            <h2>Practical tools for the work behind learning.</h2>
          </div>

          <div className="ss-tool-grid">
            {[
              "Classrooms",
              "Subjects",
              "Teachers",
              "Students",
              "Assignments",
              "Timetable",
              "Bulk imports",
              "Announcements",
            ].map((item) => (
              <span key={item}>
                <Icon name="check" size={16} />
                {item}
              </span>
            ))}
          </div>
        </div>
      </section>

      <section id="technology" className="ss-section">
        <div className="ss-container ss-tech-layout">
          <div className="ss-section-intro">
            <p className="ss-eyebrow">Security and technology</p>
            <h2>A dependable foundation for school data.</h2>
          </div>

          <div className="ss-tech-grid">
            <article className="ss-tech-card">
              <Icon name="shield" size={26} />
              <h3>Thoughtful by design</h3>
              <p>
                Role-Based Access Control, JWT authentication, audit-aware
                attendance workflows, and secure environment configuration.
              </p>
            </article>
            <article className="ss-tech-card">
              <p className="ss-tech-label">Technology</p>
              <p>
                React · TypeScript · FastAPI · PostgreSQL · Docker · Vercel ·
                Render · Neon
              </p>
            </article>
          </div>
        </div>
      </section>

      <section className="ss-section">
        <div className="ss-container">
          <div className="ss-final-cta">
            <p className="ss-eyebrow">Take the next step</p>
            <h2>Bring your school operations into one workspace.</h2>
            <p>
              Give your team a clearer way to manage the school day and support
              every learner.
            </p>
            <a href="/login" className="ss-button ss-button-primary">
              Open ShikshaSathi <Icon name="arrow" size={17} />
            </a>
          </div>
        </div>
      </section>

      </main>

      <footer className="ss-footer">
        <div className="ss-container ss-footer-inner">
          <Logo />
          <div className="ss-footer-links">
            <a href="#features">Features</a>
            <a href="#technology">Technology</a>
            <a
              href="https://github.com/KYogeshPandey/ShikshaSathi"
              target="_blank"
              rel="noreferrer"
            >
              GitHub
            </a>
            <a href="/login">Sign In</a>
          </div>
          <p>© 2026 ShikshaSathi</p>
        </div>
      </footer>
    </div>
  );
}
