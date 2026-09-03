import { Skeleton } from "@/core/primitives/Skeleton";

/** Static shaped mock of the authed shell, shown while `GET /auth/me` is in flight. */
export function AppShellSkeleton() {
  return (
    <div className="flex min-h-dvh flex-col bg-bg" aria-hidden="true">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-border px-4">
        <div className="flex items-center gap-6">
          <Skeleton className="h-4 w-24" />
          <div className="hidden gap-2 sm:flex">
            <Skeleton className="h-4 w-16" />
            <Skeleton className="h-4 w-16" />
            <Skeleton className="h-4 w-20" />
          </div>
        </div>
        <Skeleton className="h-6 w-6" rounded="full" />
      </header>
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <aside className="shrink-0 space-y-3 border-b border-border bg-surface-2/40 p-3 lg:w-64 lg:border-b-0 lg:border-r">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} className="h-4 w-full" />
          ))}
        </aside>
        <main className="min-w-0 flex-1 space-y-4 px-4 py-6 sm:px-6">
          <Skeleton className="h-12 w-64" />
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-24 w-full" />
        </main>
      </div>
    </div>
  );
}
