"use client";

import { useState, useRef } from "react";
import { UploadCloud, Loader2 } from "lucide-react";
import { useUploadDocument } from "@/hooks/useDocuments";
import { cn } from "@/lib/utils";

export function UploadDropzone() {
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { mutate: upload, isPending } = useUploadDocument();

  const handleFile = (file: File) => {
    if (!file) return;
    upload(file);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={onDrop}
      onClick={() => fileInputRef.current?.click()}
      className={cn(
        "relative flex flex-col items-center justify-center w-full h-56 border-2 border-dashed rounded-2xl cursor-pointer transition-all duration-300 overflow-hidden group bg-white dark:bg-slate-900/50 shadow-sm hover:shadow-md",
        isDragging
          ? "border-teal-500 bg-teal-50/80 dark:bg-teal-900/20 scale-[1.02]"
          : "border-slate-300 hover:border-teal-400 dark:border-slate-700",
        isPending && "opacity-50 pointer-events-none"
      )}
    >
      <input
        type="file"
        ref={fileInputRef}
        className="hidden"
        accept=".pdf,.docx,.txt,.md"
        onChange={(e) => {
          if (e.target.files?.length) handleFile(e.target.files[0]);
        }}
      />

      {isPending ? (
        <div className="flex flex-col items-center text-teal-600 animate-pulse">
          <Loader2 className="w-12 h-12 mb-4 animate-spin" />
          <p className="text-sm font-semibold tracking-wide">Uploading document...</p>
        </div>
      ) : (
        <div className="flex flex-col items-center text-slate-500 z-10">
          <div className="p-4 bg-teal-50 dark:bg-slate-800 rounded-2xl shadow-sm mb-5 group-hover:scale-110 transition-transform duration-300 group-hover:-translate-y-1">
            <UploadCloud className="w-8 h-8 text-teal-600 dark:text-teal-400" />
          </div>
          <p className="text-base font-semibold text-slate-800 dark:text-slate-200">
            Click to upload or drag and drop
          </p>
          <p className="text-sm text-slate-400 mt-2 font-medium">PDF, DOCX, TXT, or MD (max 50MB)</p>
        </div>
      )}
    </div>
  );
}