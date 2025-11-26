import React, { useState, useEffect, useCallback } from "react";
import { api } from "../../api/api";

const EVENT_COLORS = {
  update: "bg-blue-100 text-blue-700",
  delete: "bg-red-100 text-red-700",
  create: "bg-green-100 text-green-700",
  login: "bg-yellow-100 text-yellow-700",
};

export default function AuditLogPage() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState("");
  const [entityType, setEntityType] = useState("");
  const [eventType, setEventType] = useState("");
  const [userId, setUserId] = useState("");
  const [error, setError] = useState("");
  const [limit, setLimit] = useState(100);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = {
        user_id: userId || undefined,
        event_type: eventType || undefined,
        entity_type: entityType || undefined,
        limit,
      };
      const res = await api.get("/logs/", { params });
      let data = res.data.data || [];
      if (q) {
        const ql = q.trim().toLowerCase();
        data = data.filter(
          (log) =>
            (log.event_type || "").toLowerCase().includes(ql) ||
            (log.entity_type || "").toLowerCase().includes(ql) ||
            (log.user_id || "").toLowerCase().includes(ql) ||
            (log.description || "").toLowerCase().includes(ql)
        );
      }
      setLogs(data);
    } catch (err) {
      setError("Failed to fetch logs.");
    } finally {
      setLoading(false);
    }
  }, [q, entityType, eventType, userId, limit]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-indigo-50 to-slate-100 p-6">
      <div className="max-w-4xl mx-auto">
        <div className="text-2xl font-bold text-slate-700 mb-6">Audit Log (Admin)</div>
        <div className="flex flex-wrap items-end gap-2 mb-4">
          <input
            type="text"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search by event/desc/entity/user"
            className="border border-slate-300 rounded px-2 py-1 text-xs"
          />
          <select
            value={eventType}
            onChange={e => setEventType(e.target.value)}
            className="border border-slate-300 rounded px-1.5 py-1 text-xs"
          >
            <option value="">All Events</option>
            <option value="create">Create</option>
            <option value="update">Update</option>
            <option value="delete">Delete</option>
            <option value="login">Login</option>
          </select>
          <select
            value={entityType}
            onChange={e => setEntityType(e.target.value)}
            className="border border-slate-300 rounded px-1.5 py-1 text-xs"
          >
            <option value="">All Entities</option>
            <option value="student">Student</option>
            <option value="teacher">Teacher</option>
            <option value="classroom">Classroom</option>
            <option value="attendance">Attendance</option>
            <option value="user">User</option>
          </select>
          <input
            type="text"
            value={userId}
            onChange={e => setUserId(e.target.value)}
            placeholder="User ID"
            className="border border-slate-300 rounded px-2 py-1 text-xs w-[110px]"
          />
          <select
            value={limit}
            onChange={e => setLimit(Number(e.target.value))}
            className="border border-slate-300 rounded px-1.5 py-1 text-xs"
          >
            {[20, 50, 100, 250].map(v => (
              <option key={v} value={v}>{v} rows</option>
            ))}
          </select>
          <button
            onClick={fetchLogs}
            className="bg-indigo-600 text-white px-3 py-1 rounded text-xs ml-2 hover:bg-indigo-700"
          >
            Refresh
          </button>
        </div>
        {error && (
          <div className="mb-2 text-red-600 text-xs">{error}</div>
        )}
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead>
              <tr className="bg-slate-100 text-slate-600">
                <th className="py-2 px-2">Time</th>
                <th className="py-2 px-2">Event</th>
                <th className="py-2 px-2">Entity</th>
                <th className="py-2 px-2">Entity ID</th>
                <th className="py-2 px-2">User</th>
                <th className="py-2 px-2">Description</th>
                {/* <th className="py-2 px-2">Meta</th> */}
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={7} className="py-10 text-center text-indigo-400">Loading…</td>
                </tr>
              )}
              {!loading && logs.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-8 text-slate-400 text-center">No log entries found…</td>
                </tr>
              )}
              {!loading &&
                logs.map((log, idx) => (
                  <tr key={log._id || idx} className="border-b border-slate-100">
                    <td className="py-1 px-2 whitespace-nowrap">
                      {log.created_at ? new Date(log.created_at).toLocaleString() : "-"}
                    </td>
                    <td className="py-1 px-2">
                      <span className={
                        `rounded-full px-2 py-0.5 text-xs font-bold ${EVENT_COLORS[log.event_type] || "bg-slate-100 text-slate-700"}`
                      }>
                        {log.event_type?.toUpperCase()}
                      </span>
                    </td>
                    <td className="py-1 px-2">{log.entity_type || "-"}</td>
                    <td className="py-1 px-2">{log.entity_id || "-"}</td>
                    <td className="py-1 px-2">{log.user_id || "-"}</td>
                    <td className="py-1 px-2">{log.description || "-"}</td>
                    {/* <td className="text-xs py-1 px-2">{JSON.stringify(log.meta)}</td> */}
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
        <div className="text-[11px] text-slate-400 mt-6">
          Showing latest {logs.length} logs. To view more, increase the "rows" dropdown or implement paging.
        </div>
      </div>
    </div>
  );
}
