"use client";

import { useEffect, useRef } from "react";
import { useChat } from "@/hooks/useChat";
import { MessageBubble } from "@/components/chat/MessageBubble";
import { InputBar } from "@/components/chat/InputBar";
import { Bot, AlertCircle, Loader2, Sparkles } from "lucide-react";

export default function ChatPage() {
  const { messages, sendMessage, isLoading, error } = useChat();
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isLoading]);

  return (
    <div className="flex flex-col h-full relative">

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6 pb-32">
        <div className="max-w-3xl mx-auto">

          {/* Empty State */}
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-[60vh] text-center animate-fade-in">
              <div className="w-20 h-20 bg-gradient-to-br from-teal-100 to-teal-50 dark:from-teal-900/40 dark:to-teal-900/10 rounded-3xl flex items-center justify-center mb-8 shadow-inner">
                <Sparkles className="w-10 h-10 text-teal-600 dark:text-teal-400" />
              </div>
              <h2 className="text-3xl font-bold text-slate-900 dark:text-slate-50 mb-3 tracking-tight">
                How can I help you today?
              </h2>
              <p className="text-slate-500 max-w-md text-lg">
                I can analyze your uploaded documents, extract tables, perform calculations, and compare multiple files.
              </p>
            </div>
          )}

          {/* Message List */}
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}

          {/* Loading Indicator */}
          {isLoading && (
            <div className="flex gap-4 mb-8 animate-fade-in">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-teal-400 to-teal-600 flex items-center justify-center shrink-0 mt-1 shadow-sm">
                <Sparkles className="w-5 h-5 text-white animate-pulse-soft" />
              </div>
              <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 px-6 py-4 rounded-2xl rounded-tl-sm shadow-sm flex items-center gap-3">
                <Loader2 className="w-5 h-5 text-teal-600 animate-spin" />
                <span className="text-sm text-slate-500 font-medium animate-pulse">
                  Agents are retrieving and analyzing evidence...
                </span>
              </div>
            </div>
          )}

          {/* Error State */}
          {error && (
            <div className="flex justify-center mb-8 animate-fade-in">
              <div className="flex items-center gap-2 px-5 py-3 bg-red-50 text-red-600 rounded-xl border border-red-200 text-sm shadow-sm font-medium">
                <AlertCircle className="w-5 h-5" />
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