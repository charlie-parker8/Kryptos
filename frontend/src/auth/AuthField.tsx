import type { ComponentPropsWithoutRef } from "react";

interface AuthFieldProps extends ComponentPropsWithoutRef<"input"> {
  label: string;
}

/** A labelled input in the auth-form style — used for email + password on both screens. */
export function AuthField({ label, id, ...props }: AuthFieldProps) {
  return (
    <label htmlFor={id} className="block">
      <span className="mb-1 block text-[0.6875rem] font-medium uppercase tracking-[0.1em] text-muted">
        {label}
      </span>
      <input
        id={id}
        className="w-full rounded-control border border-border bg-bg px-3 py-2 font-mono text-sm text-fg-strong outline-none placeholder:text-muted focus:border-accent"
        {...props}
      />
    </label>
  );
}
