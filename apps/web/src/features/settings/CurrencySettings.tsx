import {
  CURRENCY_NAMES,
  CURRENCY_REGIONS,
  SUPPORTED_CURRENCIES,
  formatMoney,
  type CurrencyCode,
} from "@ai-pos/shared-types";
import { ArrowLeftRight, Check, Coins, RefreshCw } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { apiGet } from "../../lib/api";
import { useCanManageSettings, useCurrency } from "../../lib/currency";
import { errorMessage } from "../users/api";

const PREVIEW_CENTS = 129_950;

interface RateQuote {
  currency: string;
  rate: string | null;
  inverse_rate: string | null;
  converted_cents: number | null;
  status: "same" | "live" | "cached" | "unavailable";
}

interface RateBoard {
  source_currency: string;
  amount_cents: number;
  provider: string;
  as_of: string | null;
  status: "live" | "cached" | "unavailable";
  message: string | null;
  quotes: RateQuote[];
}

interface ConvertResult {
  source_currency: string;
  target_currency: string;
  amount_cents: number;
  converted_cents: number;
  rate: string;
  inverse_rate: string;
  as_of: string;
  provider: string;
  status: "live" | "cached";
}

function updatedLine(updatedAt: string, by: string | null): string {
  const when = new Date(updatedAt).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  return by ? `Last changed ${when} by ${by}` : `Set ${when}`;
}

