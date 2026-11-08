"use client";

import { Children } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Message } from "@/hooks/useChat";
import { formatTextWithCitations, CitationMatch } from "@/lib/chat-utils";
import { Bot, User, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { useToast } from "@/components/ui/use-toast";

export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  const { toast } = useToast();

  const handleCitationClick = (citation: CitationMatch) => {
    toast({
      title: "Citation Source",
      description: `Document: ${citation.docId} | Page: ${citation.page}`,
      duration: 3000,
    });
  };

  return (
    <div className={cn("flex w-full mb-8 animate-fade-in", isUser ? "justify-end" : "justify-start")}>
      <div className={cn("flex gap-4 max-w-[85%]", isUser ? "flex-row-reverse" : "flex-row")}>

        {/* Avatar */}
        <div className={cn(
          "flex items-center justify-center w-9 h-9 rounded-xl shrink-0 mt-1 shadow-sm",
          isUser ? "bg-slate-800 text-slate-100" : "bg-gradient-to-br from-teal-400 to-teal-600 text-white"
        )}>
          {isUser ? <User className="w-5 h-5" /> : <Sparkles className="w-5 h-5" />}
        </div>

        {/* Bubble */}
        <div className={cn(
          "px-5 py-4 rounded-2xl text-[15px] leading-relaxed shadow-sm",
          isUser
            ? "bg-slate-800 text-white rounded-tr-sm"
            : "bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-800 dark:text-slate-200 rounded-tl-sm"
        )}>
          {isUser ? (
            <p className="whitespace-pre-wrap">{message.content}</p>
          ) : (
            <div className="prose prose-sm md:prose-base dark:prose-invert max-w-none prose-table:border prose-table:border-slate-200 prose-th:bg-slate-50 prose-th:p-3 prose-td:p-3 prose-td:border-t prose-td:border-slate-200 prose-a:text-teal-600">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  p: ({ children }) => {
                    return (
                      <p className="mb-4 last:mb-0">
                        {Children.map(children, (child) => {
                          if (typeof child === "string") {
                            return formatTextWithCitations(child, handleCitationClick);
                          }
                          return child;
                        })}
                      </p>
                    );
                  }
                }}
              >
                {message.content}
              </ReactMarkdown>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}