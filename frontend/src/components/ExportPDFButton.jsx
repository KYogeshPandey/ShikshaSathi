import React from "react";
import html2pdf from "html2pdf.js";

/**
 * props:
 *   targetRef: ref to any HTML element (table, div, etc) to export
 *   filename: filename for PDF ("report.pdf" etc)
 *   buttonText: Label for export button
 *   className: extra CSS class
 */
export default function ExportPDFButton({
  targetRef,
  filename = "report.pdf",
  buttonText = "Export PDF",
  className = "",
  ...rest
}) {
  const handleExport = () => {
    if (!targetRef?.current) {
      alert("Nothing to export!");
      return;
    }
    html2pdf()
      .set({
        margin: [10, 8],
        filename: filename,
        image: { type: "jpeg", quality: 0.98 },
        html2canvas: { scale: 2, useCORS: true },
        jsPDF: { unit: "mm", format: "a4", orientation: "portrait" },
      })
      .from(targetRef.current)
      .save();
  };

  return (
    <button
      type="button"
      onClick={handleExport}
      className={`bg-pink-600 text-white px-3 py-1.5 rounded shadow hover:bg-pink-700 text-xs font-medium ${className}`}
      {...rest}
    >
      {buttonText}
    </button>
  );
}
