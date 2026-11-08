import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

type ButtonProps = ComponentProps<"button"> & {
  variant?: "default" | "ghost" | "outline";
  size?: "default" | "icon";
};

export function Button({
  className,
  variant = "default",
  size = "default",
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-xl text-sm font-medium transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 active:scale-95",
        variant === "ghost" && "hover:bg-slate-100 dark:hover:bg-slate-800",
        variant === "outline" && "border border-slate-200 bg-transparent hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800",
        variant === "default" && "bg-gradient-to-r from-teal-500 to-teal-600 text-white shadow-md hover:shadow-lg hover:from-teal-600 hover:to-teal-700",
        size === "icon" ? "h-10 w-10" : "h-11 px-6 py-2",
        className
      )}
      {...props}
    />
  );
}