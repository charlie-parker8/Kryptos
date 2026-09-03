import type { ComponentPropsWithoutRef } from "react";
import clsx from "clsx";

interface ButtonProps extends ComponentPropsWithoutRef<"button"> {
  variant?: "primary" | "secondary";
  full?: boolean;
}

/** The repeated auth/action button, extracted. Not a design system — one file, two variants. */
export function Button({
  variant = "primary",
  full = false,
  className,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={clsx(
        "rounded-control px-3 py-2 text-sm font-semibold transition-opacity",
        variant === "primary"
          ? "bg-accent text-accent-fg hover:opacity-90 disabled:opacity-50"
          : "border border-border text-fg hover:text-fg-strong disabled:opacity-40",
        full && "w-full",
        className,
      )}
      {...props}
    />
  );
}
