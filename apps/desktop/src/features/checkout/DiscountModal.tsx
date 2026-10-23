import { Permission, discountLimitBps, discountShareBps, formatMoney } from "@ai-pos/shared-types";
import { Select } from "@ai-pos/ui";
import { Percent, X } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { ManagerApprovalModal } from "../../components/ManagerApprovalModal";
import { posPolicy } from "../../lib/capabilities";
import type { CashierSession } from "../auth/session";
import { lineGross, type CartLine, type ManualDiscount } from "./cart";
import { parseCents } from "./tenders";
import { verifyManager } from "./wholesaleClient";

interface DiscountModalProps {
  session: CashierSession;
  /** One line, or every discountable line for a whole-sale discount. */
  lines: CartLine[];
  title: string;
  currency: string;
  onClose: () => void;
  onApplied: (discounts: { lineId: string; discount: ManualDiscount }[]) => void;
}

/** What is left of a line after its promotion: the base a cashier discount is taken from. */
function baseOf(line: CartLine): number {
  return Math.max(0, lineGross(line) - (line.promotion?.discountCents ?? 0));
}

/** A fixed amount spread over lines in proportion to their value; the odd cents go to the largest remainders. */
export function spreadAmount(lines: CartLine[], cents: number): Map<string, number> {
  const bases = lines.map((line) => ({ id: line.lineId, base: baseOf(line) }));
  const total = bases.reduce((sum, item) => sum + item.base, 0);
  const shares = new Map<string, number>();
  if (total <= 0) return shares;
  const exact = bases.map((item) => ({ ...item, raw: (cents * item.base) / total }));
  let assigned = 0;
  for (const item of exact) {
    const whole = Math.floor(item.raw);
    shares.set(item.id, whole);
    assigned += whole;
  }
  const order = [...exact].sort((a, b) => b.raw - Math.floor(b.raw) - (a.raw - Math.floor(a.raw)));
  for (let index = 0; assigned < cents && index < order.length; index += 1, assigned += 1) {
    const id = order[index]!.id;
    shares.set(id, (shares.get(id) ?? 0) + 1);
  }
  return shares;
}

