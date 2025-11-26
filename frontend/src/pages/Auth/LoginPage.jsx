// frontend/src/pages/Auth/LoginPage.jsx
import React, { useState, useContext } from "react";
import { loginRequest } from "../../api/api";
import { useNavigate } from "react-router-dom";
import { AuthContext } from "../../context/AuthContext";

export default function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const { login } = useContext(AuthContext);

  const handleLogin = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await loginRequest({ username, password });

      const token = res.data.access_token;
      const user = res.data.user; // { role, username, ... }

      login(user, token); // context auth update

      // Redirect based on role
      if (user.role === "admin") navigate("/admin", { replace: true });
      else if (user.role === "teacher") navigate("/teacher", { replace: true });
      else if (user.role === "student") navigate("/student", { replace: true });
      else navigate("/", { replace: true });

      // Optional: can show toast "Login Successful"
    } catch (err) {
      console.error("❌ Login error:", err);

      if (err.response) {
        const errorMsg = err.response.data?.message || "Invalid credentials";
        setError(errorMsg);
      } else if (err.request) {
        setError("Server not responding. Please check backend.");
      } else {
        setError("An unexpected error occurred.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      <form
        onSubmit={handleLogin}
        className="bg-white p-8 rounded-lg shadow-lg w-96"
      >
        <h2 className="text-3xl font-bold mb-6 text-center text-indigo-700">
          🎓 ShikshaSathi
        </h2>
        <p className="text-center text-gray-600 mb-6">Login to continue</p>

        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="Username"
          className="w-full px-4 py-3 mb-4 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
          required
          autoComplete="username"
        />

        <input
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          type="password"
          placeholder="Password"
          className="w-full px-4 py-3 mb-6 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
          required
          autoComplete="current-password"
        />

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-indigo-600 text-white py-3 rounded-lg font-semibold hover:bg-indigo-700 disabled:bg-gray-400"
        >
          {loading ? "Logging in..." : "Login"}
        </button>

        {error && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-center text-red-700 font-medium text-sm">
              {error}
            </p>
          </div>
        )}

        <div className="mt-6 text-center text-xs text-gray-500">
          <p>Demo: admin1 / admin123</p>
        </div>
      </form>
    </div>
  );
}
