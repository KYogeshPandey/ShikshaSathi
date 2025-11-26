import React from "react";

export default function Loader({ text = "Loading..." }) {
  return (
    <div className="flex justify-center items-center py-6">
      <span className="animate-spin text-indigo-500 mr-2 text-xl">⏳</span>
      <span>{text}</span>
    </div>
  );
}
