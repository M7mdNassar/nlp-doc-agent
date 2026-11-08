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
        "relative flex flex-col items-center justify-center w-full h-48 border-2 border-dashed rounded-xl cursor-pointer transition-all duration-200",
        isDragging 
          ? "border-teal-500 bg-teal-50/50 dark:bg-teal-900/20" 
          : "border-slate-300 hover:border-teal-400 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-900",
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
        <div className="flex flex-col items-center text-teal-600">
          <Loader2 className="w-10 h-10 mb-4 animate-spin" />
          <p className="text-sm font-medium">Uploading document...</p>
        </div>
      ) : (
        <div className="flex flex-col items-center text-slate-500">
          <div className="p-3 bg-white dark:bg-slate-800 rounded-full shadow-sm mb-4">
            <UploadCloud className="w-8 h-8 text-teal-600" />
          </div>
          <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
            Click to upload or drag and drop
          </p>
          <p className="text-xs text-slate-400 mt-1">PDF, DOCX, TXT, or MD (max 50MB)</p>
        </div>
      )}
    </div>
  );
}