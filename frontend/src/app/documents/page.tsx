"use client";

import { UploadDropzone } from "@/components/documents/UploadDropzone";
import { DocumentCard } from "@/components/documents/DocumentCard";
import { useDocuments } from "@/hooks/useDocuments";
import { FileText, Loader2 } from "lucide-react";

export default function DocumentsPage() {
  const { data, isLoading, isError } = useDocuments();

  return (
    <div className="flex-1 overflow-y-auto p-8">
      <div className="max-w-4xl mx-auto space-y-8">
        
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-50 tracking-tight">
            Document Library
          </h1>
          <p className="text-slate-500 mt-1">
            Upload and manage the documents your AI agents will use.
          </p>
        </div>

        {/* Upload Area */}
        <UploadDropzone />

        {/* Document List */}
        <div className="space-y-4">
          <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-200">
            Your Documents
          </h2>
          
          {isLoading ? (
            <div className="flex items-center justify-center py-12 text-slate-500">
              <Loader2 className="w-6 h-6 animate-spin mr-2" />
              Loading documents...
            </div>
          ) : isError ? (
            <div className="p-4 bg-red-50 text-red-600 rounded-lg border border-red-200">
              Failed to load documents. Is the backend running?
            </div>
          ) : data?.items.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl text-center">
              <FileText className="w-12 h-12 text-slate-300 mb-4" />
              <p className="text-slate-600 dark:text-slate-400 font-medium">No documents yet</p>
              <p className="text-sm text-slate-400 mt-1">Upload a file above to get started.</p>
            </div>
          ) : (
            <div className="grid gap-3">
              {data?.items.map((doc) => (
                <DocumentCard key={doc.id} doc={doc} />
              ))}
            </div>
          )}
        </div>

      </div>
    </div>
  );
}