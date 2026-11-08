import { FileText, Trash2, Loader2 } from "lucide-react";
import { Document } from "@/lib/api";
import { IngestionStatusBadge } from "./IngestionStatusBadge";
import { useDeleteDocument } from "@/hooks/useDocuments";
import { Button } from "@/components/ui/button";

export function DocumentCard({ doc }: { doc: Document }) {
  const { mutate: deleteDoc, isPending: isDeleting } = useDeleteDocument();

  return (
    <div className="group flex items-center justify-between p-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl hover:shadow-lg hover:border-teal-100 dark:hover:border-teal-900/50 transition-all duration-300 animate-fade-in">
      <div className="flex items-center gap-4 overflow-hidden">
        <div className="p-3 bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-800 dark:to-slate-800/50 rounded-xl shrink-0 group-hover:scale-105 transition-transform">
          <FileText className="w-6 h-6 text-teal-600 dark:text-teal-400" />
        </div>
        <div className="truncate">
          <p className="font-semibold text-slate-900 dark:text-slate-100 truncate text-sm">
            {doc.name}
          </p>
          <p className="text-xs text-slate-500 mt-1 font-mono">
            ID: {doc.id.slice(0, 8)}...
          </p>
        </div>
      </div>

      <div className="flex items-center gap-4 shrink-0">
        <IngestionStatusBadge status={doc.status} />
        <Button
          variant="ghost"
          size="icon"
          className="text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30 rounded-xl"
          onClick={() => deleteDoc(doc.id)}
          disabled={isDeleting}
        >
          {isDeleting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
        </Button>
      </div>
    </div>
  );
}