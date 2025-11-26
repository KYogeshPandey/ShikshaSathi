import React, { useRef, useState } from "react";

export default function BulkImportForm({
  entity = "student",        // "student" | "teacher" | "classroom"
  onImport,                  // (file: File) => void
  uploading = false,
  result = null,             // result object from API
  clearResult,
}) {
  const fileRef = useRef();

  // Allowed CSV sample headers for UI
  const samples = {
    student: "name,roll_no,classroom_id,email",
    teacher: "name,email,phone,role",
    classroom: "name,standard,section,label",
  };

  return (
    <div className="border border-slate-200 bg-slate-50 rounded-xl p-4 mb-4">
      <div className="font-semibold text-slate-700 mb-1">
        Import {entity.charAt(0).toUpperCase() + entity.slice(1)}s (.csv)
      </div>
      <form
        onSubmit={e => {
          e.preventDefault();
          if (fileRef.current && fileRef.current.files.length) {
            onImport(fileRef.current.files[0]);
          }
        }}
        className="flex flex-col md:flex-row items-center gap-2 md:gap-4"
      >
        <input
          ref={fileRef}
          type="file"
          accept=".csv"
          required
          className="flex-1 border border-slate-300 rounded px-2 py-1 text-xs"
        />
        <button
          type="submit"
          disabled={uploading}
          className="bg-emerald-600 text-white font-medium px-4 py-1.5 rounded shadow hover:bg-emerald-700 disabled:bg-slate-400"
        >
          {uploading ? "Uploading..." : "Import"}
        </button>
        <span className="text-xs text-slate-400 italic">
          Sample: {samples[entity]}
        </span>
      </form>
      {result && (
        <div className="mt-2 bg-white border border-green-200 text-green-700 px-3 py-2 rounded text-xs">
          <div>
            Imported: <b>{result.imported_count ?? 0}</b> / {result.total ?? 0}
            {result.failed_count > 0 && (
              <> | Failed: <b className="text-red-600">{result.failed_count}</b></>
            )}
          </div>
          {result.errors && result.errors.length > 0 && (
            <details className="mt-1">
              <summary className="cursor-pointer">View Errors</summary>
              <ul className="list-disc ml-4">
                {result.errors.map((e, idx) => (
                  <li key={idx}>
                    Row {e.row_no}: {e.error}
                    <span className="ml-2 text-slate-400">{JSON.stringify(e.row)}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
          <button className="mt-2 text-indigo-500 underline" onClick={clearResult}>
            OK
          </button>
        </div>
      )}
    </div>
  );
}