export function DiscountModal({ session, lines, title, currency, onClose, onApplied }: DiscountModalProps) {
  const titleId = useId();
  const policy = posPolicy();
  const reasons = policy.discounts.reasons;
  const [mode, setMode] = useState<"percent" | "amount">("percent");
  const [value, setValue] = useState("");
  const [reason, setReason] = useState(reasons[0]?.key ?? "");
  const [needsManager, setNeedsManager] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const before = lines.reduce((sum, line) => sum + baseOf(line), 0);
  const typed = mode === "percent" ? Number.parseFloat(value || "0") : parseCents(value);
  const discountCents =
    typed === null || !Number.isFinite(typed) || typed <= 0
      ? 0
      : mode === "percent"
        ? Math.floor((before * Math.min(typed, 100) * 100) / 10_000)
        : Math.min(typed, before);
  const share = discountShareBps(discountCents, before);
  const limit = discountLimitBps(session.user, policy);
  const valid = discountCents > 0 && reason !== "" && (mode !== "percent" || (typed !== null && typed <= 100));
  const reasonLabel = reasons.find((item) => item.key === reason)?.label ?? reason;

  const entries = useMemo(() => {
    return (approvedById: string | null, approverName: string | null, note: string) => {
      const base = { reason, reasonLabel, approvedById, approverName, note };
      if (mode === "percent") {
        const bps = Math.round(Math.min(typed ?? 0, 100) * 100);
        return lines.map((line) => ({ lineId: line.lineId, discount: { mode: "percent" as const, value: bps, ...base } }));
      }
      const spread = spreadAmount(lines, discountCents);
      return lines.map((line) => ({
        lineId: line.lineId,
        discount: { mode: "amount" as const, value: spread.get(line.lineId) ?? 0, ...base },
      }));
    };
  }, [discountCents, lines, mode, reason, reasonLabel, typed]);

  const apply = () => {
    if (!valid) return;
    if (share > limit) {
      setNeedsManager(true);
      return;
    }
    onApplied(entries(null, null, ""));
  };

  if (needsManager) {
    return (
      <ManagerApprovalModal
        reasons={[`${reasonLabel}: ${formatMoney(discountCents, currency)} off (${(share / 100).toFixed(1)}%) on ${title}`]}
        subtitle={`Above ${session.user.full_name}'s ${(limit / 100).toFixed(0)}% discount limit. A manager must enter their PIN.`}
        verify={async (username, pin) => {
          const approver = await verifyManager(session, username, pin, Permission.PosDiscount);
          if (share > discountLimitBps(approver, policy)) {
            throw new Error(`${approver.full_name} can approve discounts up to ${(discountLimitBps(approver, policy) / 100).toFixed(0)}%.`);
          }
          return approver;
        }}
        onClose={onClose}
        approveLabel="Approve discount"
        onApproved={(approver, note) => onApplied(entries(approver.id, approver.full_name, note))}
      />
    );
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="modal-card max-w-md">
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-primary/15 text-primary">
            <Percent size={20} aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-xl font-semibold">
              Discount
            </h2>
            <p className="truncate text-sm text-zinc-500 dark:text-zinc-400">
              {title} · {formatMoney(before, currency)}
            </p>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} className="modal-close">
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <form
          className="mt-5 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            setError(null);
            if (!valid) {
              setError("Enter the discount and pick a reason.");
              return;
            }
            apply();
          }}
        >
          <div className="flex rounded-full bg-zinc-100 p-1 dark:bg-zinc-800" role="group" aria-label="Discount type">
            {(["percent", "amount"] as const).map((option) => (
              <button
                key={option}
                type="button"
                aria-pressed={mode === option}
                onClick={() => {
                  setMode(option);
                  setValue("");
                }}
                className={`h-9 flex-1 rounded-full text-sm font-semibold ${
                  mode === option ? "bg-primary text-white" : "text-zinc-600 dark:text-zinc-300"
                }`}
              >
                {option === "percent" ? "Percent" : "Amount"}
              </button>
            ))}
          </div>
          <label className="block text-sm font-medium">
            {mode === "percent" ? "Discount (%)" : `Discount (${currency})`}
            <input
              autoFocus
              inputMode="decimal"
              value={value}
              onChange={(event) => setValue(event.target.value.replace(/[^\d.]/g, ""))}
              placeholder={mode === "percent" ? "10" : "5.00"}
              className="modal-input mt-1.5 text-lg font-semibold tabular-nums"
            />
          </label>
          {mode === "percent" ? (
            <div className="flex gap-2">
              {[5, 10, 15, 20].map((preset) => (
                <button
                  key={preset}
                  type="button"
                  onClick={() => setValue(String(preset))}
                  className="h-9 flex-1 rounded-xl border border-zinc-200 text-sm font-semibold hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
                >
                  {preset}%
                </button>
              ))}
            </div>
          ) : null}
          <label className="block text-sm font-medium">
            Reason
            <Select
              className="mt-1.5"
              aria-label="Reason"
              value={reason}
              onChange={setReason}
              options={reasons.map((item) => ({ value: item.key, label: item.label }))}
            />
          </label>
          <p className="text-sm tabular-nums text-zinc-600 dark:text-zinc-300">
            {discountCents > 0
              ? `${formatMoney(discountCents, currency)} off → ${formatMoney(before - discountCents, currency)}${
                  share > limit ? ` · above your ${(limit / 100).toFixed(0)}% limit, a manager approves` : ""
                }`
              : `You can give up to ${(limit / 100).toFixed(0)}% without a manager.`}
          </p>
          {error ? (
            <p role="alert" className="text-sm font-medium text-red-600 dark:text-red-400">
              {error}
            </p>
          ) : null}
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="modal-cancel">
              Cancel
            </button>
            <button type="submit" className="modal-save" disabled={!valid}>
              {share > limit ? "Ask a manager" : "Apply discount"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
