import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

type BadgeProps = ComponentProps<"span"> & {
  variant?: "default" | "outline";
};

export function Badge({
  className,
  variant = "default",
  ...props
}: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold",
        variant === "outline"
          ? "border-slate-200 text-slate-700 dark:border-slate-700 dark:text-slate-200"
          : "border-transparent bg-teal-600 text-white",
        className
      )}
      {...props}
    />
  );
}
