import type { ComponentProps } from "react";

// size lives in the variant too: Tailwind orders utilities by its own rules, not by the class string, so a
// `py-1` passed in className can't reliably beat a base `py-2`
const VARIANTS = {
  primary: "px-4 py-2 bg-accent text-on-accent",
  quiet: "px-3 py-1 text-sm border border-border text-muted hover:text-fg",
};

type Props = ComponentProps<"button"> & { variant?: keyof typeof VARIANTS };

export function Button({ variant = "primary", className = "", ...props }: Props) {
  return (
    <button
      className={`rounded-lg font-medium disabled:opacity-40 ${VARIANTS[variant]} ${className}`}
      {...props}
    />
  );
}
