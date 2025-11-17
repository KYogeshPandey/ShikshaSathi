// frontend/src/App.jsx
import React, { useState } from "react";
import AdminDashboard from "./pages/Admin/AdminDashboard";
import TeacherDashboard from "./pages/Teacher/TeacherDashboard";
import StudentDashboard from "./pages/Student/StudentDashboard";
import Login from "./pages/Auth/LoginPage";

function App() {
  const [token, setToken] = useState(localStorage.getItem("erpToken") || "");
  const [role, setRole] = useState(localStorage.getItem("erpRole") || "");
  const [userName, setUserName] = useState(
    localStorage.getItem("erpUserName") || "",
  );

  const handleSetUserName = (uname) => {
    setUserName(uname);
    localStorage.setItem("erpUserName", uname);
  };

  const handleSetToken = (newToken) => {
    setToken(newToken);
    localStorage.setItem("erpToken", newToken);
    // also keep generic token for axios interceptor
    localStorage.setItem("token", newToken);
  };

  const handleSetRole = (newRole) => {
    setRole(newRole);
    localStorage.setItem("erpRole", newRole);
  };

  const handleLogout = () => {
    setToken("");
    setRole("");
    setUserName("");
    localStorage.removeItem("erpToken");
    localStorage.removeItem("erpRole");
    localStorage.removeItem("erpUserName");
    localStorage.removeItem("token");
  };

  // Not logged in → show login shell
  if (!token) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center px-4">
        <div className="bg-white/95 rounded-2xl shadow-2xl w-full max-w-md p-1">
          <div className="bg-gradient-to-r from-indigo-600 to-blue-500 rounded-xl px-6 py-4 text-white text-center mb-3">
            <h1 className="text-2xl font-bold tracking-wide">
              🎓 ShikshaSathi ERP
            </h1>
            <p className="text-xs mt-1 text-indigo-100">
              Smart attendance & analytics for Admin, Teachers and Students
            </p>
          </div>
          <div className="px-4 pb-5">
            <Login
              setToken={handleSetToken}
              setRole={handleSetRole}
              setUserName={handleSetUserName}
            />
          </div>
        </div>
      </div>
    );
  }

  // Routing by role
  let dashboard = null;
  if (role === "admin") dashboard = <AdminDashboard token={token} />;
  else if (role === "teacher") dashboard = <TeacherDashboard token={token} />;
  else if (role === "student") dashboard = <StudentDashboard token={token} />;
  else
    dashboard = (
      <div className="p-6 text-center text-red-500 font-semibold">
        Unknown role: {role}
      </div>
    );

  return (
    <div className="min-h-screen bg-slate-100 flex flex-col">
      {/* App header */}
      <header className="bg-gradient-to-r from-indigo-700 via-indigo-600 to-blue-600 py-4 shadow-lg relative">
        <div className="max-w-6xl mx-auto px-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl md:text-3xl font-extrabold text-white tracking-tight">
              ShikshaSathi ERP
            </h1>
            <p className="text-xs md:text-sm text-indigo-100">
              {role === "admin"
                ? "Admin · Full institute control & analytics"
                : role === "teacher"
                ? "Teacher · Class management & attendance"
                : role === "student"
                ? "Student · Personal attendance dashboard"
                : "Unified ERP dashboard"}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="text-right hidden sm:block">
              <div className="text-xs text-indigo-100 uppercase tracking-wide">
                Logged in as
              </div>
              <div className="text-sm font-semibold text-white">
                {userName || "Unknown"}
              </div>
              <div className="text-[10px] text-indigo-200">
                Role: {role || "N/A"}
              </div>
            </div>
            <button
              className="bg-red-500 hover:bg-red-600 text-white text-xs md:text-sm font-semibold px-3 py-1.5 rounded-full shadow-md transition"
              onClick={handleLogout}
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      {/* Dashboard content */}
      <main className="flex-1 max-w-6xl mx-auto w-full">{dashboard}</main>

      {/* Footer strip */}
      <footer className="mt-4 py-3 text-center text-[11px] text-slate-500">
        © {new Date().getFullYear()} ShikshaSathi · Built for smart attendance
        & student engagement.
      </footer>
    </div>
  );
}

export default App;
