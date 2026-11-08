"use client";

import { useEffect, useRef } from "react";
import { useChat } from "@/hooks/useChat";
import { MessageBubble } from "@/components/chat/MessageBubble";
import { InputBar } from "@/components/chat/InputBar";
import { Bot, AlertCircle, Loader2 } from "lucide-react";

export default function ChatPage() {
  const { messages, sendMessage, isLoading, error } = useChat();
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isLoading]);

  return (
    <div className="flex flex-col h-full bg-slate-50 dark:bg-slate-950">
      
      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6">
        <div className="max-w-3xl mx-auto">
          
          {/* Empty State */}
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-[50vh] text-center">
              <div className="w-16 h-16 bg-teal-100 dark:bg-teal-900/50 rounded-2xl flex items-center justify-center mb-6 shadow-sm">
                <Bot className="w-8 h-8 text-teal-600 dark:text-teal-400" />
              </div>
              <h2 className="text-2xl font-bold text-slate-900 dark:text-slate-100 mb-2">
                How can I help you today?
              </h2>
              <p className="text-slate-500 max-w-md">
                I can analyze your uploaded documents, extract tables, perform calculations, and compare multiple files.
              </p>
            </div>
          )}

          {/* Message List */}
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}

          {/* Loading Indicator (The 3-Agent Pipeline) */}
          {isLoading && (
            <div className="flex gap-4 mb-6">
              <div className="w-8 h-8 rounded-full bg-teal-100 flex items-center justify-center shrink-0 mt-1">
                <Bot className="w-5 h-5 text-teal-700" />
              </div>
              <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 px-5 py-4 rounded-2xl rounded-tl-sm shadow-sm flex items-center gap-3">
                <Loader2 className="w-4 h-4 text-teal-600 animate-spin" />
                <span className="text-sm text-slate-500 font-medium animate-pulse">
                  Agents are retrieving and analyzing evidence...
                </span>
              </div>
            </div>
          )}

          {/* Error State */}
          {error && (
            <div className="flex justify-center mb-6">
              <div className="flex items-center gap-2 px-4 py-2 bg-red-50 text-red-600 rounded-lg border border-red-200 text-sm">
                <AlertCircle className="w-4 h-4" />
                {error}
              </div>
            </div>
          )}

          <div ref={scrollRef} />
        </div>
      </div>

      {/* Input Area */}
      <InputBar onSend={sendMessage} isLoading={isLoading} />
    </div>
  );
}