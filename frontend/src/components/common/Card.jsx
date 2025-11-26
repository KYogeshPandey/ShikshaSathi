import React from "react";

export default function Card({ title, value, icon, trend, color = "indigo" }) {
  const colorClasses = {
    indigo: "bg-indigo-50 text-indigo-600",
    green: "bg-emerald-50 text-emerald-600",
    orange: "bg-orange-50 text-orange-600",
    blue: "bg-blue-50 text-blue-600",
  };

  return (
    <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-slate-500">{title}</p>
          <h3 className="text-2xl font-bold text-slate-800 mt-2">{value}</h3>
        </div>
        <div className={`p-3 rounded-lg ${colorClasses[color]}`}>
          {icon}
        </div>
      </div>
      {trend && (
        <div className="mt-4 flex items-center text-xs">
          <span className={trend > 0 ? "text-emerald-600" : "text-red-600"}>
            {trend > 0 ? "+" : ""}{trend}%
          </span>
          <span className="text-slate-400 ml-2">from last month</span>
        </div>
      )}
    </div>
  );
}
