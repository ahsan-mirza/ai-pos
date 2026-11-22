import {
  CURRENCY_NAMES,
  CURRENCY_REGIONS,
  formatMoney,
  isSupportedCurrency,
  type BusinessSettings,
  type CurrencyCode,
} from "@ai-pos/shared-types";
import { formatDateTime } from "@ai-pos/ui";
import { ArrowLeftRight, Check, Coins } from "lucide-react";
import { useEffect, useState } from "react";
import { RetailRequestError, retailCall } from "../../lib/retailClient";
import { syncBusinessCurrency } from "../checkout/currency";
import { currencySaveEnabled } from "./settingsRoutes";
import { SettingsConfirmationDialog, SettingsSectionCard } from "./settingsUi";

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

function stamp(value: string | null): string {
  if (value === null) return "Unknown time";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Unknown time";
  return formatDateTime(parsed);
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

function statusLabel(status: string): string {
  if (status === "live" || status === "same") return "Live";
  if (status === "cached") return "Cached";
  return "Unavailable";
}

function messageOf(caught: unknown, fallback: string): string {
  if (caught instanceof RetailRequestError) return caught.message;
  return fallback;
}

export function CurrencyCard({
  code,
  selected,
  current,
  example,
  rateLine,
  disabled,
  onSelect,
}: {
  code: CurrencyCode;
  selected: boolean;
  current: boolean;
  example: string | null;
  rateLine: string | null;
  disabled: boolean;
  onSelect: () => void;
}) {
  return (
    <label
      className={`flex min-h-[9.5rem] min-w-0 cursor-pointer flex-col rounded-2xl border p-3 ${
        selected ? "border-primary bg-primary/10" : "border-zinc-200 bg-white hover:bg-zinc-50"
      } ${disabled ? "cursor-not-allowed opacity-70" : ""}`}
    >
      <input type="radio" name="business-currency" value={code} checked={selected} disabled={disabled} onChange={onSelect} className="sr-only" />
      <span className="flex items-start justify-between gap-2">
        <span className="text-lg font-semibold tracking-tight">{code}</span>
        {current ? (
          <span className="shrink-0 rounded-full bg-zinc-900 px-2 py-0.5 text-[0.625rem] font-semibold uppercase tracking-wider text-white">Current</span>
        ) : selected ? (
          <Check size={16} className="shrink-0 text-primary" aria-hidden="true" />
        ) : null}
      </span>
      <span className="mt-1 text-xs text-zinc-600">{CURRENCY_NAMES[code]}</span>
      <span className="text-xs text-zinc-400">{CURRENCY_REGIONS[code]}</span>
      <span className="mt-auto pt-3 text-[0.6875rem] uppercase tracking-wide text-zinc-400">
        {current ? "Reference amount" : "Estimated equivalent"}
      </span>
      <span className="break-words text-sm font-medium tabular-nums">{example ?? "Rate unavailable"}</span>
      {rateLine ? <span className="mt-1 break-words text-[0.6875rem] text-zinc-500">{rateLine}</span> : null}
    </label>
  );
}

export function ExchangeRateStatus({ board, error, onRefresh }: { board: RateBoard | null; error: string | null; onRefresh: () => void }) {
  return (
    <div className="mt-4 flex flex-wrap items-center justify-between gap-2 text-sm text-zinc-600">
      <p>
        {board ? (
          <>
            Rates {statusLabel(board.status).toLowerCase()}
            {board.provider ? ` · ${board.provider}` : ""}
            {board.as_of ? ` · ${stamp(board.as_of)}` : ""}
          </>
        ) : error ? (
          error
        ) : (
          "Loading exchange rates…"
        )}
      </p>
      <button type="button" className="font-semibold text-zinc-900 underline-offset-2 hover:underline" onClick={onRefresh}>
        Refresh rates
      </button>
    </div>
  );
}

export function CurrencyPanel({
  settings,
  canManage,
  onSaved,
}: {
  settings: BusinessSettings | null;
  canManage: boolean;
  onSaved: (next: BusinessSettings) => void;
}) {
  const currency = settings?.currency ?? "AED";
  const [choice, setChoice] = useState<CurrencyCode>(isSupportedCurrency(currency) ? currency : "AED");
  const [confirming, setConfirming] = useState(false);
  const [converting, setConverting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [board, setBoard] = useState<RateBoard | null>(null);
  const [boardError, setBoardError] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const options = (settings?.supported_currencies ?? []).filter(isSupportedCurrency);
  const codes = options.length > 0 ? options : [];
  const canSave = currencySaveEnabled(currency, choice, canManage && settings !== null, busy);

  useEffect(() => {
    if (isSupportedCurrency(currency)) setChoice(currency);
  }, [currency]);

  useEffect(() => {
    let cancelled = false;
    const refresh = refreshTick > 0 ? "&refresh=true" : "";
    void retailCall<RateBoard>(
      "GET",
      `/api/v1/settings/exchange-rates?source=${encodeURIComponent(currency)}&amount_cents=${PREVIEW_CENTS}${refresh}`,
    )
      .then((next) => {
        if (cancelled) return;
        setBoard(next);
        setBoardError(next.status === "unavailable" ? next.message ?? "Exchange rates are unavailable." : null);
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setBoard(null);
        setBoardError(messageOf(caught, "Exchange rates are unavailable."));
      });
    return () => {
      cancelled = true;
    };
  }, [currency, refreshTick]);

  const quotes = new Map((board?.quotes ?? []).map((quote) => [quote.currency, quote]));

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const next = await retailCall<BusinessSettings>("PUT", "/api/v1/settings/currency", { currency: choice });
      onSaved(next);
      void syncBusinessCurrency().catch(() => undefined);
      setNotice(`${CURRENCY_NAMES[choice]} (${choice}) is now the business currency. Prices were not converted.`);
      setConfirming(false);
    } catch (caught) {
      setError(messageOf(caught, "Could not change the currency."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <SettingsSectionCard>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-primary text-white">
            <Coins size={20} aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-2xl font-semibold text-zinc-900">Business currency</h2>
            <p className="text-sm text-zinc-500">Used for every price, register, receipt and report across all stores.</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={!canSave}
            onClick={() => {
              setError(null);
              setNotice(null);
              setConfirming(true);
            }}
            className="box-border inline-flex h-12 items-center justify-center rounded-xl bg-primary px-4 text-sm font-semibold text-white transition-colors hover:bg-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:opacity-40"
          >
            Save currency
          </button>
          <button type="button" onClick={() => setConverting(true)} className="box-border inline-flex h-12 items-center justify-center rounded-xl bg-white px-4 text-sm font-semibold text-zinc-800 ring-1 ring-zinc-300 hover:bg-zinc-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40">
            Convert currency
          </button>
        </div>
      </div>
      <p className="mt-4 text-sm text-zinc-600">
        Current currency: <span className="font-semibold text-zinc-900">{currency}</span>
        {isSupportedCurrency(currency) ? ` · ${CURRENCY_NAMES[currency]}` : ""}
      </p>
      <p className="mt-1 text-xs text-zinc-500">
        {canManage
          ? canSave
            ? `${CURRENCY_NAMES[choice]} is selected and not saved yet.`
            : "Select a different currency to save a change."
          : "Only a business-wide administrator can change the currency. This register can review it."}
      </p>
      {codes.length === 0 ? (
        <p className="mt-4 text-sm text-zinc-500">Supported currencies load with the business settings.</p>
      ) : (
        <div className="mt-4 grid grid-cols-[repeat(auto-fill,minmax(9.25rem,1fr))] gap-3">
          {codes.map((code) => {
            const quote = quotes.get(code);
            const current = code === currency;
            const example =
              current || quote?.status === "same"
                ? formatMoney(PREVIEW_CENTS, code)
                : quote?.converted_cents != null
                  ? formatMoney(quote.converted_cents, code)
                  : null;
            const rateLine = !current && quote?.rate ? `1 ${currency} = ${showRate(quote.rate)} ${code}` : null;
            return (
              <CurrencyCard
                key={code}
                code={code}
                selected={choice === code}
                current={current}
                example={boardError && !current ? null : example}
                rateLine={rateLine}
                disabled={!canManage}
                onSelect={() => setChoice(code)}
              />
            );
          })}
        </div>
      )}
      <ExchangeRateStatus board={board} error={boardError} onRefresh={() => setRefreshTick((value) => value + 1)} />
      {board?.message ? <p className="mt-2 text-sm text-zinc-600">{board.message}</p> : null}
      {notice ? <p role="status" className="mt-4 rounded-2xl bg-zinc-50 px-4 py-3 text-sm text-zinc-700">{notice}</p> : null}
      {error && !confirming ? <p role="alert" className="mt-3 text-sm text-red-700">{error}</p> : null}
      <div className="mt-5 text-sm text-zinc-600">
        <h3 className="font-semibold text-zinc-900">What a currency change does</h3>
        <ul className="mt-2 list-disc space-y-1.5 pl-4">
          <li>Product prices keep their numbers. They are not multiplied by an exchange rate.</li>
          <li>Completed sales and historical financial records retain the currency in which they were recorded.</li>
          <li>Registers pick up the new currency on their next successful sync. Pending transactions using an outdated currency are handled according to existing server validation.</li>
        </ul>
      </div>
      {confirming && isSupportedCurrency(currency) ? (
        <SettingsConfirmationDialog
          title={`Switch the business currency to ${choice}?`}
          subtitle={`${CURRENCY_NAMES[currency]} (${currency}) to ${CURRENCY_NAMES[choice]} (${choice})`}
          busy={busy}
          error={error}
          confirmLabel={busy ? "Saving…" : `Switch to ${choice}`}
          onCancel={() => setConfirming(false)}
          onConfirm={() => void save()}
        >
          <p>
            This does not convert prices. A product at {formatMoney(PREVIEW_CENTS, currency)} stays {formatMoney(PREVIEW_CENTS, choice)} and is only relabelled.
          </p>
          <p>Completed sales, invoices, receipts, returns and repairs keep the currency they were taken in.</p>
          <p>Sales still queued in {currency} stay in that currency. The server rejects a queued sale whose currency no longer matches.</p>
        </SettingsConfirmationDialog>
      ) : null}
      {converting && isSupportedCurrency(currency) ? <Converter businessCurrency={currency} onClose={() => setConverting(false)} /> : null}
    </SettingsSectionCard>
  );
}

function Converter({ businessCurrency, onClose }: { businessCurrency: CurrencyCode; onClose: () => void }) {
  const [amount, setAmount] = useState("1299.50");
  const [source, setSource] = useState<CurrencyCode>(businessCurrency);
  const [target, setTarget] = useState<CurrencyCode>(businessCurrency === "PKR" ? "AED" : "PKR");
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
      void retailCall<ConvertResult>(
        "GET",
        `/api/v1/settings/exchange-rates/convert?source=${source}&target=${target}&amount_cents=${cents}`,
      )
        .then((next) => {
          if (cancelled) return;
          setResult(next);
          setError(null);
        })
        .catch((caught: unknown) => {
          if (cancelled) return;
          setResult(null);
          setError(messageOf(caught, "Exchange rates are unavailable."));
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 400);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [cents, source, target]);

  return (
    <SettingsConfirmationDialog
      title="Convert currency"
      subtitle="An estimate only. This does not change the business currency or any price."
      busy={false}
      error={error}
      confirmLabel="Close"
      onCancel={onClose}
      onConfirm={onClose}
    >
      <label className="block text-sm">
        Amount
        <input value={amount} inputMode="decimal" onChange={(event) => setAmount(event.target.value)} className="mt-1 h-12 w-full rounded-xl border border-zinc-200 px-3 text-base tabular-nums" />
      </label>
      <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-end gap-2">
        <CurrencySelector label="From" value={source} onChange={setSource} />
        <button
          type="button"
          aria-label="Swap currencies"
          className="inline-flex h-12 w-12 items-center justify-center rounded-xl border border-zinc-200"
          onClick={() => {
            setSource(target);
            setTarget(source);
          }}
        >
          <ArrowLeftRight size={16} aria-hidden="true" />
        </button>
        <CurrencySelector label="To" value={target} onChange={setTarget} />
      </div>
      <p className="text-sm text-zinc-600">
        {loading ? "Checking the rate…" : result ? `${formatMoney(result.converted_cents, result.target_currency)} · 1 ${result.source_currency} = ${showRate(result.rate)} ${result.target_currency} · ${statusLabel(result.status)} · ${result.provider}` : "No rate"}
      </p>
    </SettingsConfirmationDialog>
  );
}

export function CurrencySelector({ label, value, onChange }: { label: string; value: CurrencyCode; onChange: (value: CurrencyCode) => void }) {
  return (
    <label className="block text-sm">
      {label}
      <select aria-label={label} value={value} onChange={(event) => { if (isSupportedCurrency(event.target.value)) onChange(event.target.value); }} className="mt-1 h-12 w-full rounded-xl border border-zinc-200 bg-white px-3 text-sm">
        {Object.keys(CURRENCY_NAMES).map((code) => (
          <option key={code} value={code}>{code} · {CURRENCY_NAMES[code as CurrencyCode]}</option>
        ))}
      </select>
    </label>
  );
}
