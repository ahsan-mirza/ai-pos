import { formatMoney } from "@ai-pos/shared-types";
import { Bell, Receipt, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useBusinessCurrency } from "../features/checkout/currency";
import { useTableAlerts } from "../features/alerts/TableAlertContext";
import type { PosTableAlert } from "../features/alerts/tableAlertClient";

function tableTitle(name: string): string {
  return /^table\b/i.test(name.trim()) ? name : `Table ${name}`;
}

function relativeTime(iso: string, now: number): string {
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (seconds < 45) return "Just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  return `${Math.floor(minutes / 60)}h ago`;
}

function AlertRow({ alert, now }: { alert: PosTableAlert; now: number }) {
  const { acknowledge, clear } = useTableAlerts();
  const currency = useBusinessCurrency();
  const bill = alert.alert === "request-bill";
  const Icon = bill ? Receipt : Bell;
  return (
    <div
      className={`flex w-full max-w-3xl flex-wrap items-center gap-x-3 gap-y-2 rounded-2xl border px-4 py-3 shadow-lg ${
        bill
          ? "border-blue-400/70 bg-blue-950/95 text-blue-50"
          : "border-amber-400/70 bg-amber-950/95 text-amber-50"
      }`}
    >
      <Icon size={18} aria-hidden="true" className="shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold">
          {tableTitle(alert.tableName)}
          <span className="mx-2 font-normal opacity-70">·</span>
          {bill ? "Bill Requested" : "Call Waiter"}
        </p>
        <p className="text-xs opacity-80">
          {relativeTime(alert.createdAt, now)}
          {bill && alert.totalAmount !== null ? ` · ${formatMoney(alert.totalAmount, currency)}` : ""}
        </p>
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => acknowledge(alert.id)}
          className="rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-zinc-900"
        >
          Acknowledge
        </button>
        <button
          type="button"
          onClick={() => clear(alert.id)}
          className="inline-flex items-center gap-1 rounded-full px-2 py-1.5 text-xs font-semibold text-white/80 hover:text-white"
        >
          <X size={13} aria-hidden="true" />
          Clear
        </button>
      </div>
    </div>
  );
}

/** Fixed drawer under the register header. One row per open guest alert. */
export function POSAlertBanner() {
  const { banner } = useTableAlerts();
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (banner.length === 0) return;
    const timer = window.setInterval(() => setNow(Date.now()), 15_000);
    return () => window.clearInterval(timer);
  }, [banner.length]);

  if (banner.length === 0) return null;
  const shown = banner.slice(0, 3);
  return (
    <div
      className="z-30 flex flex-col items-center gap-2 border-b border-zinc-200 bg-zinc-50/95 px-4 py-3 backdrop-blur dark:border-zinc-800 dark:bg-zinc-950/95"
      role="status"
      aria-live="assertive"
      aria-label="Table alerts"
    >
      {shown.map((alert) => (
        <AlertRow key={alert.id} alert={alert} now={now} />
      ))}
      {banner.length > shown.length ? (
        <p className="text-xs font-semibold text-zinc-600 dark:text-zinc-300">
          {banner.length - shown.length} more table alert{banner.length - shown.length === 1 ? "" : "s"}
        </p>
      ) : null}
    </div>
  );
}
