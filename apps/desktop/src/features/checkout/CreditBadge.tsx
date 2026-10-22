import { RISK_GRADE_LABELS, formatMoney, type RiskGrade } from "@ai-pos/shared-types";
import type { RegisterCustomer } from "../../lib/tauri";

const GRADE_STYLES: Record<RiskGrade, string> = {
  A: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  B: "bg-lime-500/15 text-lime-700 dark:text-lime-300",
  C: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  D: "bg-orange-500/15 text-orange-700 dark:text-orange-300",
  E: "bg-red-500/15 text-red-700 dark:text-red-300",
};

interface CreditBadgeProps {
  customer: RegisterCustomer;
  currency: string;
  /** On-account amount of the sale being rung up, previewed against the limit. */
  pendingCents?: number;
}

export function CreditBadge({ customer, currency, pendingCents = 0 }: CreditBadgeProps) {
  const limit = customer.credit_limit_cents;
  const balance = customer.current_balance_cents;
  const projected = balance + pendingCents;
  const available = limit - projected;
  const over = available < 0;
  const used = limit > 0 ? Math.min(100, Math.round((projected / limit) * 100)) : projected > 0 ? 100 : 0;

  return (
    <div className="rounded-2xl bg-zinc-100 dark:bg-white/10 p-3" aria-label="Credit account">
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div>
          <p className="text-zinc-500 dark:text-white/50">Credit limit</p>
          <p className="mt-0.5 font-semibold tabular-nums">{formatMoney(limit, currency)}</p>
        </div>
        <div>
          <p className="text-zinc-500 dark:text-white/50">Unpaid</p>
          <p className="mt-0.5 font-semibold tabular-nums">{formatMoney(balance, currency)}</p>
        </div>
        <div className="text-right">
          <p className="text-zinc-500 dark:text-white/50">{over ? "Over limit" : "Available"}</p>
          <p className={`mt-0.5 font-semibold tabular-nums ${over ? "text-primary" : ""}`}>
            {formatMoney(Math.abs(available), currency)}
          </p>
        </div>
      </div>
      <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-zinc-100 dark:bg-white/10" aria-hidden="true">
        <div className={`h-full rounded-full ${over ? "bg-primary" : "bg-zinc-200 dark:bg-white/70"}`} style={{ width: `${used}%` }} />
      </div>
      {customer.risk_grade || customer.overdue_cents > 0 || (customer.pending_on_account_cents ?? 0) > 0 ? (
        <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-zinc-600 dark:text-white/60 tabular-nums">
          {customer.risk_grade ? (
            <span
              title={`Credit risk score ${customer.risk_score ?? "?"}/100`}
              className={`rounded-full px-2 py-0.5 font-bold ${GRADE_STYLES[customer.risk_grade]}`}
            >
              Risk {customer.risk_grade} · {RISK_GRADE_LABELS[customer.risk_grade]}
            </span>
          ) : null}
          {customer.overdue_cents > 0 ? (
            <span className="font-semibold text-primary">{formatMoney(customer.overdue_cents, currency)} overdue</span>
          ) : null}
          {(customer.pending_on_account_cents ?? 0) > 0 ? (
            <span>{formatMoney(customer.pending_on_account_cents ?? 0, currency)} waiting to sync</span>
          ) : null}
        </p>
      ) : null}
    </div>
  );
}
