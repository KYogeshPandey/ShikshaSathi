import React, { useState } from "react";
import BulkImportForm from "../../components/forms/BulkImportForm";
import { api } from "../../api/api";

const entityApi = {
  student: "/students/import/csv",
  teacher: "/teachers/import/csv",
  classroom: "/classrooms/import/csv",
};

export default function BulkImportPage() {
  const [entity, setEntity] = useState("student");
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);

  const handleImport = async (file) => {
    setUploading(true);
    setResult(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await api.post(entityApi[entity], formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(res.data);
    } catch (err) {
      setResult({
        imported_count: 0,
        total: 0,
        failed_count: 1,
        errors: [{ row_no: "?", error: err.response?.data?.message || "Upload failed", row: {} }],
      });
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-indigo-50 to-slate-100 p-6">
      <div className="max-w-2xl mx-auto">
        <h2 className="text-2xl font-bold text-slate-800 mb-5">
          Bulk Import (Students, Teachers, Classes)
        </h2>
        <div className="flex gap-2 mb-3">
          {["student", "teacher", "classroom"].map((key) => (
            <button
              key={key}
              className={
                "px-3 py-1 text-sm rounded font-semibold " +
                (entity === key
                  ? "bg-indigo-600 text-white shadow"
                  : "bg-slate-200 text-slate-700 hover:bg-slate-300")
              }
              onClick={() => {
                setEntity(key);
                setResult(null);
              }}
            >
              {key.charAt(0).toUpperCase() + key.slice(1)}
            </button>
          ))}
        </div>
        <BulkImportForm
          entity={entity}
          uploading={uploading}
          result={result}
          onImport={handleImport}
          clearResult={() => setResult(null)}
        />
        <div className="mt-6 text-xs text-slate-500">
          <b>Tip:</b> Use a spreadsheet and export as <b>CSV</b>. Column order should match the sample header. Email/classroom can be blank for any row.
          <br />
          Admins can bulk enroll students, create many classes, or add teachers in one shot!
        </div>
      </div>
    </div>
  );
}
