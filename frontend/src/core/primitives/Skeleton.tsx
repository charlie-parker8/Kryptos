import clsx from "clsx";

/** A single shimmering placeholder block. Give it a height + width via `className`. */
export function Skeleton({
  className,
  rounded = "sm",
}: {
  className?: string;
  rounded?: "sm" | "full" | "none";
}) {
  return (
    <span
      aria-hidden="true"
      className={clsx(
        "k-skeleton block",
        rounded === "full" && "rounded-full",
        rounded === "none" && "rounded-none",
        className,
      )}
    />
  );
}

/** N stacked text-line skeletons; the last line is shorter. */
export function SkeletonText({
  lines = 3,
  className,
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <span className={clsx("flex flex-col gap-1.5", className)} aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton
          key={i}
          className={clsx("h-3", i === lines - 1 ? "w-2/3" : "w-full")}
        />
      ))}
    </span>
  );
}

/** Skeleton rows for a table `<tbody>` — `cols` cells wide, `rows` tall. */
export function SkeletonRows({ cols, rows = 5 }: { cols: number; rows?: number }) {
  return (
    <>
      {Array.from({ length: rows }, (_, r) => (
        <tr key={r} aria-hidden="true">
          {Array.from({ length: cols }, (_, c) => (
            <td key={c}>
              <Skeleton className="h-3.5 w-full" />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}
