import { Capability, formatMoney, type PaymentsConfig, type ProductUpsert } from "@ai-pos/shared-types";
import { DateInput } from "@ai-pos/ui";
import {
  ArrowLeftRight,
  Banknote,
  BookUser,
  CalendarClock,
  CreditCard,
  FileCheck2,
  Minus,
  Plus,
  QrCode,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Truck,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useCapabilities } from "../../lib/capabilities";
import type { CashierProfile, RegisterCustomer } from "../../lib/tauri";
import { useEffect, useState, type ReactNode } from "react";
import { BnplTender } from "./BnplTender";
import { CardTerminalTender } from "./CardTerminalTender";
import { foreignNeeded, loadCurrencies, type ForeignCurrency } from "./fx";
import { loadPaymentsConfig } from "./integratedPay";
import { loadLoyaltyRules, maxRedeemable, type LoyaltyRules } from "./loyalty";
import { QrTender } from "./QrTender";
import { GiftCardRow } from "./GiftCardRow";
import { StoreCreditRow } from "./StoreCreditRow";
import { TradeInRow } from "./TradeInRow";
import {
  MAX_GUESTS,
  parseCents,
  quickCashAmounts,
  splitEqually,
  tenderOptions,
  type DepositMethod,
  type GuestShare,
  type PaymentDraft,
  type TenderChoice,
  type TenderPlan,
} from "./tenders";

const depositMethods: { value: DepositMethod; label: string }[] = [
  { value: "cash", label: "Cash" },
  { value: "card", label: "Card" },
  { value: "transfer", label: "Transfer" },
];

const tenderIcons: Record<TenderChoice, LucideIcon> = {
  cash: Banknote,
  card: CreditCard,
  transfer: ArrowLeftRight,
  cheque: FileCheck2,
  qr: QrCode,
  bnpl: CalendarClock,
  on_account: BookUser,
  split: Users,
  channel: Truck,
};

const shortLabels: Record<TenderChoice, string> = {
  cash: "Cash",
  card: "Card",
  transfer: "Transfer",
  cheque: "Cheque",
  qr: "QR",
  bnpl: "Later",
  on_account: "Account",
  split: "Split",
  channel: "App",
};

