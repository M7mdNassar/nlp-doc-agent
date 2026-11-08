import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function useDocuments() {
  return useQuery({
    queryKey: ["documents"],
    queryFn: api.getDocuments,
    // Smart polling: If any document is still processing, poll every 3 seconds
    refetchInterval: (query) => {
      const docs = query.state.data?.items || [];
      const isProcessing = docs.some((d) => 
        ["queued", "parsing", "embedding"].includes(d.status)
      );
      return isProcessing ? 3000 : false;
    },
  });
}

export function useUploadDocument() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: api.uploadDocument,
    onSuccess: () => {
      // Refresh the document list instantly
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}

export function useDeleteDocument() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: api.deleteDocument,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}
