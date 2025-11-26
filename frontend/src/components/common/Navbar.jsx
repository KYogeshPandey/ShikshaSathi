import React from "react";
import { Menu, Bell, User } from "lucide-react";
import { useAuth } from "../../context/AuthContext"; // <-- Fix here

export default function Navbar({ onMenuClick }) {
  const { user, logout } = useAuth(); // Context from AuthProvider

  return (
    <header className="h-16 bg-white border-b border-slate-200 flex items-center justify-between px-4 md:px-6 sticky top-0 z-30">
      {/* Left: Mobile Toggle & Title */}
      <div className="flex items-center gap-4">
        <button
          onClick={onMenuClick}
          className="p-2 text-slate-600 hover:bg-slate-100 rounded-lg lg:hidden"
        >
          <Menu size={24} />
        </button>
        <h2 className="text-lg font-semibold text-slate-800 hidden sm:block">
          Admin Dashboard
        </h2>
      </div>

      {/* Right: Profile & Actions */}
      <div className="flex items-center gap-4">
        <button className="p-2 text-slate-500 hover:bg-slate-100 rounded-full relative">
          <Bell size={20} />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full border border-white"></span>
        </button>
        <div className="flex items-center gap-3 pl-4 border-l border-slate-200">
          <div className="text-right hidden md:block">
            <p className="text-sm font-medium text-slate-700">{user?.username || "Admin"}</p>
            <p className="text-xs text-slate-500 capitalize">{user?.role || "Administrator"}</p>
          </div>
          <div className="h-10 w-10 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-600 border border-indigo-200">
            <User size={20} />
          </div>
          <button
            className="ml-4 px-3 py-1 bg-red-100 text-red-700 rounded text-xs font-bold hover:bg-red-200"
            onClick={logout}
            title="Logout"
          >
            Logout
          </button>
        </div>
      </div>
    </header>
  );
}
