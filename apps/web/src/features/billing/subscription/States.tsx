import { useLocale } from "@ai-pos/ui";
import type { ReactNode } from "react";

export function SectionHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h2 className="text-lg font-semibold text-charcoal dark:text-white">{title}</h2>
        {subtitle ? <p className="mt-1 max-w-2xl text-sm text-charcoal/70 dark:text-white/70">{subtitle}</p> : null}
      </div>
      {action ? <div className="min-w-0 max-w-full">{action}</div> : null}
    </div>
  );
}

export function LoadingBlock({ className = "h-40" }: { className?: string }) {
  return <div className={`animate-pulse rounded-2xl bg-zinc-100 dark:bg-zinc-800 ${className}`} />;
}

export function LoadingCards({ count, tall = false }: { count: number; tall?: boolean }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-busy="true">
      {Array.from({ length: count }, (_, index) => (
        <LoadingBlock key={index} className={tall ? "h-64" : "h-28"} />
      ))}
    </div>
  );
}

export function EmptyState({ title, message }: { title: string; message?: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-line bg-white px-4 py-8 text-center dark:border-zinc-800 dark:bg-zinc-900">
      <p className="text-sm font-semibold text-charcoal dark:text-white">{title}</p>
      {message ? <p className="mt-1 text-sm text-charcoal/60 dark:text-white/60">{message}</p> : null}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useLocale();
  return (
    <div className="rounded-2xl border border-red-200 bg-white px-4 py-4 dark:border-red-900/60 dark:bg-zinc-900" role="alert">
      <p className="text-sm text-red-800 dark:text-red-300">{message}</p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 inline-flex h-10 items-center rounded-full border border-line px-4 text-sm font-semibold text-charcoal focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent dark:text-white"
        >
          {t("Try again")}
        </button>
      ) : null}
    </div>
  );
}
