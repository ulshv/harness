import type { ComponentProps } from "react";

export function TextArea({ className = "", ...props }: ComponentProps<"textarea">) {
  return (
    <textarea
      className={`resize-none rounded-lg border border-border bg-surface px-3 py-2 outline-none placeholder:text-muted focus:border-accent ${className}`}
      {...props}
    />
  );
}
