import { Badge } from "@/components/ui/badge";
import { Loader2, CheckCircle2, XCircle, Clock } from "lucide-react";
import { Document } from "@/lib/api";

export function IngestionStatusBadge({ status }: { status: Document["status"] }) {
  switch (status) {
    case "queued":
      return (
        <Badge variant="outline" className="text-slate-500 border-slate-200 bg-slate-50">
          <Clock className="w-3 h-3 mr-1" /> Queued
        </Badge>
      );
    case "parsing":
    case "embedding":
      return (
        <Badge variant="outline" className="text-teal-600 border-teal-200 bg-teal-50">
          <Loader2 className="w-3 h-3 mr-1 animate-spin" /> Processing
        </Badge>
      );
    case "indexed":
      return (
        <Badge variant="outline" className="text-emerald-600 border-emerald-200 bg-emerald-50">
          <CheckCircle2 className="w-3 h-3 mr-1" /> Ready
        </Badge>
      );
    case "failed":
      return (
        <Badge variant="outline" className="text-red-600 border-red-200 bg-red-50">
          <XCircle className="w-3 h-3 mr-1" /> Failed
        </Badge>
      );
    default:
      return <Badge variant="outline">{status}</Badge>;
  }
}