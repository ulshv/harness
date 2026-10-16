import type { ReactNode } from "react";

// a right-aligned bubble: sets a short message apart from the text around it
export function Bubble({ children }: { children: ReactNode }) {
  return (
    <div className="max-w-[80%] self-end rounded-2xl bg-surface px-4 py-2 wrap-break-word whitespace-pre-wrap shadow-sm">
      {children}
    </div>
  );
}
