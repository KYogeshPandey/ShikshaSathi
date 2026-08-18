import type { UserRole } from "../types/auth";

export interface NavigationItem {
  label: string;
  to: string;
  end?: boolean;
}

export interface RoleRouteDefinition {
  role: UserRole;
  basePath: `/${UserRole}`;
  title: string;
  navigation: readonly NavigationItem[];
}

export const roleRouteDefinitions = {
  admin: {
    role: "admin",
    basePath: "/admin",
    title: "Administration workspace",
    navigation: [
      { label: "Overview", to: "/admin", end: true },
      { label: "Classrooms", to: "/admin/classrooms" },
      { label: "Subjects", to: "/admin/subjects" },
      { label: "Teachers", to: "/admin/teachers" },
      { label: "Students", to: "/admin/students" },
      { label: "Assignments", to: "/admin/assignments" },
      { label: "Timetable", to: "/admin/timetable" },
      { label: "Announcements", to: "/admin/announcements" },
      { label: "Bulk imports", to: "/admin/imports" },
      { label: "Reports", to: "/admin/reports" },
    ],
  },
  teacher: {
    role: "teacher",
    basePath: "/teacher",
    title: "Teacher workspace",
    navigation: [
      { label: "Overview", to: "/teacher", end: true },
      { label: "Classes & timetable", to: "/teacher/schedule" },
      { label: "Manual attendance", to: "/teacher/attendance/manual" },
      { label: "Recognition", to: "/teacher/attendance/recognition" },
      { label: "Reports", to: "/teacher/reports" },
      { label: "Announcements", to: "/teacher/announcements" },
    ],
  },
  student: {
    role: "student",
    basePath: "/student",
    title: "Student portal",
    navigation: [
      { label: "Overview", to: "/student", end: true },
      { label: "My attendance", to: "/student/attendance" },
      { label: "Announcements", to: "/student/announcements" },
    ],
  },
} satisfies Record<UserRole, RoleRouteDefinition>;

export function homePathForRole(role: UserRole): `/${UserRole}` {
  return roleRouteDefinitions[role].basePath;
}
