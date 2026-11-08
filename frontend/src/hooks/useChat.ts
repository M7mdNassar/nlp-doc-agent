import { useState } from "react";
import { api } from "@/lib/api";

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sendMessage = async (content: string) => {
    if (!content.trim() || isLoading) return;

    const userMsg: Message = { id: Date.now().toString(), role: "user", content };
    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);
    setError(null);

    try {
      const response = await api.chat(content);
      
      const assistantMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: response.answer,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: unknown) {
      setError(
        err instanceof Error && err.message
          ? err.message
          : "Failed to get a response from the agents."
      );
    } finally {
      setIsLoading(false);
    }
  };

  return { messages, sendMessage, isLoading, error };
}
