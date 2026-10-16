import type { ComponentProps } from "react";

export function Button({ className = "", ...props }: ComponentProps<"button">) {
  return (
    <button
      className={`rounded-lg bg-accent px-4 py-2 font-medium text-on-accent disabled:opacity-40 ${className}`}
      {...props}
    />
  );
}
