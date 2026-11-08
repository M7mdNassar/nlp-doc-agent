import { FileText, Trash2, Loader2 } from "lucide-react";
import { Document } from "@/lib/api";
import { IngestionStatusBadge } from "./IngestionStatusBadge";
import { useDeleteDocument } from "@/hooks/useDocuments";
import { Button } from "@/components/ui/button";

export function DocumentCard({ doc }: { doc: Document }) {
  const { mutate: deleteDoc, isPending: isDeleting } = useDeleteDocument();

  return (
    <div className="group flex items-center justify-between p-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl hover:shadow-md transition-shadow">
      <div className="flex items-center gap-4 overflow-hidden">
        <div className="p-3 bg-slate-100 dark:bg-slate-800 rounded-lg shrink-0">
          <FileText className="w-6 h-6 text-teal-600" />
        </div>
        <div className="truncate">
          <p className="font-medium text-slate-900 dark:text-slate-100 truncate">
            {doc.name}
          </p>
          <p className="text-xs text-slate-500 mt-0.5">
            ID: {doc.id.slice(0, 12)}...
          </p>
        </div>
      </div>

      <div className="flex items-center gap-4 shrink-0">
        <IngestionStatusBadge status={doc.status} />
        <Button
          variant="ghost"
          size="icon"
          className="text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30"
          onClick={() => deleteDoc(doc.id)}
          disabled={isDeleting}
        >
          {isDeleting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
        </Button>
      </div>
    </div>
  );
}
