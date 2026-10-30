import {
  TRADE_IN_GRADE_LABELS,
  formatMoney,
  type ProductUpsert,
  type TradeIn,
  type TradeInCheckResult,
  type TradeInGrade,
  type TradeInPayout,
} from "@ai-pos/shared-types";
import { CheckCircle2, Loader2, ShieldAlert, X } from "lucide-react";
import { useMemo, useState } from "react";
import { env } from "../../config/env";
import type { RegisterCustomer } from "../../lib/tauri";
import { checkIdentifier, createTradeIn, identifierKind } from "./tradeIn";
import { parseCents } from "./tenders";

const input =
  "h-11 w-full rounded-xl border border-zinc-200 bg-white px-3.5 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-primary focus:outline-none focus:ring-4 focus:ring-primary/20 dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-white dark:placeholder:text-white/30";

const checks = [
  { key: "powers_on", label: "Powers on and charges" },
  { key: "screen_ok", label: "Screen and touch work" },
  { key: "body_ok", label: "No cracks or bent frame" },
  { key: "account_removed", label: "iCloud / Google account removed" },
] as const;

interface TradeInModalProps {
  products: ProductUpsert[];
  cashierId: string;
  customer: RegisterCustomer | null;
  currency: string;
  /** Sale total still to collect; sale credit cannot exceed it. */
  saleCents: number;
  onClose: () => void;
  onDone: (tradeIn: TradeIn) => void;
}