function stamp(value: string | null): string {
  if (value === null) return "Unknown time";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Unknown time";
  return parsed.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function showRate(rate: string): string {
  const [whole = "0", fraction = ""] = rate.split(".");
  const trimmed = fraction.replace(/0+$/, "");
  return trimmed === "" ? whole : `${whole}.${trimmed}`;
}

function centsOf(raw: string): number | null {
  const trimmed = raw.trim();
  if (!/^\d+(\.\d{0,2})?$/.test(trimmed)) return null;
  const [whole, fraction = ""] = trimmed.split(".");
  return Number(whole) * 100 + Number((fraction + "00").slice(0, 2));
}

function statusLabel(status: RateQuote["status"] | RateBoard["status"]): string {
  if (status === "live" || status === "same") return "Live";
  if (status === "cached") return "Cached";
  return "Unavailable";
}

export function CurrencySettings() {
  const { currency, settings, loadError, saveCurrency } = useCurrency();
  const canManage = useCanManageSettings();
  const [choice, setChoice] = useState<CurrencyCode>(currency);
  const [confirming, setConfirming] = useState(false);
  const [converting, setConverting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [board, setBoard] = useState<RateBoard | null>(null);
  const [boardError, setBoardError] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const helperId = useId();

  useEffect(() => setChoice(currency), [currency]);

  useEffect(() => {
    let cancelled = false;
    const refresh = refreshTick > 0 ? "&refresh=true" : "";
    apiGet<RateBoard>(`/api/v1/settings/exchange-rates?source=${currency}&amount_cents=${PREVIEW_CENTS}${refresh}`)
      .then((next) => {
        if (cancelled) return;
        setBoard(next);
        setBoardError(next.status === "unavailable" ? next.message : null);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setBoardError(errorMessage(caught, "Exchange rates are unavailable."));
      });
    return () => {
      cancelled = true;
    };
  }, [currency, refreshTick]);

  const options = settings?.supported_currencies ?? [...SUPPORTED_CURRENCIES];
  const changed = choice !== currency;
  const quotes = new Map((board?.quotes ?? []).map((quote) => [quote.currency, quote]));

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const next = await saveCurrency(choice);
      setNotice(`The business now trades in ${CURRENCY_NAMES[next.currency]} (${next.currency}). Prices were not converted.`);
      setConfirming(false);
    } catch (caught) {
      setError(errorMessage(caught, "Could not change the currency."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid items-start gap-4 lg:grid-cols-2">
      <div className="rounded-card border border-line bg-white p-6">
        <h2 className="text-lg font-semibold">Store code</h2>
        <p className="mt-1 text-sm text-charcoal/60">Used to sign in to this business. It is the same for every branch.</p>
        <input
          readOnly
          aria-label="Store code"
          value={settings?.store_code ?? ""}
          className="mt-4 h-12 w-full rounded-2xl border border-line bg-surface px-4 font-mono text-base text-charcoal"
        />
      </div>

      <div className="rounded-card border border-line bg-white p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-accent text-white">
              <Coins size={20} aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <h2 className="text-2xl font-semibold">Business currency</h2>
              <p className="text-sm text-charcoal/60">Used for every price, register, receipt and report across all stores.</p>
            </div>
          </div>
          <div className="flex flex-col items-stretch gap-1 sm:items-end">
            <PrimaryButton
              type="button"
              disabled={!changed || !canManage || busy || settings === null}
              aria-describedby={helperId}
              aria-busy={busy || undefined}
              onClick={() => {
                setError(null);
                setNotice(null);
                setConfirming(true);
              }}
            >
              {busy ? "Saving…" : "Save currency"}
            </PrimaryButton>
            <p id={helperId} className="max-w-xs text-right text-xs text-charcoal/50">
              {canManage
                ? changed
                  ? `${CURRENCY_NAMES[choice]} is selected and not saved yet.`
                  : "Select a different currency to save a change."
                : "Only a business-wide administrator can change the currency."}
            </p>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-charcoal/60">
            Current currency: <span className="font-semibold text-charcoal">{currency}</span>
            {board ? ` · Rates ${statusLabel(board.status).toLowerCase()}` : ""}
            {board?.as_of ? ` · ${stamp(board.as_of)}` : ""}
          </p>
          <GhostButton type="button" onClick={() => setConverting(true)}>
            Convert currency
          </GhostButton>
        </div>

        <fieldset className="mt-4" disabled={!canManage}>
          <legend className="sr-only">Business currency</legend>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(148px,1fr))] gap-3">
            {options.map((code) => {
              const selected = choice === code;
              const current = code === currency;
              const quote = quotes.get(code);
              const example =
                current || quote?.status === "same"
                  ? formatMoney(PREVIEW_CENTS, code)
                  : quote?.converted_cents != null
                    ? formatMoney(quote.converted_cents, code)
                    : null;
              return (
                <label
                  key={code}
                  className={`flex min-h-[9.5rem] min-w-0 cursor-pointer flex-col rounded-2xl border p-3 transition focus-within:ring-2 focus-within:ring-accent ${
                    selected ? "border-accent bg-accent/5" : "border-line hover:bg-surface"
                  } ${canManage ? "" : "cursor-not-allowed opacity-70"}`}
                >
                  <input
                    type="radio"
                    name="business-currency"
                    value={code}
                    checked={selected}
                    disabled={!canManage}
                    onChange={() => setChoice(code)}
                    className="sr-only"
                  />
                  <span className="flex items-start justify-between gap-2">
                    <span className="text-lg font-semibold tracking-tight">{code}</span>
                    {current ? (
                      <span className="shrink-0 rounded-full bg-charcoal px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-white">
                        Current
                      </span>
                    ) : selected ? (
                      <Check size={16} className="shrink-0 text-accent" aria-hidden="true" />
                    ) : null}
                  </span>
                  <span className="mt-1 text-xs text-charcoal/70">{CURRENCY_NAMES[code]}</span>
                  <span className="text-xs text-charcoal/45">{CURRENCY_REGIONS[code]}</span>
                  <span className="mt-auto pt-3 text-[11px] uppercase tracking-wide text-charcoal/45">
                    {current ? "Reference amount" : quote?.status === "unavailable" || quote === undefined ? "Estimate" : "Estimated equivalent"}
                  </span>
                  <span className="break-words text-sm font-medium tabular-nums">
                    {example ?? (boardError ? "Rate unavailable" : "Loading rate…")}
                  </span>
                  {!current && quote?.rate ? (
                    <span className="mt-1 break-words text-[11px] text-charcoal/50">
                      1 {currency} = {showRate(quote.rate)} {code}
                    </span>
                  ) : null}
                </label>
              );
            })}
          </div>
        </fieldset>

        <p className="mt-4 text-xs text-charcoal/50">
          {board?.provider ? `${board.provider}. ` : ""}
          {board?.status === "cached" ? "Cached rate. " : board?.status === "live" ? "Live rate. " : ""}
          Choosing a card does not convert prices. Use Convert currency for an estimate.
          <button type="button" className="ml-2 font-medium text-charcoal underline-offset-2 hover:underline" onClick={() => setRefreshTick((value) => value + 1)}>
            Refresh rates
          </button>
        </p>
        {board?.message ? <p className="mt-2 text-sm text-charcoal/70">{board.message}</p> : null}
        {notice ? (
          <p role="status" className="mt-4 rounded-2xl bg-surface px-4 py-3 text-sm text-charcoal/80">
            {notice}
          </p>
        ) : null}
        <ErrorNote message={confirming ? loadError : (error ?? loadError ?? boardError)} />
        <div className="mt-4 rounded-2xl bg-charcoal p-4 text-white">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-white/50">In use</p>
          <p className="mt-1 text-2xl font-semibold tracking-tight">{currency}</p>
          <p className="text-sm text-white/70">{CURRENCY_NAMES[currency]}</p>
          <p className="mt-2 text-xs text-white/50">{settings ? updatedLine(settings.updated_at, settings.updated_by_name) : "Loading…"}</p>
        </div>
        <div className="mt-4 text-sm text-charcoal/70">
          <h3 className="font-semibold text-charcoal">What a currency change does</h3>
          <ul className="mt-2 list-disc space-y-1.5 pl-4">
            <li>Product prices keep their numbers. They are not multiplied by an exchange rate.</li>
            <li>Completed sales, receipts, invoices, returns and repairs keep the currency they were taken in.</li>
            <li>Registers pick up the new currency on their next sync. Sales still queued in {currency} are rejected until those registers sync.</li>
          </ul>
        </div>
      </div>

      {confirming ? (
        <Modal
          title={`Switch the business currency to ${choice}?`}
          subtitle={`${CURRENCY_NAMES[currency]} (${currency}) to ${CURRENCY_NAMES[choice]} (${choice})`}
          onClose={() => (busy ? undefined : setConfirming(false))}
          footer={
            <>
              <GhostButton type="button" disabled={busy} onClick={() => setConfirming(false)}>
                Cancel
              </GhostButton>
              <PrimaryButton type="button" disabled={busy} aria-busy={busy || undefined} onClick={() => void save()}>
                {busy ? "Saving…" : `Switch to ${choice}`}
              </PrimaryButton>
            </>
          }
        >
          <div className="space-y-3 text-sm text-charcoal">
            <p>
              This does not convert prices. A product at{" "}
              <span className="font-semibold tabular-nums">{formatMoney(PREVIEW_CENTS, currency)}</span> stays{" "}
              <span className="font-semibold tabular-nums">{formatMoney(PREVIEW_CENTS, choice)}</span> and is only relabelled.
              That is not an exchange-rate conversion.
            </p>
            <p>Completed sales, invoices, receipts, returns and repairs keep the currency they were taken in. Reports do not add those totals into {choice}.</p>
            <p>Sync every register first. Sales still queued in {currency} are rejected after the switch, and this change is blocked while a register reports unsynced sales.</p>
          </div>
          <ErrorNote message={error} />
        </Modal>
      ) : null}
      {converting ? (
        <Converter
          businessCurrency={currency}
          onClose={() => setConverting(false)}
        />
      ) : null}
    </div>
  );
}

function Converter({ businessCurrency, onClose }: { businessCurrency: CurrencyCode; onClose: () => void }) {
  const [amount, setAmount] = useState("1299.50");
  const [source, setSource] = useState<CurrencyCode>(businessCurrency);
  const [target, setTarget] = useState<CurrencyCode>(businessCurrency === "PKR" ? "AED" : "PKR");
  const [refresh, setRefresh] = useState(false);
  const [result, setResult] = useState<ConvertResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const cents = centsOf(amount);

  useEffect(() => {
    if (cents === null) {
      setResult(null);
      setError("Enter an amount with up to 2 decimal places.");
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      setLoading(true);
      const flag = refresh ? "&refresh=true" : "";
      apiGet<ConvertResult>(
        `/api/v1/settings/exchange-rates/convert?source=${source}&target=${target}&amount_cents=${cents}${flag}`,
      )
        .then((next) => {
          if (cancelled) return;
          setResult(next);
          setError(null);
          setRefresh(false);
        })
        .catch((caught: unknown) => {
          if (cancelled) return;
          setResult(null);
          setError(errorMessage(caught, "Exchange rates are unavailable."));
          setRefresh(false);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 400);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [cents, source, target, refresh]);

  return (
    <Modal
      title="Convert currency"
      subtitle="An estimate only. This does not change the business currency or any price."
      onClose={onClose}
      width="lg"
      footer={
        <>
          <GhostButton type="button" onClick={() => setRefresh(true)} disabled={loading || cents === null}>
            <RefreshCw size={16} className="mr-2" aria-hidden="true" />
            Refresh rate
          </GhostButton>
          <PrimaryButton type="button" onClick={onClose}>
            Close
          </PrimaryButton>
        </>
      }
    >
      <div className="grid gap-3">
        <label className="block text-sm">
          Amount
          <input
            inputMode="decimal"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            className="mt-1 h-12 w-full rounded-2xl border border-line bg-white px-4 text-base tabular-nums focus:border-accent focus:outline-none"
          />
        </label>
        <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-end gap-2">
          <CurrencySelect label="From" value={source} onChange={setSource} />
          <button
            type="button"
            aria-label="Swap currencies"
            className="inline-flex h-12 w-12 items-center justify-center rounded-2xl border border-line hover:bg-surface"
            onClick={() => {
              setSource(target);
              setTarget(source);
            }}
          >
            <ArrowLeftRight size={16} aria-hidden="true" />
          </button>
          <CurrencySelect label="To" value={target} onChange={setTarget} />
        </div>
      </div>
      <dl className="mt-5 space-y-3 rounded-2xl bg-surface p-4 text-sm">
        <div className="flex flex-wrap justify-between gap-2">
          <dt className="text-charcoal/60">Amount</dt>
          <dd className="font-medium tabular-nums">{cents === null ? "—" : formatMoney(cents, source)}</dd>
        </div>
        <div className="flex flex-wrap justify-between gap-2">
          <dt className="text-charcoal/60">Exchange rate</dt>
          <dd className="font-medium tabular-nums">
            {result ? `1 ${result.source_currency} = ${showRate(result.rate)} ${result.target_currency}` : "—"}
          </dd>
        </div>
        <div className="flex flex-wrap justify-between gap-2">
          <dt className="text-charcoal/60">Estimated equivalent</dt>
          <dd className="text-base font-semibold tabular-nums">
            {result ? formatMoney(result.converted_cents, result.target_currency) : "—"}
          </dd>
        </div>
        <div className="flex flex-wrap justify-between gap-2 text-charcoal/60">
          <dt>Updated</dt>
          <dd>
            {loading ? "Checking the rate…" : result ? `${stamp(result.as_of)} · ${statusLabel(result.status)} · ${result.provider}` : "No rate"}
          </dd>
        </div>
      </dl>
      <ErrorNote message={error} />
    </Modal>
  );
}

function CurrencySelect({
  label,
  value,
  onChange,
}: {
  label: string;
  value: CurrencyCode;
  onChange: (value: CurrencyCode) => void;
}) {
  return (
    <label className="block text-sm">
      {label}
      <select
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value as CurrencyCode)}
        className="mt-1 h-12 w-full rounded-2xl border border-line bg-white px-3 text-sm focus:border-accent focus:outline-none"
      >
        {SUPPORTED_CURRENCIES.map((code) => (
          <option key={code} value={code}>
            {code} · {CURRENCY_NAMES[code]}
          </option>
        ))}
      </select>
    </label>
  );
}