/** Guest-by-guest payment: equal or custom shares, each collected by cash or card and ticked off as paid. */
function GuestSplit({
  draft,
  dueCents,
  currency,
  disabled,
  onChange,
}: {
  draft: PaymentDraft;
  dueCents: number;
  currency: string;
  disabled: boolean;
  onChange: (draft: PaymentDraft) => void;
}) {
  const guests = draft.guests ?? [];
  const sum = guests.reduce((total, guest) => total + (parseCents(guest.amount) ?? 0), 0);
  const left = dueCents - sum;
  const setGuests = (next: GuestShare[]) => onChange({ ...draft, guests: next });
  const update = (index: number, changes: Partial<GuestShare>) =>
    setGuests(guests.map((guest, at) => (at === index ? { ...guest, ...changes } : guest)));
  return (
    <div className="space-y-1.5 rounded-2xl border border-zinc-200 bg-white/[0.03] p-2 dark:border-white/[0.08]">
      <div className="flex items-center gap-2 text-xs">
        <span className="font-semibold">Split equally into</span>
        <button type="button" aria-label="Fewer guests" disabled={disabled || guests.length <= 2}
          onClick={() => setGuests(splitEqually(dueCents, guests.length - 1))}
          className="flex h-7 w-7 items-center justify-center rounded-full bg-zinc-100 disabled:opacity-40 dark:bg-white/10">
          <Minus size={13} aria-hidden="true" />
        </button>
        <span className="w-5 text-center text-sm font-bold tabular-nums">{guests.length}</span>
        <button type="button" aria-label="More guests" disabled={disabled || guests.length >= MAX_GUESTS}
          onClick={() => setGuests(splitEqually(dueCents, guests.length + 1))}
          className="flex h-7 w-7 items-center justify-center rounded-full bg-zinc-100 disabled:opacity-40 dark:bg-white/10">
          <Plus size={13} aria-hidden="true" />
        </button>
        {left === 0 ? (
          <span className="ml-auto text-zinc-500 dark:text-white/50">Shares add up</span>
        ) : (
          <button type="button" disabled={disabled || guests.some((guest) => guest.paid)}
            onClick={() => setGuests(splitEqually(dueCents, guests.length))}
            title="Share the amount due equally again"
            className="ml-auto font-semibold tabular-nums text-amber-600 underline-offset-2 hover:underline disabled:no-underline">
            {left > 0 ? "Left" : "Over"} {formatMoney(Math.abs(left), currency)}
          </button>
        )}
      </div>
      <ul className="custom-scrollbar max-h-56 space-y-1 overflow-y-auto">
        {guests.map((guest, index) => (
          <li key={index} className={`flex items-center gap-1.5 rounded-xl px-1.5 py-1 ${guest.paid ? "bg-emerald-500/10" : ""}`}>
            <span className="w-14 shrink-0 text-xs font-semibold">Guest {index + 1}</span>
            <input aria-label={`Guest ${index + 1} share`} inputMode="decimal" value={guest.amount} disabled={disabled || guest.paid}
              onChange={(event) => update(index, { amount: event.target.value })}
              className={`${darkInput} h-8 min-w-0 flex-1 text-right text-sm font-semibold tabular-nums`} />
            <div className="flex shrink-0 rounded-full bg-zinc-100 p-0.5 dark:bg-white/10" role="group" aria-label={`Guest ${index + 1} pays by`}>
              {(["cash", "card"] as const).map((method) => (
                <button key={method} type="button" aria-pressed={guest.method === method} disabled={disabled || guest.paid}
                  onClick={() => update(index, { method })}
                  className={`h-7 rounded-full px-2 text-[11px] font-semibold ${guest.method === method ? "bg-white text-zinc-900 shadow-sm dark:bg-zinc-800 dark:text-white" : "text-zinc-500"}`}>
                  {method === "cash" ? "Cash" : "Card"}
                </button>
              ))}
            </div>
            <label className="flex shrink-0 items-center gap-1 text-[11px] font-semibold">
              <input type="checkbox" checked={guest.paid} disabled={disabled || parseCents(guest.amount) === null}
                onChange={(event) => update(index, { paid: event.target.checked })} className="h-4 w-4 accent-emerald-500" />
              Paid
            </label>
          </li>
        ))}
      </ul>
    </div>
  );
}

const darkInput =
  "h-11 w-full rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/60 px-3.5 text-zinc-900 dark:text-white placeholder:text-zinc-400 dark:placeholder:text-white/30 transition-colors focus:border-primary focus:outline-none focus:ring-4 focus:ring-primary/20";

interface TenderPanelProps {
  draft: PaymentDraft;
  plan: TenderPlan;
  totalCents: number;
  currency: string;
  customer: RegisterCustomer | null;
  canSellOnAccount: boolean;
  creditApprover: string | null;
  disabled: boolean;
  onChange: (draft: PaymentDraft) => void;
  onRequestCreditApproval: () => void;
  canTradeIn: boolean;
  cashierId: string;
  products: ProductUpsert[];
  /** The coupon field, when this sale can take one; `applied` keeps the extras section open. */
  coupon: { node: ReactNode; applied: boolean } | null;
  /** Settling a delivery-app order: the app's name, which unlocks the "paid on the app" tender. */
  deliveryChannel?: string | null;
  /** Checks a manager's PIN for a manual card entry when the store's terminal is integrated. */
  verifyManager?: (username: string, pin: string) => Promise<CashierProfile>;
}

/** "voucher", "coupon", "trade-in" -> "voucher, coupon or trade-in". */
function orList(items: string[]): string {
  return items.length < 2 ? (items[0] ?? "") : `${items.slice(0, -1).join(", ")} or ${items[items.length - 1]}`;
}

