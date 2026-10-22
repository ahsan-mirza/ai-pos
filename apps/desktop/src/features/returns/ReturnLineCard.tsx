import {
  ReturnReason,
  formatMoney,
  type ReceiptItem,
  type ReturnCondition as Condition,
  type ReturnPolicy,
  type ReturnReason as Reason,
} from "@ai-pos/shared-types";
import { CheckCircle2, Minus, Plus, ScanLine, ShieldCheck } from "lucide-react";
import { Select } from "../../components/Select";
import {
  conditionOptions,
  isFaultyCondition,
  reasonOptions,
  remainingQuantity,
  type LineDraft,
  type PricedLine,
} from "./returnMath";

interface ReturnLineCardProps {
  item: ReceiptItem;
  policy: ReturnPolicy;
  currency: string;
  priced: PricedLine | undefined;
  disabled: boolean;
  onToggle: () => void;
  onChange: (patch: Partial<LineDraft>) => void;
  onVerifySerial: () => void;
}

/** Whether the unit is still covered: returns outside the window may still qualify for a warranty repair. */
function WarrantyChip({ expires }: { expires: string }) {
  const end = new Date(expires);
  const covered = end.getTime() > Date.now();
  return (
    <span
      title={`Warranty ${covered ? "until" : "ended"} ${end.toLocaleDateString()}`}
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
        covered ? "bg-charcoal text-white dark:bg-white dark:text-zinc-900" : "bg-surface text-charcoal/60 ring-1 ring-line"
      }`}
    >
      <ShieldCheck size={11} aria-hidden="true" />
      {covered ? `Warranty to ${end.toLocaleDateString(undefined, { month: "short", year: "numeric" })}` : "Warranty ended"}
    </span>
  );
}


export function ReturnLineCard({
  item,
  policy,
  currency,
  priced,
  disabled,
  onToggle,
  onChange,
  onVerifySerial,
}: ReturnLineCardProps) {
  const remaining = remainingQuantity(item);
  const selected = priced !== undefined;
  const exhausted = remaining === 0 || Boolean(item.gift_card);
  const inputId = `return-line-${item.sale_item_id}`;

  return (
    <li
      className={`rounded-2xl border p-4 transition ${
        selected ? "border-primary bg-white dark:bg-zinc-900 shadow-[0_0_0_1px_rgb(var(--primary-rgb))]" : "border-line dark:border-zinc-800 bg-surface dark:bg-zinc-800/60"
      } ${exhausted ? "opacity-60" : ""}`}
    >
      <div className="flex items-start gap-3">
        <input
          id={inputId}
          type="checkbox"
          checked={selected}
          disabled={disabled || exhausted}
          onChange={onToggle}
          className="mt-1 h-5 w-5 shrink-0 accent-primary"
        />
        <label htmlFor={inputId} className="flex min-w-0 flex-1 cursor-pointer flex-wrap items-start justify-between gap-3">
          <span className="min-w-0">
            <span className="flex flex-wrap items-center gap-2 font-semibold">
              {item.name}
              {item.warranty_expires_at ? (
                <WarrantyChip expires={item.warranty_expires_at} />
              ) : null}
              {item.final_sale ? (
                <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-800 dark:bg-amber-900/40 dark:text-amber-200">
                  Final sale
                </span>
              ) : null}
              {item.gift_card ? (
                <span className="rounded-full bg-surface px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-charcoal/60 ring-1 ring-line">
                  Gift card · not returnable
                </span>
              ) : null}
            </span>
            <span className="mt-0.5 block text-xs text-charcoal/50 dark:text-zinc-400">
              {item.sku} · {item.category}
              {item.variant ? ` · ${item.variant}` : ""}
              {item.serial_last4 ? (
                <span className="font-mono">
                  {" "}
                  · {item.serial_kind === "imei" ? "IMEI" : "S/N"} •••• {item.serial_last4}
                </span>
              ) : null}
            </span>
          </span>
          <span className="text-right text-sm tabular-nums">
            <span className="block font-semibold">{formatMoney(item.line_total_cents, currency)}</span>
            <span className="block text-xs text-charcoal/50 dark:text-zinc-400">
              {item.quantity} × {formatMoney(item.unit_price_cents, currency)}
              {item.discount_cents ? ` · −${formatMoney(item.discount_cents, currency)} discount` : ""}
              {item.returned_quantity > 0 ? ` · ${item.returned_quantity} returned` : ""}
            </span>
          </span>
        </label>
      </div>

      {selected ? (
        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {item.is_serialized ? (
            <div className="text-xs font-medium text-charcoal/60 dark:text-zinc-400">
              Unit check
              <button
                type="button"
                disabled={disabled}
                onClick={onVerifySerial}
                className={`mt-1 flex h-11 w-full items-center justify-center gap-2 rounded-xl text-sm font-semibold ${
                  priced.draft.serialValue ? "bg-charcoal text-white dark:bg-zinc-100 dark:text-zinc-900" : "bg-primary text-white"
                }`}
              >
                {priced.draft.serialValue ? (
                  <>
                    <CheckCircle2 size={16} aria-hidden="true" /> Verified
                  </>
                ) : (
                  <>
                    <ScanLine size={16} aria-hidden="true" /> Scan {item.serial_kind === "imei" ? "IMEI" : "serial"}
                  </>
                )}
              </button>
            </div>
          ) : (
            <div className="text-xs font-medium text-charcoal/60 dark:text-zinc-400">
              Quantity (of {remaining})
              <div className="mt-1 flex h-11 items-center justify-between rounded-xl border border-line dark:border-zinc-800 bg-white dark:bg-zinc-900 px-1">
                <button
                  type="button"
                  aria-label="Fewer"
                  disabled={disabled || priced.draft.quantity <= 1}
                  onClick={() => onChange({ quantity: priced.draft.quantity - 1 })}
                  className="flex h-9 w-9 items-center justify-center rounded-lg text-charcoal dark:text-zinc-100 disabled:opacity-30"
                >
                  <Minus size={16} aria-hidden="true" />
                </button>
                <span className="text-base font-semibold tabular-nums text-charcoal dark:text-zinc-100">{priced.draft.quantity}</span>
                <button
                  type="button"
                  aria-label="More"
                  disabled={disabled || priced.draft.quantity >= remaining}
                  onClick={() => onChange({ quantity: priced.draft.quantity + 1 })}
                  className="flex h-9 w-9 items-center justify-center rounded-lg text-charcoal dark:text-zinc-100 disabled:opacity-30"
                >
                  <Plus size={16} aria-hidden="true" />
                </button>
              </div>
            </div>
          )}
          <div className="text-xs font-medium text-charcoal/60 dark:text-zinc-400">
            <label id={`${inputId}-condition-label`} htmlFor={`${inputId}-condition`}>
              Condition
            </label>
            <Select<Condition>
              id={`${inputId}-condition`}
              labelledBy={`${inputId}-condition-label`}
              className="mt-1"
              value={priced.draft.condition}
              disabled={disabled}
              options={conditionOptions(policy)}
              onChange={(condition) =>
                onChange(
                  isFaultyCondition(policy, condition) && priced.draft.reason === ReturnReason.ChangedMind
                    ? { condition, reason: ReturnReason.Defective }
                    : { condition },
                )
              }
            />
          </div>
          <div className="text-xs font-medium text-charcoal/60 dark:text-zinc-400">
            <label id={`${inputId}-reason-label`} htmlFor={`${inputId}-reason`}>
              Reason
            </label>
            <Select<Reason>
              id={`${inputId}-reason`}
              labelledBy={`${inputId}-reason-label`}
              className="mt-1"
              value={priced.draft.reason}
              disabled={disabled}
              options={reasonOptions(policy)}
              onChange={(reason) => onChange({ reason })}
            />
          </div>
          <div className="rounded-xl bg-surface dark:bg-zinc-800/60 px-3 py-2 text-xs text-charcoal/60 dark:text-zinc-400 tabular-nums">
            <p className="flex justify-between">
              <span>Tax refund</span>
              <span>{formatMoney(priced.tax, currency)}</span>
            </p>
            <p className="flex justify-between">
              <span>Restocking fee</span>
              <span className={priced.fee > 0 ? "text-primary" : ""}>
                {priced.policyFee === 0
                  ? "None"
                  : priced.fee === 0
                    ? "Waived"
                    : `−${formatMoney(priced.fee, currency)}`}
              </span>
            </p>
            <p className="mt-0.5 flex justify-between text-sm font-semibold text-charcoal dark:text-zinc-100">
              <span>Line refund</span>
              <span>{formatMoney(priced.refund, currency)}</span>
            </p>
          </div>
        </div>
      ) : null}
    </li>
  );
}
