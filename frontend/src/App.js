import React, { useState } from "react";
import Login from './components/Login';
import Students from './components/Students';
import Teachers from './components/Teachers';
import Attendance from './components/Attendance';
import Classrooms from './components/Classrooms';

function App() {
  const [token, setToken] = useState(localStorage.getItem('erpToken') || '');

  const handleSetToken = (newToken) => {
    setToken(newToken);
    localStorage.setItem('erpToken', newToken);
  };

  const handleLogout = () => {
    setToken('');
    localStorage.removeItem('erpToken');
  };

  if (!token) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-100">
        <div className="bg-white p-8 rounded-lg shadow-md w-full max-w-sm">
          <h1 className="text-3xl font-bold text-blue-700 mb-4 text-center">ERP Login</h1>
          <Login setToken={handleSetToken} />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-100">
      <header className="bg-blue-700 py-6 shadow">
        <h1 className="text-4xl font-bold text-white text-center tracking-wider">ERP Dashboard</h1>
        <button
          className="absolute top-5 right-6 bg-red-600 text-white rounded px-4 py-1 hover:bg-red-700 transition-all"
          onClick={handleLogout}
        >
          Logout
        </button>
      </header>
      <main className="flex flex-col md:flex-row md:space-x-8 justify-center p-8 max-w-6xl mx-auto">
        <div className="md:w-1/2 mb-8 md:mb-0">
          <section className="bg-white rounded-lg shadow-md p-6 mb-8">
            <Students token={token} onLogout={handleLogout} />
          </section>
          <section className="bg-white rounded-lg shadow-md p-6 mt-8">
            <Teachers token={token} onLogout={handleLogout} />
          </section>
        </div>
        <div className="md:w-1/2">
          <section className="bg-white rounded-lg shadow-md p-6 mb-8">
            <Classrooms token={token} onLogout={handleLogout} />
          </section>
          <section className="bg-white rounded-lg shadow-md p-6 mt-8">
            <Attendance token={token} onLogout={handleLogout} />
          </section>
        </div>
      </main>
    </div>
  );
}

export default App;
