import { RISK_GRADE_LABELS, formatMoney, type CreditRisk, type RiskGrade } from "@ai-pos/shared-types";
import { Gauge } from "lucide-react";
import { useEffect, useState } from "react";
import { customersApi, message } from "./api";

export const RISK_GRADE_STYLES: Record<RiskGrade, string> = {
  A: "bg-emerald-100 text-emerald-800",
  B: "bg-lime-100 text-lime-800",
  C: "bg-amber-100 text-amber-800",
  D: "bg-orange-100 text-orange-800",
  E: "bg-red-100 text-red-800",
};

export function RiskGradeBadge({ grade, score }: { grade: RiskGrade | null | undefined; score?: number | null }) {
  if (!grade) return <span className="text-xs text-charcoal/40">—</span>;
  return (
    <span
      title={`${RISK_GRADE_LABELS[grade]}${score !== null && score !== undefined ? ` · score ${score}/100` : ""}`}
      className={`inline-flex h-6 min-w-6 items-center justify-center rounded-full px-2 text-xs font-bold ${RISK_GRADE_STYLES[grade]}`}
    >
      {grade}
    </span>
  );
}

/** Explainable credit risk: the grade, every factor that added points, and the suggested limit. */
export function CreditRiskCard({ customerId, currency, refreshKey }: { customerId: string; currency: string; refreshKey: string }) {
  const [risk, setRisk] = useState<CreditRisk | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    customersApi
      .risk(customerId)
      .then((next) => !cancelled && setRisk(next))
      .catch((caught: unknown) => !cancelled && setError(message(caught, "Could not score this account.")));
    return () => {
      cancelled = true;
    };
  }, [customerId, refreshKey]);

  if (risk === null) {
    return error ? <p className="rounded-card border border-line bg-white p-5 text-sm text-charcoal/60">{error}</p> : null;
  }
  const limitDelta = risk.suggested_limit_cents - risk.credit_limit_cents;

  return (
    <article className="rounded-card border border-line bg-white p-5" aria-labelledby="credit-risk-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className={`flex h-12 w-12 items-center justify-center rounded-2xl text-xl font-bold ${RISK_GRADE_STYLES[risk.grade]}`}>
            {risk.grade}
          </span>
          <div>
            <h3 id="credit-risk-title" className="flex items-center gap-2 text-base font-semibold">
              <Gauge size={16} className="text-charcoal/50" aria-hidden="true" /> Credit risk · {risk.label}
            </h3>
            <p className="text-sm text-charcoal/70">{risk.recommendation}</p>
          </div>
        </div>
        <div className="text-right">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-charcoal/50">Score</p>
          <p className="text-2xl font-semibold tabular-nums">
            {risk.score}
            <span className="text-sm font-normal text-charcoal/50">/100</span>
          </p>
        </div>
      </div>

      <div className="mt-3 h-2 overflow-hidden rounded-full bg-surface" aria-hidden="true">
        <div
          className={`h-full rounded-full ${risk.score >= 50 ? "bg-red-500" : risk.score >= 30 ? "bg-amber-400" : "bg-emerald-500"}`}
          style={{ width: `${Math.max(4, risk.score)}%` }}
        />
      </div>

      {risk.factors.length > 0 ? (
        <ul className="mt-4 divide-y divide-line text-sm">
          {risk.factors.map((factor) => (
            <li key={factor.key} className="flex items-start justify-between gap-3 py-2">
              <span>
                <span className="font-medium">{factor.label}</span>
                <span className="block text-xs text-charcoal/60">{factor.detail}</span>
              </span>
              <span className="shrink-0 rounded-full bg-surface px-2 py-0.5 text-xs font-semibold tabular-nums">+{factor.points}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-4 text-sm text-charcoal/60">Nothing counts against this account: it pays on time and stays within its limit.</p>
      )}

      <p className="mt-3 rounded-xl bg-surface px-3 py-2 text-xs text-charcoal/70">
        Suggested limit {formatMoney(risk.suggested_limit_cents, currency)} (current {formatMoney(risk.credit_limit_cents, currency)}
        {limitDelta !== 0 ? `, ${limitDelta > 0 ? "+" : "−"}${formatMoney(Math.abs(limitDelta), currency)}` : ""}), from the last
        90 days of purchases, the payment terms and this grade.
      </p>
    </article>
  );
}