export function TradeInModal({ products, cashierId, customer, currency, saleCents, onClose, onDone }: TradeInModalProps) {
  const models = useMemo(
    () => products.filter((product) => product.is_active !== false && product.is_serialized && !product.sku.startsWith("PO-")),
    [products],
  );
  const [query, setQuery] = useState("");
  const [productId, setProductId] = useState<string | null>(null);
  const [identifier, setIdentifier] = useState("");
  const [checkResult, setCheckResult] = useState<TradeInCheckResult | null>(null);
  const [grade, setGrade] = useState<TradeInGrade>("B");
  const [checklist, setChecklist] = useState<Record<(typeof checks)[number]["key"], boolean>>({
    powers_on: true,
    screen_ok: true,
    body_ok: true,
    account_removed: false,
  });
  const [battery, setBattery] = useState("");
  const [seller, setSeller] = useState(customer?.name ?? "");
  const [phone, setPhone] = useState(customer?.phone ?? "");
  const [idNumber, setIdNumber] = useState("");
  const [offer, setOffer] = useState("");
  const [resale, setResale] = useState("");
  const [payout, setPayout] = useState<TradeInPayout>(saleCents > 0 ? "SALE_CREDIT" : "CASH");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const product = models.find((row) => row.id === productId) ?? null;
  const matches = query.trim()
    ? models.filter((row) => `${row.name} ${row.sku} ${row.model_number ?? ""}`.toLowerCase().includes(query.trim().toLowerCase())).slice(0, 6)
    : [];
  const offerCents = parseCents(offer);
  const resaleCents = parseCents(resale);

  async function runCheck() {
    if (identifier.trim().length < 4) return;
    setBusy(true);
    setError(null);
    try {
      setCheckResult(await checkIdentifier(identifierKind(identifier), identifier));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    if (!product) return setError("Choose the model being traded in.");
    if (!checkResult?.ok) return setError("Check the IMEI first.");
    if (!checklist.account_removed) return setError("The seller must remove their iCloud / Google account before you buy the device.");
    if (seller.trim().length < 2 || phone.trim().length < 5 || idNumber.trim().length < 5) {
      return setError("Record the seller's name, phone and Emirates ID or passport number.");
    }
    if (offerCents === null || resaleCents === null) return setError("Enter the offer and the resale price.");
    if (payout === "SALE_CREDIT" && offerCents > saleCents) {
      return setError(`The offer is more than the sale (${formatMoney(saleCents, currency)}). Pay it as cash or store credit instead.`);
    }
    setBusy(true);
    setError(null);
    try {
      onDone(
        await createTradeIn({
          id: crypto.randomUUID(),
          store_id: env.storeId,
          cashier_id: cashierId,
          product_id: product.id,
          identifier_kind: identifierKind(identifier),
          identifier_value: identifier.trim(),
          grade,
          checklist: { ...checklist, battery_pct: battery.trim() === "" ? null : Math.min(100, Number(battery) || 0) },
          seller_name: seller.trim(),
          seller_phone: phone.trim(),
          seller_id_number: idNumber.trim(),
          customer_id: customer?.id ?? null,
          offer_cents: offerCents,
          resale_price_cents: resaleCents,
          payout,
        }),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="trade-in-title">
      <div className="modal-card max-w-2xl">
        <div className="mb-5 flex items-start justify-between gap-3">
          <div>
            <h2 id="trade-in-title" className="text-xl font-semibold">
              Trade-in
            </h2>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">Buy the customer's old device. It goes into stock as a pre-owned unit.</p>
          </div>
          <button type="button" onClick={onClose} className="modal-close" aria-label="Close">
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        <div className="space-y-4">
          {product ? (
            <div className="flex items-center justify-between rounded-2xl bg-zinc-100 px-4 py-3 text-sm dark:bg-white/5">
              <span className="font-semibold">{product.name}</span>
              <button type="button" onClick={() => setProductId(null)} className="text-xs font-semibold text-primary">
                Change
              </button>
            </div>
          ) : (
            <div>
              <label className="text-xs font-medium text-zinc-600 dark:text-white/60" htmlFor="trade-model">
                Model
              </label>
              <input id="trade-model" autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="iPhone 13 128GB" className={`${input} mt-1.5`} />
              {matches.length ? (
                <ul className="mt-1 divide-y divide-zinc-100 overflow-hidden rounded-xl border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-800">
                  {matches.map((row) => (
                    <li key={row.id}>
                      <button
                        type="button"
                        onClick={() => {
                          setProductId(row.id);
                          setResale(((row.price_cents * 0.6) / 100).toFixed(2));
                        }}
                        className="flex w-full justify-between px-3.5 py-2.5 text-left text-sm hover:bg-zinc-50 dark:hover:bg-white/5"
                      >
                        <span>{row.name}</span>
                        <span className="tabular-nums text-zinc-500">new {formatMoney(row.price_cents, currency)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          )}

          <div>
            <label className="text-xs font-medium text-zinc-600 dark:text-white/60" htmlFor="trade-imei">
              IMEI or serial number
            </label>
            <div className="mt-1.5 flex gap-2">
              <input
                id="trade-imei"
                value={identifier}
                onChange={(event) => {
                  setIdentifier(event.target.value);
                  setCheckResult(null);
                }}
                placeholder="Dial *#06# on the phone"
                className={`${input} font-mono`}
              />
              <button
                type="button"
                disabled={busy || identifier.trim().length < 4}
                onClick={() => void runCheck()}
                className="h-11 shrink-0 rounded-xl bg-zinc-900 px-4 text-sm font-semibold text-white disabled:opacity-40 dark:bg-white dark:text-zinc-900"
              >
                Check
              </button>
            </div>
            {checkResult ? (
              <p className={`mt-2 flex items-start gap-2 text-xs ${checkResult.ok ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>
                {checkResult.ok ? <CheckCircle2 size={14} aria-hidden="true" className="mt-0.5 shrink-0" /> : <ShieldAlert size={14} aria-hidden="true" className="mt-0.5 shrink-0" />}
                <span>
                  {checkResult.message}
                  {checkResult.sold_as ? ` Sold as ${checkResult.sold_as}` : ""}
                  {checkResult.sold_here_at ? ` on ${new Date(checkResult.sold_here_at).toLocaleDateString()}` : ""}
                  {checkResult.warranty_status ? ` · warranty ${checkResult.warranty_status.replace("_", " ").toLowerCase()}` : ""}
                </span>
              </p>
            ) : null}
          </div>

          <div>
            <p className="text-xs font-medium text-zinc-600 dark:text-white/60">Condition</p>
            <div className="mt-1.5 grid grid-cols-4 gap-1 rounded-2xl bg-zinc-100 p-1 dark:bg-white/5" role="group" aria-label="Grade">
              {(Object.keys(TRADE_IN_GRADE_LABELS) as TradeInGrade[]).map((value) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={grade === value}
                  onClick={() => setGrade(value)}
                  className={`h-10 rounded-xl text-xs font-semibold ${grade === value ? "bg-primary text-white" : "text-zinc-600 dark:text-white/70"}`}
                >
                  {TRADE_IN_GRADE_LABELS[value]}
                </button>
              ))}
            </div>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {checks.map((item) => (
                <label key={item.key} className="flex items-center gap-2 rounded-xl border border-zinc-200 px-3 py-2 text-sm dark:border-zinc-800">
                  <input
                    type="checkbox"
                    checked={checklist[item.key]}
                    onChange={(event) => setChecklist({ ...checklist, [item.key]: event.target.checked })}
                    className="h-4 w-4 accent-primary"
                  />
                  {item.label}
                </label>
              ))}
            </div>
            <input
              aria-label="Battery health percent"
              inputMode="numeric"
              value={battery}
              onChange={(event) => setBattery(event.target.value.replace(/\D/g, "").slice(0, 3))}
              placeholder="Battery health % (optional)"
              className={`${input} mt-2`}
            />
          </div>

          <div className="grid grid-cols-3 gap-2">
            <input aria-label="Seller name" value={seller} onChange={(event) => setSeller(event.target.value)} placeholder="Seller name" className={input} />
            <input aria-label="Seller phone" value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="Phone" className={input} />
            <input aria-label="Emirates ID or passport" value={idNumber} onChange={(event) => setIdNumber(event.target.value)} placeholder="Emirates ID / passport" className={input} />
          </div>

          <div className="grid grid-cols-2 gap-2">
            <label className="text-xs font-medium text-zinc-600 dark:text-white/60">
              We pay
              <input inputMode="decimal" value={offer} onChange={(event) => setOffer(event.target.value)} placeholder="0.00" className={`${input} mt-1.5 text-lg font-semibold tabular-nums`} />
            </label>
            <label className="text-xs font-medium text-zinc-600 dark:text-white/60">
              Resell for
              <input inputMode="decimal" value={resale} onChange={(event) => setResale(event.target.value)} placeholder="0.00" className={`${input} mt-1.5 text-lg font-semibold tabular-nums`} />
            </label>
          </div>
          {offerCents !== null && resaleCents !== null && resaleCents > 0 ? (
            <p className="text-xs text-zinc-500 tabular-nums dark:text-zinc-400">
              Margin on resale {formatMoney(resaleCents - offerCents, currency)} ({Math.round(((resaleCents - offerCents) / resaleCents) * 100)}%)
            </p>
          ) : null}

          <div className="grid grid-cols-3 gap-1 rounded-2xl bg-zinc-100 p-1 dark:bg-white/5" role="group" aria-label="Pay the customer with">
            {(
              [
                ["SALE_CREDIT", "Off this sale"],
                ["CASH", "Cash from drawer"],
                ["STORE_CREDIT", "Store credit voucher"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                disabled={value === "SALE_CREDIT" && saleCents === 0}
                aria-pressed={payout === value}
                onClick={() => setPayout(value)}
                className={`h-10 rounded-xl text-xs font-semibold disabled:opacity-30 ${payout === value ? "bg-zinc-900 text-white dark:bg-white dark:text-zinc-900" : "text-zinc-600 dark:text-white/70"}`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {error ? (
          <p role="alert" className="mt-4 rounded-xl bg-red-500/10 px-3 py-2.5 text-xs font-medium text-red-700 dark:text-red-300">
            {error}
          </p>
        ) : null}
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="modal-cancel">
            Cancel
          </button>
          <button type="button" disabled={busy} onClick={() => void submit()} className="modal-save inline-flex items-center gap-2">
            {busy ? <Loader2 size={16} aria-hidden="true" className="animate-spin" /> : null}
            Buy device{offerCents ? ` for ${formatMoney(offerCents, currency)}` : ""}
          </button>
        </div>
      </div>
    </div>
  );
}
