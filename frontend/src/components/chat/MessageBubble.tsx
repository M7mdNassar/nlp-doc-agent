"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Message } from "@/hooks/useChat";
import { formatTextWithCitations, CitationMatch } from "@/lib/chat-utils";
import { Bot, User, BookOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import { useToast } from "@/components/ui/use-toast"; // Assuming you have toast setup

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

  // Split text into chunks so Markdown still works, but citations are React elements
  // (A simplified approach: render text with citations first, then pass to Markdown)
  // For simplicity in this demo, we will parse citations directly in the text.
  
  return (
    <div className={cn("flex w-full mb-6", isUser ? "justify-end" : "justify-start")}>
      <div className={cn("flex gap-4 max-w-[85%]", isUser ? "flex-row-reverse" : "flex-row")}>
        
        {/* Avatar */}
        <div className={cn(
          "flex items-center justify-center w-8 h-8 rounded-full shrink-0 mt-1",
          isUser ? "bg-slate-200 text-slate-600" : "bg-teal-100 text-teal-700"
        )}>
          {isUser ? <User className="w-5 h-5" /> : <Bot className="w-5 h-5" />}
        </div>

        {/* Bubble */}
        <div className={cn(
          "px-5 py-3.5 rounded-2xl text-sm leading-relaxed",
          isUser 
            ? "bg-teal-600 text-white rounded-tr-sm shadow-sm" 
            : "bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-800 dark:text-slate-200 rounded-tl-sm shadow-sm"
        )}>
          {isUser ? (
            <p className="whitespace-pre-wrap">{message.content}</p>
          ) : (
            <div className="prose prose-sm dark:prose-invert max-w-none prose-table:border prose-table:border-slate-200 prose-th:bg-slate-50 prose-th:p-2 prose-td:p-2 prose-td:border-t prose-td:border-slate-200">
              <ReactMarkdown 
                remarkPlugins={[remarkGfm]}
                components={{
                  p: ({ children }) => {
                    // Intercept paragraph text to inject citation chips
                    return (
                      <p>
                        {React.Children.map(children, (child) => {
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