"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { X } from "lucide-react";
import { Button } from "./button";

type ToastOptions = {
  title: string;
  description?: string;
  duration?: number;
};

const ToastContext = createContext<{
  toast: (options: ToastOptions) => void;
} | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [notification, setNotification] = useState<ToastOptions | null>(null);
  const toast = useCallback((options: ToastOptions) => {
    setNotification({ ...options });
  }, []);

  useEffect(() => {
    if (!notification) return;
    const duration = notification.duration ?? 3000;
    if (duration <= 0) return;

    const timer = window.setTimeout(() => setNotification(null), duration);
    return () => window.clearTimeout(timer);
  }, [notification]);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="fixed bottom-4 right-4 z-50 w-[calc(100%-2rem)] max-w-sm"
      >
        {notification && (
          <div className="flex items-start gap-3 rounded-lg border border-slate-200 bg-white p-4 text-slate-900 shadow-lg dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold">{notification.title}</p>
              {notification.description && (
                <p className="mt-1 break-words text-sm text-slate-600 dark:text-slate-300">
                  {notification.description}
                </p>
              )}
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 shrink-0"
              aria-label="Dismiss notification"
              onClick={() => setNotification(null)}
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        )}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return context;
}
