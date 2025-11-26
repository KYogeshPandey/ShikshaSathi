import React from "react";

export default function ClassForm({ form, onChange, onSubmit, disabled }) {
  return (
    <form onSubmit={onSubmit} className="grid grid-cols-1 md:grid-cols-5 gap-3 items-end bg-slate-50 border border-slate-200 rounded-lg p-3">
      <input name="name" value={form.name} onChange={onChange} required placeholder="Class name" className="border border-slate-300 rounded-md px-2 py-1.5 text-sm" />
      <input name="standard" value={form.standard} onChange={onChange} placeholder="Standard" className="border border-slate-300 rounded-md px-2 py-1.5 text-sm" />
      <input name="section" value={form.section} onChange={onChange} placeholder="Section" className="border border-slate-300 rounded-md px-2 py-1.5 text-sm" />
      <input name="label" value={form.label} onChange={onChange} placeholder="Label" className="border border-slate-300 rounded-md px-2 py-1.5 text-sm" />
      <input name="teacher" value={form.teacher} onChange={onChange} placeholder="Class Teacher" className="border border-slate-300 rounded-md px-2 py-1.5 text-sm" />
      <button type="submit" disabled={disabled} className="col-span-5 bg-indigo-600 text-white rounded-md px-4 py-2 transition">{disabled ? "Saving..." : "Save"}</button>
    </form>
  );
}
