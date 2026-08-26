import type { ReactNode } from "react";

export type AppIconName =
  | "announcements"
  | "assignments"
  | "attendance"
  | "calendar"
  | "classrooms"
  | "dashboard"
  | "imports"
  | "recognition"
  | "recovery"
  | "reports"
  | "shield"
  | "students"
  | "subjects"
  | "teachers";

interface AppIconProps {
  className?: string;
  name: AppIconName;
  size?: number;
}

export function AppIcon({ className = "", name, size = 19 }: AppIconProps) {
  const paths: Record<AppIconName, ReactNode> = {
    announcements: (
      <>
        <path d="M3 11v2a2 2 0 0 0 2 2h2l4 4V5L7 9H5a2 2 0 0 0-2 2Z" />
        <path d="M15 9a4 4 0 0 1 0 6M18 6a8 8 0 0 1 0 12" />
      </>
    ),
    assignments: (
      <>
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z" />
        <path d="m9 9 2 2 4-4" />
      </>
    ),
    attendance: (
      <>
        <rect x="4" y="4" width="16" height="17" rx="2" />
        <path d="M9 4V2h6v2M8 10h8M8 15l2 2 5-5" />
      </>
    ),
    calendar: (
      <>
        <rect x="3" y="5" width="18" height="16" rx="2" />
        <path d="M16 3v4M8 3v4M3 11h18M8 15h2M14 15h2" />
      </>
    ),
    classrooms: (
      <>
        <path d="M3 21h18M5 21V7l7-4 7 4v14" />
        <path d="M9 21v-5h6v5M8 10h2M14 10h2" />
      </>
    ),
    dashboard: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </>
    ),
    imports: (
      <>
        <path d="M12 16V4M7 9l5-5 5 5" />
        <path d="M5 14v6h14v-6" />
      </>
    ),
    recognition: (
      <>
        <path d="M4 8V4h4M16 4h4v4M20 16v4h-4M8 20H4v-4" />
        <circle cx="12" cy="10" r="3" />
        <path d="M7.5 17a5.5 5.5 0 0 1 9 0" />
      </>
    ),
    recovery: (
      <>
        <path d="M3 18 9 12l4 4 8-10" />
        <path d="M15 6h6v6" />
      </>
    ),
    reports: (
      <>
        <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
      </>
    ),
    shield: (
      <>
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" />
        <path d="m9 12 2 2 4-4" />
      </>
    ),
    students: (
      <>
        <path d="m2 10 10-5 10 5-10 5Z" />
        <path d="M6 12v5c3 2 9 2 12 0v-5M22 10v6" />
      </>
    ),
    subjects: (
      <>
        <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H11v17H6.5A2.5 2.5 0 0 0 4 22Z" />
        <path d="M20 5.5A2.5 2.5 0 0 0 17.5 3H13v17h4.5A2.5 2.5 0 0 1 20 22Z" />
      </>
    ),
    teachers: (
      <>
        <circle cx="9" cy="8" r="4" />
        <path d="M3 21v-2a6 6 0 0 1 12 0v2M16 5h5v9h-3" />
      </>
    ),
  };

  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="none"
      height={size}
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.8"
      viewBox="0 0 24 24"
      width={size}
    >
      {paths[name]}
    </svg>
  );
}
