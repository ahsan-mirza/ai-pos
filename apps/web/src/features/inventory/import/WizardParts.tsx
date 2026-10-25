import { formatMoney, type ImportRowStatus } from "@ai-pos/shared-types";
import { ArrowDownRight, ArrowUpRight, Check } from "lucide-react";
import type { ReactNode } from "react";

export const STEPS = [
  { id: 1, label: "Upload", hint: "File, branch & supplier" },
  { id: 2, label: "Map columns", hint: "Match file headers" },
  { id: 3, label: "Preview & commit", hint: "Review every line" },
] as const;

export function StepProgress({ step }: { step: number }) {
  return (
    <ol className="grid grid-cols-3 gap-2" aria-label="Import progress">
      {STEPS.map((item) => {
        const done = step > item.id;
        const current = step === item.id;
        return (
          <li key={item.id} aria-current={current ? "step" : undefined} className="min-w-0">
            <div
              className={`h-1.5 rounded-full transition-colors duration-300 ${
                done || current ? "bg-accent" : "bg-charcoal/10"
              }`}
            />
            <div className="mt-2.5 flex items-center gap-2.5">
              <span
                className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-bold tabular-nums transition-colors ${
                  done
                    ? "bg-accent text-white"
                    : current
                      ? "bg-charcoal text-white"
                      : "bg-surface text-charcoal/40 ring-1 ring-line"
                }`}
              >
                {done ? <Check size={13} strokeWidth={3} aria-hidden="true" /> : item.id}
              </span>
              <span className="min-w-0">
                <span
                  className={`block truncate text-sm font-semibold ${current || done ? "text-charcoal" : "text-charcoal/40"}`}
                >
                  {item.label}
                </span>
                <span className="hidden truncate text-[11px] text-charcoal/50 sm:block">{item.hint}</span>
              </span>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

const rowStyles: Record<ImportRowStatus, string> = {
  NEW: "bg-accent text-white",
  EXISTING: "bg-charcoal text-white",
  ERROR: "bg-danger/10 text-danger ring-1 ring-danger/40",
};

const rowLabels: Record<ImportRowStatus, string> = { NEW: "New", EXISTING: "Existing", ERROR: "Error" };

export function RowBadge({ status }: { status: ImportRowStatus }) {
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${rowStyles[status]}`}
    >
      {rowLabels[status]}
    </span>
  );
}

/** "Existing Cost: AED 50.00 | Import Cost: AED 58.00", tinted by direction of the change. */
export function CostDelta({
  existing,
  incoming,
  currency,
}: {
  existing: number | null;
  incoming: number | null;
  currency: string;
}) {
  if (existing === null || incoming === null || existing === incoming) return null;
  const up = incoming > existing;
  const percent = existing > 0 ? Math.round(((incoming - existing) / existing) * 1000) / 10 : null;
  return (
    <span
      className={`mt-1 inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-semibold tabular-nums ${
        up ? "bg-accent/10 text-accent" : "bg-charcoal/[0.06] text-charcoal/70"
      }`}
    >
      {up ? <ArrowUpRight size={12} aria-hidden="true" /> : <ArrowDownRight size={12} aria-hidden="true" />}
      <span>Existing Cost: {formatMoney(existing, currency)}</span>
      <span className="text-current/40" aria-hidden="true">
        |
      </span>
      <span>Import Cost: {formatMoney(incoming, currency)}</span>
      {percent !== null ? (
        <span className="opacity-70">
          ({up ? "+" : ""}
          {percent}%)
        </span>
      ) : null}
    </span>
  );
}

export function Metric({ label, value, tone = "plain" }: { label: string; value: ReactNode; tone?: "plain" | "accent" }) {
  return (
    <div className="min-w-0 rounded-2xl border border-line bg-white px-4 py-3">
      <span className="block text-[11px] font-semibold uppercase tracking-wider text-[#6B7280]">{label}</span>
      <span
        className={`mt-1 block truncate text-lg font-semibold tabular-nums ${tone === "accent" ? "text-accent" : ""}`}
      >
        {value}
      </span>
    </div>
  );
}
