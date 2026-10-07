import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

/** A styled native <select>: light, accessible, and uses the phone's own picker. */
export function NativeSelect({ className, ...props }: ComponentProps<"select">) {
  return (
    <select
      className={cn(
        "border-input bg-background focus-visible:ring-ring/50 h-9 rounded-lg border px-2.5 text-sm outline-none focus-visible:ring-3 disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}