function MoneyInput({
  id,
  label,
  value,
  onChange,
  action,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  action?: { label: string; onClick: () => void; disabled?: boolean };
}) {
  return (
    <div className="flex items-end gap-2">
      <label className="flex-1 text-xs font-medium text-zinc-600 dark:text-white/60" htmlFor={id}>
        {label}
        <input
          id={id}
          inputMode="decimal"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="0.00"
          className={`${darkInput} mt-1.5 text-lg font-semibold tabular-nums`}
        />
      </label>
      {action ? (
        <button
          type="button"
          disabled={action.disabled}
          onClick={action.onClick}
          className="h-11 rounded-2xl bg-zinc-100 dark:bg-white/10 px-4 text-sm font-semibold transition hover:bg-zinc-200 dark:hover:bg-white/15 disabled:opacity-40"
        >
          {action.label}
        </button>
      ) : null}
    </div>
  );
}

export function TenderPanel({
  draft,
  plan,
  totalCents,
  currency,
  customer,
  canSellOnAccount,
  creditApprover,
  disabled,
  onChange,
  onRequestCreditApproval,
  canTradeIn,
  cashierId,
  products,
  coupon,
  deliveryChannel = null,
  verifyManager,
}: TenderPanelProps) {
  const [extrasOpen, setExtrasOpen] = useState(false);
  const loyaltyCents = Math.min(draft.loyalty?.valueCents ?? 0, totalCents);
  const tradeInCents = Math.min(draft.tradeIn?.amountCents ?? 0, totalCents - loyaltyCents);
  const giftCardCents = Math.min(draft.giftCard?.balanceCents ?? 0, totalCents - loyaltyCents - tradeInCents);
  const voucherCents = Math.min(
    draft.storeCredit?.balanceCents ?? 0,
    totalCents - loyaltyCents - tradeInCents - giftCardCents,
  );
  // What the chosen tender still has to collect after points, trade-in, gift card and store credit.
  const dueCents = totalCents - loyaltyCents - tradeInCents - giftCardCents - voucherCents;
  const exact = (dueCents / 100).toFixed(2);
  const [currencies, setCurrencies] = useState<ForeignCurrency[]>([]);
  const [rules, setRules] = useState<LoyaltyRules | null>(null);
  useEffect(() => {
    void loadCurrencies().then(setCurrencies);
    void loadLoyaltyRules().then(setRules);
  }, []);
  const { enabled } = useCapabilities();
  const [payments, setPayments] = useState<PaymentsConfig | null>(null);
  const integrated = enabled.has(Capability.CardTerminals) || enabled.has(Capability.Bnpl);
  useEffect(() => {
    if (integrated) void loadPaymentsConfig().then(setPayments);
  }, [integrated]);
  const bnplOffered = enabled.has(Capability.Bnpl) && (payments?.bnpl.length ?? 0) > 0;
  const cardTerminal = enabled.has(Capability.CardTerminals) && (payments?.card_terminal_required ?? false);
  useEffect(() => {
    if (cardTerminal !== Boolean(draft.cardTerminal)) onChange({ ...draft, cardTerminal });
  }, [cardTerminal, draft, onChange]);
  const options = tenderOptions.filter(
    (option) =>
      (option.value !== "bnpl" || bnplOffered) &&
      (option.value !== "cheque" || enabled.has(Capability.Cheques)) &&
      (option.value !== "on_account" || enabled.has(Capability.B2bCredit)) &&
      (option.value !== "split" || enabled.has(Capability.SplitBills)) &&
      (option.value !== "channel" || deliveryChannel !== null),
  );
  const foreignCash = enabled.has(Capability.MultiCurrency) ? currencies : [];
  const loyaltyOn = enabled.has(Capability.Loyalty);
  const hiddenChoice = !options.some((option) => option.value === draft.choice);
  const staleForeign = draft.cashCurrency != null && foreignCash.length === 0;
  useEffect(() => {
    if (hiddenChoice || staleForeign) onChange({ ...draft, choice: hiddenChoice ? "cash" : draft.choice, cashCurrency: null });
  }, [hiddenChoice, staleForeign, draft, onChange]);
  const balance = customer?.loyalty_points ?? 0;
  const redeemable = rules ? maxRedeemable(rules, balance, totalCents) : 0;
  const usingPoints = (draft.loyalty?.points ?? 0) > 0;
  const onAccountAllowed = canSellOnAccount && customer?.customer_type === "WHOLESALE";
  const changeDue = plan.changeCents !== null && plan.changeCents >= 0 ? plan.changeCents : null;
  const pointsOffered = Boolean(loyaltyOn && rules?.enabled && customer && (redeemable > 0 || usingPoints));
  const tradeInOffered = canTradeIn && enabled.has(Capability.TradeIn);
  const giftCardsOffered = enabled.has(Capability.GiftCards);
  const extrasApplied =
    draft.storeCredit != null || draft.giftCard != null || draft.tradeIn != null || usingPoints || (coupon?.applied ?? false);
  // Anything applied changes what is due, so it stays on screen until removed.
  const showExtras = extrasOpen || extrasApplied;
  const extraNames = [
    ...(giftCardsOffered ? ["gift card"] : []),
    "voucher",
    ...(coupon ? ["coupon"] : []),
    ...(tradeInOffered ? ["trade-in"] : []),
    ...(pointsOffered ? ["points"] : []),
  ];

  return (
    <div className="space-y-2">
      <div
        className="no-scrollbar flex gap-1 overflow-x-auto rounded-2xl bg-zinc-100 p-1 dark:bg-black/25"
        role="group"
        aria-label="Payment method"
      >
        {options.map((option) => {
          const blocked = option.value === "on_account" && !onAccountAllowed;
          const Icon = tenderIcons[option.value];
          const active = draft.choice === option.value;
          return (
            <button
              key={option.value}
              type="button"
              aria-pressed={active}
              aria-label={option.label}
              disabled={disabled || blocked}
              title={
                blocked
                  ? canSellOnAccount
                    ? "Attach a wholesale customer to sell on account."
                    : "Your role cannot sell on account."
                  : option.label
              }
              onClick={() =>
                onChange({
                  ...draft,
                  choice: option.value,
                  guests: option.value === "split" && !(draft.guests?.length) ? splitEqually(dueCents, 2) : draft.guests,
                })
              }
              className={`flex min-h-12 min-w-[4.5rem] flex-1 flex-col items-center justify-center gap-0.5 rounded-xl px-1 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 active:scale-[0.98] disabled:opacity-30 ${
                active ? "bg-primary text-white shadow-md shadow-primary/25" : "text-zinc-600 dark:text-white/70 hover:bg-white dark:hover:bg-white/5 hover:text-zinc-900 dark:hover:text-white"
              }`}
            >
              <Icon size={16} aria-hidden="true" />
              {shortLabels[option.value]}
            </button>
          );
        })}
      </div>

      {draft.choice === "cash" ? (
        <div className="space-y-1.5 rounded-2xl border border-zinc-200 bg-white/[0.03] p-2 dark:border-white/[0.08]">
          {foreignCash.length > 0 ? (
            <div className="flex flex-wrap gap-1" role="group" aria-label="Cash currency">
              {[{ code: currency, rate_micros: 0, name: currency }, ...foreignCash].map((option) => {
                const active = (draft.cashCurrency?.code ?? currency) === option.code;
                return (
                  <button
                    key={option.code}
                    type="button"
                    aria-pressed={active}
                    disabled={disabled}
                    onClick={() =>
                      onChange({
                        ...draft,
                        cashReceived: "",
                        cashCurrency: option.code === currency ? null : { code: option.code, rateMicros: option.rate_micros },
                      })
                    }
                    className={`h-7 rounded-full px-3 text-xs font-semibold ${
                      active ? "bg-zinc-900 text-white dark:bg-white dark:text-zinc-900" : "bg-zinc-100 text-zinc-600 dark:bg-white/10 dark:text-white/70"
                    }`}
                  >
                    {option.code}
                  </button>
                );
              })}
            </div>
          ) : null}
          <div className="flex items-center gap-2">
            <label className="relative min-w-0 flex-1" htmlFor="cash-received">
              <span className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-xs font-medium text-zinc-500 dark:text-white/50">
                {draft.cashCurrency ? `${draft.cashCurrency.code} received` : "Cash received"}
              </span>
              <input
                id="cash-received"
                inputMode="decimal"
                value={draft.cashReceived}
                onChange={(event) => onChange({ ...draft, cashReceived: event.target.value })}
                placeholder="0.00"
                className={`${darkInput} h-10 pl-28 text-right text-base font-semibold tabular-nums`}
              />
            </label>
            <p className="w-24 shrink-0 text-right" aria-live="polite">
              <span className="block text-[10px] font-semibold uppercase tracking-wide text-zinc-500 dark:text-white/50">Change</span>
              <span className={`block truncate text-base font-bold tabular-nums ${changeDue ? "text-emerald-500 dark:text-emerald-400" : "text-zinc-400 dark:text-white/40"}`}>
                {changeDue !== null ? formatMoney(changeDue, currency) : "—"}
              </span>
            </p>
          </div>
          {draft.cashCurrency ? (
            <p className="flex items-center justify-between text-xs text-zinc-600 dark:text-white/60">
              <span className="tabular-nums">
                Needed {formatMoney(foreignNeeded(dueCents, draft.cashCurrency.rateMicros), draft.cashCurrency.code)} at{" "}
                {(draft.cashCurrency.rateMicros / 1_000_000).toFixed(4)}
              </span>
              <button
                type="button"
                disabled={disabled || dueCents === 0}
                onClick={() =>
                  onChange({
                    ...draft,
                    cashReceived: (foreignNeeded(dueCents, draft.cashCurrency!.rateMicros) / 100).toFixed(2),
                  })
                }
                className="rounded-full bg-zinc-100 px-3 py-1 font-semibold dark:bg-white/10"
              >
                Exact
              </button>
            </p>
          ) : null}
          <div className={`no-scrollbar flex gap-1 overflow-x-auto ${draft.cashCurrency ? "hidden" : ""}`} role="group" aria-label="Quick cash amounts">
            <button
              type="button"
              disabled={disabled || dueCents === 0}
              onClick={() => onChange({ ...draft, cashReceived: exact })}
              className="h-7 shrink-0 rounded-full bg-zinc-200/70 px-3 text-[11px] font-semibold transition hover:bg-zinc-200 disabled:opacity-40 dark:bg-white/10 dark:hover:bg-white/15"
            >
              Exact
            </button>
            {quickCashAmounts(dueCents).map((cents) => (
              <button
                key={cents}
                type="button"
                disabled={disabled}
                onClick={() => onChange({ ...draft, cashReceived: (cents / 100).toFixed(2) })}
                className="h-7 shrink-0 rounded-full border border-zinc-200 px-2.5 text-[11px] font-semibold tabular-nums transition hover:border-primary hover:text-primary disabled:opacity-40 dark:border-white/10"
              >
                {formatMoney(cents, currency)}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {draft.choice === "channel" ? (
        <p className="rounded-2xl border border-zinc-200 bg-white/[0.03] p-3 text-xs text-zinc-600 dark:border-white/[0.08] dark:text-white/60">
          The customer paid {deliveryChannel ?? "the delivery app"}. The app owes this amount, less its commission, until
          it pays out.
        </p>
      ) : null}

      {draft.choice === "split" ? (
        <GuestSplit draft={draft} dueCents={dueCents} currency={currency} disabled={disabled} onChange={onChange} />
      ) : null}

      {draft.choice === "transfer" ? (
        <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white/[0.03] p-3">
          <label className="block text-xs font-medium text-zinc-600 dark:text-white/60" htmlFor="tender-reference">
            Transfer reference
            <input
              id="tender-reference"
              value={draft.reference}
              maxLength={64}
              onChange={(event) => onChange({ ...draft, reference: event.target.value })}
              placeholder="e.g. TRX-88213"
              className={`${darkInput} mt-1.5 text-sm`}
            />
          </label>
        </div>
      ) : null}

      {draft.choice === "qr" ? (
        <QrTender draft={draft} totalCents={dueCents} currency={currency} disabled={disabled} onChange={onChange} />
      ) : null}

      {draft.choice === "card" && cardTerminal && payments ? (
        <CardTerminalTender
          draft={draft}
          totalCents={dueCents}
          currency={currency}
          disabled={disabled}
          config={payments}
          onChange={onChange}
          verifyManager={verifyManager}
        />
      ) : null}

      {draft.choice === "bnpl" && payments ? (
        <BnplTender
          draft={draft}
          totalCents={dueCents}
          currency={currency}
          disabled={disabled}
          config={payments}
          customer={customer}
          onChange={onChange}
        />
      ) : null}

      {draft.choice === "cheque" ? (
        <div className="grid grid-cols-2 gap-2 rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white/[0.03] p-3">
          <label className="block text-xs font-medium text-zinc-600 dark:text-white/60" htmlFor="cheque-number">
            Cheque number
            <input
              id="cheque-number"
              value={draft.reference}
              maxLength={32}
              onChange={(event) => onChange({ ...draft, reference: event.target.value })}
              placeholder="004512"
              className={`${darkInput} mt-1.5 text-sm tabular-nums`}
            />
          </label>
          <label className="block text-xs font-medium text-zinc-600 dark:text-white/60" htmlFor="cheque-bank">
            Bank
            <input
              id="cheque-bank"
              value={draft.chequeBank}
              maxLength={80}
              onChange={(event) => onChange({ ...draft, chequeBank: event.target.value })}
              placeholder="Emirates NBD"
              className={`${darkInput} mt-1.5 text-sm`}
            />
          </label>
          <label className="col-span-2 block text-xs font-medium text-zinc-600 dark:text-white/60" htmlFor="cheque-date">
            Date on the cheque
            <DateInput
              id="cheque-date"
              value={draft.chequeDate}
              onChange={(event) => onChange({ ...draft, chequeDate: event.target.value })}
              className={`${darkInput} mt-1.5 text-sm [color-scheme:dark]`}
            />
          </label>
          {draft.chequeDate > new Date().toISOString().slice(0, 10) ? (
            <p className="col-span-2 text-xs text-zinc-600 dark:text-white/60">Post-dated cheque: the office tracks it until it clears.</p>
          ) : null}
        </div>
      ) : null}

      {draft.choice === "on_account" ? (
        <div className="space-y-3 rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white/[0.03] p-3">
          <MoneyInput
            id="deposit-paid"
            label="Deposit paid now (optional)"
            value={draft.deposit}
            onChange={(deposit) => onChange({ ...draft, deposit })}
            action={{ label: "None", onClick: () => onChange({ ...draft, deposit: "" }), disabled: draft.deposit === "" }}
          />
          {draft.deposit.trim() !== "" ? (
            <div className="inline-flex rounded-full bg-white dark:bg-zinc-900/60 p-1" role="group" aria-label="Deposit method">
              {depositMethods.map((method) => (
                <button
                  key={method.value}
                  type="button"
                  aria-pressed={draft.depositMethod === method.value}
                  onClick={() => onChange({ ...draft, depositMethod: method.value })}
                  className={`h-10 rounded-full px-4 text-xs font-semibold ${
                    draft.depositMethod === method.value ? "bg-white text-charcoal" : "text-zinc-600 dark:text-white/70 hover:text-zinc-900 dark:hover:text-white"
                  }`}
                >
                  {method.label}
                </button>
              ))}
            </div>
          ) : null}
          {draft.deposit.trim() !== "" && draft.depositMethod === "transfer" ? (
            <input
              aria-label="Deposit reference"
              value={draft.reference}
              maxLength={64}
              onChange={(event) => onChange({ ...draft, reference: event.target.value })}
              placeholder="Cheque or transfer reference"
              className={`${darkInput} text-sm`}
            />
          ) : null}
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <div className="rounded-xl bg-white dark:bg-zinc-900/60 px-3 py-2">
              <dt className="text-[11px] text-zinc-500 dark:text-white/50">Deposit paid</dt>
              <dd className="font-semibold tabular-nums">{formatMoney(plan.paidCents, currency)}</dd>
            </div>
            <div className="rounded-xl bg-white dark:bg-zinc-900/60 px-3 py-2">
              <dt className="text-[11px] text-zinc-500 dark:text-white/50">Balance on credit</dt>
              <dd className="font-semibold tabular-nums text-primary">{formatMoney(plan.onAccountCents, currency)}</dd>
            </div>
          </dl>
          {plan.overLimitCents > 0 || plan.holdReason ? (
            creditApprover ? (
              <p className="flex items-center gap-2 text-xs text-zinc-600 dark:text-white/70">
                <ShieldCheck size={14} aria-hidden="true" className="text-primary" />
                {plan.holdReason ? "Credit hold" : `Over limit by ${formatMoney(plan.overLimitCents, currency)}`}. Approved by{" "}
                {creditApprover}.
              </p>
            ) : (
              <button
                type="button"
                onClick={onRequestCreditApproval}
                className="flex min-h-12 w-full items-center gap-2 rounded-xl border border-primary/60 px-3 py-2 text-left text-xs font-medium text-zinc-900 dark:text-white hover:bg-primary/15"
              >
                <ShieldAlert size={16} aria-hidden="true" className="shrink-0 text-primary" />
                <span>
                  {plan.holdReason
                    ? `On credit hold: ${plan.holdReason}.`
                    : `Over the credit limit by ${formatMoney(plan.overLimitCents, currency)}.`}{" "}
                  Get manager approval to continue.
                </span>
              </button>
            )
          ) : null}
        </div>
      ) : null}

      {extrasApplied ? null : (
        <button
          type="button"
          aria-expanded={showExtras}
          aria-controls="sale-extras"
          disabled={disabled}
          onClick={() => setExtrasOpen((open) => !open)}
          className="flex items-center gap-1.5 rounded-full px-1 text-xs font-semibold text-primary transition-opacity hover:opacity-80 disabled:opacity-40"
        >
          {showExtras ? <Minus size={14} aria-hidden="true" /> : <Plus size={14} aria-hidden="true" />}
          {showExtras ? "Hide" : "Add"} {orList(extraNames)}
        </button>
      )}
      {showExtras ? (
        <div id="sale-extras" className="space-y-2">
          {giftCardsOffered ? (
            <GiftCardRow
              draft={draft}
              totalCents={totalCents - loyaltyCents - tradeInCents}
              currency={currency}
              disabled={disabled}
              onChange={onChange}
            />
          ) : null}
          <StoreCreditRow
            draft={draft}
            totalCents={totalCents - loyaltyCents - tradeInCents - giftCardCents}
            currency={currency}
            disabled={disabled}
            onChange={onChange}
          />
          {coupon?.node}
          {tradeInOffered ? (
            <TradeInRow
              draft={draft}
              products={products}
              cashierId={cashierId}
              customer={customer}
              currency={currency}
              saleCents={totalCents - loyaltyCents}
              disabled={disabled}
              onChange={onChange}
            />
          ) : null}
          {pointsOffered && rules ? (
            <label className="flex h-10 items-center justify-between gap-3 rounded-2xl border border-zinc-200 bg-white/[0.03] px-3 text-sm dark:border-zinc-800">
              <span className="flex min-w-0 items-center gap-2">
                <Sparkles size={15} aria-hidden="true" className="shrink-0 text-primary" />
                <span className="truncate tabular-nums">
                  <span className="font-semibold">Points</span>{" "}
                  <span className="text-xs text-zinc-600 dark:text-white/60">
                    {balance.toLocaleString()} ·{" "}
                    {usingPoints
                      ? `${draft.loyalty!.points.toLocaleString()} used = ${formatMoney(draft.loyalty!.valueCents, currency)}`
                      : `up to ${formatMoney(redeemable * rules.redeem_cents, currency)} off`}
                  </span>
                </span>
              </span>
              <input
                type="checkbox"
                checked={usingPoints}
                disabled={disabled}
                onChange={(event) =>
                  onChange({
                    ...draft,
                    loyalty: event.target.checked ? { points: redeemable, valueCents: redeemable * rules.redeem_cents } : null,
                  })
                }
                className="h-5 w-5 shrink-0 accent-primary"
              />
            </label>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
