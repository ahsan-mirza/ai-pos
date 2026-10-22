import { formatMoney, type Quote } from "@ai-pos/shared-types";
import { Banknote, CalendarClock, CheckCircle2, FileText, Loader2, Package, UserRound, X } from "lucide-react";
import { useEffect, useId, useState, type ReactNode } from "react";
import { useRegisterLayout } from "../../components/RegisterLayout";
import type { RegisterCustomer } from "../../lib/tauri";
import { openQuotePdf } from "./checkout";

const validity = [7, 14, 30] as const;

interface QuoteModalProps {
  totalCents: number;
  pieces: number;
  currency: string;
  customer: RegisterCustomer | null;
  onClose: () => void;
  /** Saves the quote or layaway; resolves with the stored quote or rejects with the API's reason. */
  onSave: (validDays: number, layaway: LayawayDeposit | null) => Promise<Quote>;
}

export interface LayawayDeposit {
  amountCents: number;
  method: "cash" | "card" | "transfer";
}

const depositMethods = [
  { id: "cash", label: "Cash" },
  { id: "card", label: "Card" },
  { id: "transfer", label: "Transfer" },
] as const;

function formatDay(date: Date): string {
  return date.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}

function SummaryRow({ icon, label, children, emphasis = false }: { icon: ReactNode; label: string; children: ReactNode; emphasis?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4 px-4 py-3.5">
      <dt className="flex items-center gap-3 text-sm font-medium text-zinc-700 dark:text-zinc-300">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white text-zinc-700 ring-1 ring-zinc-200 dark:bg-zinc-900 dark:text-zinc-200 dark:ring-zinc-700">
          {icon}
        </span>
        {label}
      </dt>
      <dd
        className={`min-w-0 truncate text-right tabular-nums ${
          emphasis
            ? "text-xl font-bold tracking-tight text-zinc-950 dark:text-white"
            : "text-sm font-semibold text-zinc-900 dark:text-zinc-50"
        }`}
      >
        {children}
      </dd>
    </div>
  );
}

const secondaryButton =
  "inline-flex h-11 items-center justify-center rounded-full border border-zinc-300 bg-white px-6 text-sm font-semibold text-zinc-800 transition-colors hover:bg-zinc-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100 dark:hover:bg-zinc-700";
const primaryButton =
  "inline-flex h-11 items-center justify-center gap-2 rounded-full bg-primary-500 px-6 text-sm font-semibold text-white shadow-lg shadow-primary-500/25 transition-colors hover:bg-primary-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50 focus-visible:ring-offset-2 focus-visible:ring-offset-white disabled:opacity-60 disabled:hover:bg-primary-500 dark:focus-visible:ring-offset-zinc-900";

