import React, { useState } from "react";
import Login from './components/Login';
import AnalyticsDashboard from './components/AdminDashboard';
import TeacherDashboard from './components/TeacherDashboard';   // Create these files
import StudentDashboard from './components/StudentDashboard';

function App() {
  const [token, setToken] = useState(localStorage.getItem('erpToken') || '');
  const [role, setRole] = useState(localStorage.getItem('erpRole') || '');
  const [userName, setUserName] = useState(localStorage.getItem('erpUserName') || '');

  const handleSetUserName = (uname) => {
  setUserName(uname);
  localStorage.setItem('erpUserName', uname);
  };
  const handleSetToken = (newToken) => {
    setToken(newToken);
    localStorage.setItem('erpToken', newToken);
  };
  const handleSetRole = (newRole) => {
    setRole(newRole);
    localStorage.setItem('erpRole', newRole);
  };
  const handleLogout = () => {
  setToken('');
  setRole('');
  setUserName('');
  localStorage.removeItem('erpToken');
  localStorage.removeItem('erpRole');
  localStorage.removeItem('erpUserName');
  };

  if (!token) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-100">
        <div className="bg-white p-8 rounded-lg shadow-md w-full max-w-sm">
          <h1 className="text-3xl font-bold text-blue-700 mb-4 text-center">ERP Login</h1>
          <Login setToken={handleSetToken} setRole={handleSetRole} setUserName={handleSetUserName} />
        </div>
      </div>
    );
  }

  // Routing by role!
  let dashboard = null;
  if (role === "admin") dashboard = <AnalyticsDashboard token={token} />;
  else if (role === "teacher") dashboard = <TeacherDashboard token={token} />;
  else if (role === "student") dashboard = <StudentDashboard token={token} />;
  else dashboard = <div>Unknown role: {role}</div>;

  return (
    <div className="min-h-screen bg-gray-100">
      <header className="bg-blue-700 py-6 shadow relative">
        <h1 className="text-4xl font-bold text-white text-center tracking-wider">
          {role === "admin"
            ? `Welcome Admin`
            : role === "teacher"
            ? `Welcome Teacher`
            : role === "student"
            ? `Welcome Student`
            : `ERP Dashboard`
          }
          {userName ? `, ${userName}` : ""}
        </h1>
        <button
          className="absolute top-5 right-6 bg-red-600 text-white rounded px-4 py-1 hover:bg-red-700 transition-all"
          onClick={handleLogout}
        >
          Logout
        </button>
      </header>
      {dashboard}
    </div>
  );
}

export default App;
