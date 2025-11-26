import React from "react";
import { NavLink } from "react-router-dom";
import { 
  LayoutDashboard, Users, GraduationCap, BookOpen, 
  CalendarCheck, FileSpreadsheet, LogOut, UploadCloud 
} from "lucide-react";
import { useAuth } from "../../context/AuthContext";

const NAV_ITEMS = [
  { label: "Dashboard", path: "/admin", icon: <LayoutDashboard size={20} /> },
  { label: "Students", path: "/admin/students", icon: <GraduationCap size={20} /> },
  { label: "Teachers", path: "/admin/teachers", icon: <Users size={20} /> },
  { label: "Classes", path: "/admin/classrooms", icon: <BookOpen size={20} /> },
  { label: "Subjects", path: "/admin/subjects", icon: <BookOpen size={20} /> },
  { label: "Attendance", path: "/admin/attendance", icon: <CalendarCheck size={20} /> },
  { label: "Bulk Import", path: "/admin/bulk-import", icon: <UploadCloud size={20} /> },
  { label: "Audit Logs", path: "/admin/audit-logs", icon: <FileSpreadsheet size={20} /> },
];

export default function Sidebar({ isOpen, onClose }) {
  const { logout } = useAuth();

  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-40 lg:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={`fixed top-0 left-0 h-full w-64 bg-white border-r border-slate-200 shadow-sm z-50 transform transition-transform duration-300
          ${isOpen ? "translate-x-0" : "-translate-x-full"} lg:translate-x-0`}
      >
        <div className="h-16 flex items-center px-6 border-b border-slate-100">
          <span className="text-xl font-bold text-indigo-600 flex items-center gap-2">
            🎓 <span>ShikshaSathi</span>
          </span>
        </div>
        <nav className="p-4 space-y-1">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              onClick={() => window.innerWidth < 1024 && onClose()}
              end={item.path === "/admin"}
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
        <div className="absolute bottom-0 w-full p-4 border-t border-slate-100">
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
