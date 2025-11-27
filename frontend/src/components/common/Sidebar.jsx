import React from "react";
import { NavLink } from "react-router-dom";
import { 
  LayoutDashboard, Users, GraduationCap, BookOpen, 
  CalendarCheck, FileSpreadsheet, LogOut, UploadCloud,
  Clock, Megaphone, FileText, UserCircle
} from "lucide-react";
import { useAuth } from "../../context/AuthContext";

export default function Sidebar({ isOpen, onClose }) {
  const { user, logout } = useAuth();
  const role = user?.role || "admin"; // default to admin if undefined

  // 1. Admin Menu Items
  const ADMIN_NAV_ITEMS = [
    { label: "Dashboard", path: "/admin", icon: <LayoutDashboard size={20} /> },
    { label: "Students", path: "/admin/students", icon: <GraduationCap size={20} /> },
    { label: "Teachers", path: "/admin/teachers", icon: <Users size={20} /> },
    { label: "Classes", path: "/admin/classrooms", icon: <BookOpen size={20} /> },
    { label: "Subjects", path: "/admin/subjects", icon: <BookOpen size={20} /> },
    { label: "Attendance", path: "/admin/attendance", icon: <CalendarCheck size={20} /> },
    { label: "Bulk Import", path: "/admin/bulk-import", icon: <UploadCloud size={20} /> },
    { label: "Audit Logs", path: "/admin/audit-logs", icon: <FileSpreadsheet size={20} /> },
  ];

  // 2. Teacher Menu Items (NEW)
  const TEACHER_NAV_ITEMS = [
    { label: "Dashboard", path: "/teacher/dashboard", icon: <LayoutDashboard size={20} /> },
    { label: "My Classes", path: "/teacher/classes", icon: <UserCircle size={20} /> },
    { label: "Mark Attendance", path: "/teacher/attendance", icon: <CalendarCheck size={20} /> },
    { label: "Timetable", path: "/teacher/timetable", icon: <Clock size={20} /> },
    { label: "Notices", path: "/teacher/announcements", icon: <Megaphone size={20} /> },
    { label: "Reports", path: "/teacher/reports", icon: <FileText size={20} /> },
  ];

  const items = role === "teacher" ? TEACHER_NAV_ITEMS : ADMIN_NAV_ITEMS;

  return (
    <>
      {/* Mobile Overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-40 lg:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar Container */}
      <aside
        className={`fixed top-0 left-0 h-full w-64 bg-white border-r border-slate-200 shadow-sm z-50 transform transition-transform duration-300
          ${isOpen ? "translate-x-0" : "-translate-x-full"} lg:translate-x-0`}
      >
        {/* Header */}
        <div className="h-16 flex items-center px-6 border-b border-slate-100">
          <span className="text-xl font-bold text-indigo-600 flex items-center gap-2">
            🎓 <span>ShikshaSathi</span>
            <span className="text-xs bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full uppercase">
                {role}
            </span>
          </span>
        </div>

        {/* Menu Items */}
        <nav className="p-4 space-y-1 overflow-y-auto max-h-[calc(100vh-80px)]">
          {items.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              onClick={() => window.innerWidth < 1024 && onClose()}
              end={item.path.endsWith("dashboard") || item.path.endsWith("admin")}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-colors
                ${isActive
                  ? "bg-indigo-50 text-indigo-700"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                }`
              }
            >
              {item.icon}
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        {/* Logout Button */}
        <div className="absolute bottom-0 w-full p-4 border-t border-slate-100 bg-white">
          <button
            className="flex items-center gap-3 px-4 py-2 w-full text-sm font-medium text-red-600 hover:bg-red-50 rounded-lg transition-colors"
            onClick={logout}
          >
            <LogOut size={20} />
            <span>Logout</span>
          </button>
        </div>
      </aside>
    </>
  );
}
