import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

type ButtonProps = ComponentProps<"button"> & {
  variant?: "default" | "ghost";
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
        "inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
        variant === "ghost"
          ? "hover:bg-slate-100 dark:hover:bg-slate-800"
          : "bg-teal-600 text-white hover:bg-teal-700",
        size === "icon" ? "h-10 w-10" : "h-10 px-4 py-2",
        className
      )}
      {...props}
    />
  );
}