export function QuoteModal({ totalCents, pieces, currency, customer, onClose, onSave }: QuoteModalProps) {
  const { theme } = useRegisterLayout();
  const titleId = useId();
  const descriptionId = useId();
  const [days, setDays] = useState<number>(7);
  const [kind, setKind] = useState<"QUOTE" | "LAYAWAY">("QUOTE");
  const [deposit, setDeposit] = useState("");
  const [depositMethod, setDepositMethod] = useState<LayawayDeposit["method"]>("cash");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<Quote | null>(null);
  const [opened, setOpened] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  const openPdf = async (quote: Quote) => {
    setBusy(true);
    setError(null);
    try {
      const path = await openQuotePdf(quote);
      setOpened(path ?? "Opened in a new tab.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };

  const depositCents = Math.round(Number.parseFloat(deposit.replace(/,/g, "") || "0") * 100);
  const depositValid = Number.isFinite(depositCents) && depositCents >= 0 && depositCents <= totalCents;
  const layawayBlocked = kind === "LAYAWAY" && (customer === null || !depositValid);

  const save = () => {
    if (layawayBlocked) return;
    setBusy(true);
    setError(null);
    onSave(days, kind === "LAYAWAY" ? { amountCents: depositCents, method: depositMethod } : null)
      .then(async (quote) => {
        setSaved(quote);
        setBusy(false);
        if (kind === "QUOTE") await openPdf(quote);
      })
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : String(caught));
        setBusy(false);
      });
  };

  const customerName = saved
    ? (saved.customer_name ?? "Walk-in customer")
    : customer
      ? (customer.company_name ?? customer.name)
      : "Walk-in customer";
  const units = saved ? saved.items.reduce((sum, item) => sum + item.quantity, 0) : pieces;
  const holdUntil = saved?.quote_expiry_date
    ? new Date(saved.quote_expiry_date)
    : new Date(Date.now() + days * 24 * 60 * 60 * 1000);

  return (
    <div data-theme={theme} className="modal-backdrop bg-black/40 dark:bg-black/60" role="presentation">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        className="modal-card max-w-md bg-white p-0 text-zinc-900 shadow-2xl ring-1 ring-zinc-200 sm:p-0 dark:bg-zinc-900 dark:text-zinc-100 dark:ring-zinc-800"
      >
        <header className="flex items-start gap-3 border-b border-zinc-200 px-6 py-5 dark:border-zinc-800">
          <span
            className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl ${
              saved
                ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                : "bg-primary-500/10 text-primary-600 dark:text-primary-400"
            }`}
          >
            {saved ? <CheckCircle2 size={22} aria-hidden="true" /> : <FileText size={22} aria-hidden="true" />}
          </span>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-lg font-semibold leading-tight text-zinc-950 dark:text-white">
              {saved
                ? `${saved.quote_kind === "LAYAWAY" ? "Layaway" : "Quotation"} ${saved.number} saved`
                : kind === "LAYAWAY"
                  ? "Hold on layaway"
                  : "Generate Quotation"}
            </h2>
            <p id={descriptionId} className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              {saved ? "Stock is reserved and the PDF invoice is ready." : "Reserves stock allocation & exports PDF invoice"}
            </p>
          </div>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            disabled={busy}
            className="-mr-2 -mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40 disabled:opacity-40 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-white"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </header>

        <div className="space-y-6 px-6 py-5">
          <dl className="divide-y divide-zinc-200 overflow-hidden rounded-2xl border border-zinc-200 bg-zinc-50 dark:divide-zinc-800 dark:border-zinc-800 dark:bg-zinc-800/40">
            <SummaryRow icon={<UserRound size={16} aria-hidden="true" />} label="Customer">
              {customerName}
            </SummaryRow>
            <SummaryRow icon={<Package size={16} aria-hidden="true" />} label="Total Units">
              {units}
            </SummaryRow>
            <SummaryRow icon={<Banknote size={16} aria-hidden="true" />} label="Total Amount" emphasis>
              {formatMoney(saved?.total_cents ?? totalCents, currency)}
            </SummaryRow>
          </dl>

          {saved ? null : (
            <section aria-label="Quote or layaway" className="space-y-3">
              <div role="group" className="grid grid-cols-2 gap-1 rounded-xl bg-zinc-100 p-1 dark:bg-zinc-800">
                {(
                  [
                    ["QUOTE", "Proforma quote"],
                    ["LAYAWAY", "Layaway (deposit)"],
                  ] as const
                ).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    aria-pressed={kind === value}
                    disabled={busy}
                    onClick={() => setKind(value)}
                    className={`h-10 rounded-lg text-sm font-semibold transition-colors ${
                      kind === value
                        ? "bg-primary-500 text-white shadow-sm shadow-primary-500/30"
                        : "text-zinc-700 hover:bg-white dark:text-zinc-300 dark:hover:bg-zinc-700"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {kind === "LAYAWAY" ? (
                customer === null ? (
                  <p className="rounded-xl bg-primary-500/10 px-3 py-2 text-sm text-primary-700 dark:text-primary-300">
                    Attach the customer first; layaway goods are released only to them.
                  </p>
                ) : (
                  <div className="grid grid-cols-[1fr_auto] items-end gap-3">
                    <label className="text-sm font-medium" htmlFor={`${titleId}-deposit`}>
                      Deposit now ({currency})
                      <input
                        id={`${titleId}-deposit`}
                        inputMode="decimal"
                        autoComplete="off"
                        value={deposit}
                        onChange={(event) => setDeposit(event.target.value.replace(/[^\d.,]/g, ""))}
                        placeholder="0.00"
                        className="mt-1.5 h-11 w-full rounded-xl border border-zinc-300 bg-white px-3 text-base font-semibold tabular-nums dark:border-zinc-700 dark:bg-zinc-800"
                      />
                    </label>
                    <div role="group" aria-label="Deposit method" className="flex gap-1 rounded-xl bg-zinc-100 p-1 dark:bg-zinc-800">
                      {depositMethods.map((method) => (
                        <button
                          key={method.id}
                          type="button"
                          aria-pressed={depositMethod === method.id}
                          onClick={() => setDepositMethod(method.id)}
                          className={`h-9 rounded-lg px-3 text-xs font-semibold ${
                            depositMethod === method.id ? "bg-zinc-900 text-white dark:bg-white dark:text-zinc-900" : "text-zinc-600"
                          }`}
                        >
                          {method.label}
                        </button>
                      ))}
                    </div>
                    {!depositValid ? (
                      <p className="col-span-2 text-xs text-red-600">The deposit cannot exceed the total.</p>
                    ) : null}
                  </div>
                )
              ) : null}
            </section>
          )}

          <section aria-labelledby={`${titleId}-validity`}>
            <div className="flex items-center justify-between gap-3">
              <h3
                id={`${titleId}-validity`}
                className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-zinc-700 dark:text-zinc-300"
              >
                <CalendarClock size={15} aria-hidden="true" className="text-primary-500" />
                Stock Reservation Validity
              </h3>
              <span className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Held until {formatDay(holdUntil)}</span>
            </div>
            {saved ? null : (
              <div
                role="group"
                aria-label="Stock reservation validity"
                className="mt-3 grid grid-cols-3 gap-1 rounded-xl bg-zinc-100 p-1 dark:bg-zinc-800"
              >
                {validity.map((value) => {
                  const active = days === value;
                  return (
                    <button
                      key={value}
                      type="button"
                      aria-pressed={active}
                      disabled={busy}
                      onClick={() => setDays(value)}
                      className={`h-10 rounded-lg text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50 ${
                        active
                          ? "bg-primary-500 text-white shadow-sm shadow-primary-500/30"
                          : "text-zinc-700 hover:bg-white hover:text-zinc-950 dark:text-zinc-300 dark:hover:bg-zinc-700 dark:hover:text-white"
                      }`}
                    >
                      {value} Days
                    </button>
                  );
                })}
              </div>
            )}
          </section>

          {opened ? (
            <p className="break-all rounded-xl bg-zinc-50 px-3 py-2 text-xs text-zinc-700 ring-1 ring-zinc-200 dark:bg-zinc-800/60 dark:text-zinc-300 dark:ring-zinc-700">
              PDF: {opened}
            </p>
          ) : null}
          {error ? (
            <p
              role="alert"
              className="rounded-xl bg-red-50 px-3 py-2 text-sm font-medium text-red-700 ring-1 ring-red-200 dark:bg-red-500/10 dark:text-red-300 dark:ring-red-500/30"
            >
              {error}
            </p>
          ) : null}
        </div>

        <footer className="flex flex-wrap justify-end gap-3 border-t border-zinc-200 bg-zinc-50 px-6 py-4 dark:border-zinc-800 dark:bg-zinc-900/60">
          {saved ? (
            <>
              <button type="button" onClick={() => void openPdf(saved)} disabled={busy} className={secondaryButton}>
                {busy ? "Opening…" : "Open PDF"}
              </button>
              <button type="button" onClick={onClose} className={primaryButton}>
                New sale
              </button>
            </>
          ) : (
            <>
              <button type="button" onClick={onClose} disabled={busy} className={secondaryButton}>
                Cancel
              </button>
              <button type="button" autoFocus disabled={busy || layawayBlocked} onClick={save} className={primaryButton}>
                {busy ? <Loader2 size={16} aria-hidden="true" className="animate-spin" /> : <FileText size={16} aria-hidden="true" />}
                {busy ? "Saving…" : kind === "LAYAWAY" ? "Hold on layaway" : "Save & Generate PDF"}
              </button>
            </>
          )}
        </footer>
      </div>
    </div>
  );
}
