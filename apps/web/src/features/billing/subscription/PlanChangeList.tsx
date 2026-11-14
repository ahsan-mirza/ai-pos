import { formatMoney, type BillingQuote } from "@ai-pos/shared-types";
import { formatDateTime, useLocale } from "@ai-pos/ui";
import { useEffect, useState } from "react";
import { ApiRequestError, apiGet, apiPost } from "../../../lib/api";
import { changeNextAction, changeStatusLabel, planChangeIsOpen } from "./display";
import { EmptyState, ErrorState, LoadingBlock } from "./States";

export interface PlanChangeEvent {
  previous_status: string | null;
  status: string;
  actor_type: string;
  created_at: string;
  reason: string | null;
}

export interface PlanChangeRequest {
  id: string;
  reference: string;
  current_plan_code: string;
  requested_plan_code: string;
  requested_cycle_code: string;
  status: string;
  quote: BillingQuote;
  invoice_id: string | null;
  rejection_reason: string | null;
  created_at: string;
  events: PlanChangeEvent[];
}

interface PlanChangePage {
  items: PlanChangeRequest[];
  total: number;
}

export function PlanChangeList({
  refreshKey,
  onPendingPlan,
}: {
  refreshKey: number;
  onPendingPlan: (planCode: string | null) => void;
}) {
  const { t } = useLocale();
  const [page, setPage] = useState<PlanChangePage | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [limit, setLimit] = useState(20);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    apiGet<PlanChangePage>(`/api/v1/billing/subscription-changes?limit=${limit}`)
      .then((found) => {
        if (cancelled) return;
        setPage(found);
        const open = found.items.find((item) => planChangeIsOpen(item.status));
        onPendingPlan(open?.requested_plan_code ?? null);
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        if (caught instanceof ApiRequestError && caught.status === 403) {
          setPage({ items: [], total: 0 });
          onPendingPlan(null);
          return;
        }
        setError(caught instanceof ApiRequestError ? caught.message : "Could not load plan changes.");
        onPendingPlan(null);
      });
    return () => {
      cancelled = true;
    };
  }, [limit, refreshKey, reload, onPendingPlan]);

  const cancel = async (id: string) => {
    setBusyId(id);
    setError(null);
    try {
      await apiPost(`/api/v1/billing/subscription-changes/${id}/cancel`, {});
      setReload((value) => value + 1);
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : t("Could not cancel the plan change."));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="min-w-0 rounded-2xl border border-line bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <h3 className="text-sm font-semibold text-charcoal dark:text-white">{t("Plan changes")}</h3>
      {page === undefined ? <div className="mt-3"><LoadingBlock className="h-16" /></div> : null}
      {error ? (
        <div className="mt-3">
          <ErrorState message={t(error)} onRetry={() => setReload((value) => value + 1)} />
        </div>
      ) : null}
      {page && page.items.length === 0 ? (
        <div className="mt-3">
          <EmptyState title={t("No plan changes yet.")} />
        </div>
      ) : null}
      {page && page.items.length > 0 ? (
        <ul className="mt-3 min-w-0 divide-y divide-line dark:divide-zinc-800">
          {page.items.map((item) => (
            <li key={item.id} className="min-w-0 py-3">
              <div className="flex min-w-0 flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-charcoal dark:text-white">
                    {t("{from} to {to}", { from: item.current_plan_code, to: t(item.quote.plan_name) })}
                  </p>
                  <p className="mt-1 text-xs text-charcoal/70 dark:text-white/70">
                    {t(item.quote.cycle_name)} · {t(changeStatusLabel(item.status))} ·{" "}
                    <span dir="ltr">{formatDateTime(item.created_at)}</span>
                  </p>
                  <p className="mt-1 text-xs text-charcoal/70 dark:text-white/70">
                    {t(changeNextAction(item.status, item.rejection_reason))}
                  </p>
                  {item.quote?.total_fils != null ? (
                    <p className="mt-1 text-sm tabular-nums text-charcoal dark:text-white" dir="ltr">
                      {formatMoney(item.quote.total_fils, item.quote.currency)}
                    </p>
                  ) : null}
                  <p className="mt-1 text-xs text-charcoal/50 dark:text-white/50">
                    {item.reference}
                    {item.invoice_id ? ` · ${t("Invoice")} ${item.invoice_id.slice(0, 8)}` : ""}
                  </p>
                  {item.rejection_reason ? (
                    <p className="mt-1 text-xs text-red-700 dark:text-red-300">{item.rejection_reason}</p>
                  ) : null}
                </div>
                {item.status === "quoted" ? (
                  <button
                    type="button"
                    disabled={busyId === item.id}
                    onClick={() => void cancel(item.id)}
                    className="inline-flex h-10 items-center rounded-full border border-line px-4 text-sm font-semibold text-charcoal focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-60 dark:text-white"
                  >
                    {busyId === item.id ? t("Please wait…") : t("Cancel request")}
                  </button>
                ) : null}
              </div>
              {item.events.length > 0 ? (
                <details className="mt-2">
                  <summary className="cursor-pointer text-xs font-semibold text-charcoal/70 dark:text-white/70">{t("Status history")}</summary>
                  <ol className="mt-2 space-y-1 text-xs text-charcoal/70 dark:text-white/70">
                    {item.events.map((event, index) => (
                      <li key={`${item.id}-${index}`}>
                        {event.previous_status ? `${t(changeStatusLabel(event.previous_status))} → ` : ""}
                        {t(changeStatusLabel(event.status))}
                        {" · "}
                        <span dir="ltr">{formatDateTime(event.created_at)}</span>
                        {event.reason ? ` · ${t(event.reason)}` : ""}
                      </li>
                    ))}
                  </ol>
                </details>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {page && page.total > page.items.length ? (
        <button
          type="button"
          onClick={() => setLimit((value) => value + 20)}
          className="mt-2 inline-flex h-10 items-center text-sm font-semibold text-accent"
        >
          {t("Show more")}
        </button>
      ) : null}
    </div>
  );
}
