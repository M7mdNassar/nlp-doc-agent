const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Document = {
  id: string;
  name: string;
  status: "queued" | "parsing" | "embedding" | "indexed" | "failed";
};

export const api = {
  getDocuments: async (): Promise<{ items: Document[] }> => {
    const res = await fetch(`${API_URL}/documents`);
    if (!res.ok) throw new Error("Failed to fetch documents");
    return res.json();
  },

  uploadDocument: async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${API_URL}/documents`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.message || "Upload failed");
    }
    return res.json();
  },

  deleteDocument: async (id: string) => {
    const res = await fetch(`${API_URL}/documents/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Delete failed");
    return res.json();
  },

  chat: async (message: string) => {
    const res = await fetch(`${API_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.message || "Chat failed");
    }
    return res.json();
  },
};