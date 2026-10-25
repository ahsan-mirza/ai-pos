import type {
  BillingAddon,
  BillingCatalog,
  BillingCheckout,
  BillingCheckoutStatus,
  BillingQuote,
  GoLiveMode,
  GoLiveResult,
  OpeningStockChoice,
} from "@ai-pos/shared-types";
import { formatMoney } from "@ai-pos/shared-types";
import { Minus, Plus, Rocket, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { ApiRequestError, apiGet, apiPost } from "../../lib/api";

const KEEP_CLEARED = [
  "Every practice sale, return, order, bill, shift and journal entry",
  "Sample products and sample customers",
  "Practice tax signing keys and the invoice chain",
];
const KEEP_KEPT = [
  "Your products, prices, categories and tax settings",
  "Staff, registers, floor plan and kitchen stations",
  "Customers you added yourself",
];
const FRESH_CLEARED = [
  "Products, categories, customers, suppliers and promotions",
  "Floor plan, kitchen stations, registers and extra staff",
  "Practice tax signing keys and the invoice chain",
];
const FRESH_KEPT = ["Your business name, tax number and currency", "Your own login", "The setup wizard, so you can start again"];

type Step = "mode" | "stock" | "package" | "confirm";

function asResult(status: BillingCheckoutStatus, fallbackMode: GoLiveMode): GoLiveResult {
  const raw = status.result;
  return {
    live_at: raw?.live_at ?? new Date().toISOString(),
    mode: raw?.mode === "fresh" || raw?.mode === "keep" ? raw.mode : fallbackMode,
    opening_stock: raw?.opening_stock === "keep" ? "keep" : "reset",
    sales_removed: raw?.sales_removed ?? 0,
    sample_products_removed: raw?.sample_products_removed ?? 0,
    sample_customers_removed: raw?.sample_customers_removed ?? 0,
  };
}

export function GoLiveModal({
  storeName,
  trn,
  taxAuthority,
  openingStockUnits,
  onClose,
  onLive,
}: {
  storeName: string;
  trn: string | null;
  taxAuthority: string;
  openingStockUnits: number;
  onClose: () => void;
  onLive: (result: GoLiveResult) => void;
}) {
  const [stepIndex, setStepIndex] = useState(0);
  const [mode, setMode] = useState<GoLiveMode>("keep");
  const [openingStock, setOpeningStock] = useState<OpeningStockChoice>("keep");
  const [taxAck, setTaxAck] = useState(false);
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GoLiveResult | null>(null);
  const [catalog, setCatalog] = useState<BillingCatalog | null | undefined>(undefined);
  const [planCode, setPlanCode] = useState("");
  const [cycleCode, setCycleCode] = useState("");
  const [quantities, setQuantities] = useState<Record<string, number>>({});
  const [quote, setQuote] = useState<BillingQuote | null>(null);
  const [watching, setWatching] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiGet<BillingCatalog>("/api/v1/billing/catalog")
      .then((found) => {
        if (cancelled) return;
        setCatalog(found);
        const plan = found.plans.find((row) => row.code === "STANDARD" && row.active) ?? found.plans.find((row) => row.active);
        const cycle = found.cycles.find((row) => row.code === "MONTHLY" && row.active) ?? found.cycles.find((row) => row.active);
        setPlanCode(plan?.code ?? "");
        setCycleCode(cycle?.code ?? "");
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        if (caught instanceof ApiRequestError && (caught.code === "billing_unavailable" || caught.status === 404)) {
          setCatalog(null);
          return;
        }
        setCatalog(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const steps: Step[] = ["mode"];
  if (mode === "keep") steps.push("stock");
  if (catalog) steps.push("package");
  steps.push("confirm");
  const step = steps[Math.min(stepIndex, steps.length - 1)] ?? "confirm";
  const matches = storeName !== "" && confirm.trim().toLowerCase() === storeName.trim().toLowerCase();
  const units = openingStockUnits.toLocaleString();
  const addons = useMemo(
    () =>
      (catalog?.addons ?? [])
        .filter((row) => row.active && (quantities[row.code] ?? 0) > 0)
        .map((row) => ({ code: row.code, quantity: quantities[row.code] ?? 0 })),
    [catalog, quantities],
  );

  useEffect(() => {
    if (!catalog || step !== "package" || !planCode || !cycleCode) return;
    const timer = window.setTimeout(() => {
      apiPost<BillingQuote>("/api/v1/billing/quote", { plan_code: planCode, cycle_code: cycleCode, addons })
        .then(setQuote)
        .catch((caught: unknown) => setError(caught instanceof ApiRequestError ? caught.message : "Could not price this package."));
    }, 200);
    return () => window.clearTimeout(timer);
  }, [catalog, step, planCode, cycleCode, addons]);

  useEffect(() => {
    if (!watching) return;
    const timer = window.setInterval(() => {
      apiGet<BillingCheckoutStatus>(`/api/v1/billing/checkout/${watching}`)
        .then((status) => {
          if (status.status === "paid") {
            setWatching(null);
            setResult(asResult(status, mode));
          } else if (status.status === "failed") {
            setWatching(null);
            setError(status.error ?? "Payment did not complete.");
            setBusy(false);
          }
        })
        .catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [watching, mode]);

  const goLive = async () => {
    setBusy(true);
    setError(null);
    try {
      if (!catalog) {
        setResult(
          await apiPost<GoLiveResult>("/api/v1/onboarding/go-live", {
            confirm,
            mode,
            opening_stock: mode === "keep" ? openingStock : "reset",
            tax_acknowledged: true,
          }),
        );
        return;
      }
      const checkout = await apiPost<BillingCheckout>("/api/v1/billing/checkout", {
        plan_code: planCode,
        cycle_code: cycleCode,
        addons,
        mode,
        opening_stock: mode === "keep" ? openingStock : "reset",
        confirm,
        tax_acknowledged: true,
      });
      if (checkout.mode === "simulator") {
        const status = await apiPost<BillingCheckoutStatus>(`/api/v1/billing/checkout/${checkout.checkout_id}/simulate`, {});
        if (status.status === "failed") {
          setError(status.error ?? "The recorded payment could not take the store live.");
          return;
        }
        setResult(asResult(status, mode));
        return;
      }
      if (checkout.url) window.open(checkout.url, "_blank", "noopener,noreferrer");
      setWatching(checkout.checkout_id);
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Could not go live.");
    } finally {
      setBusy(false);
    }
  };

  if (result !== null) {
    const stockNote =
      result.opening_stock === "reset"
        ? " Opening stock is zero, ready for a physical count."
        : " Opening stock you kept is still on the shelf.";
    return (
      <Modal
        title="You are live"
        subtitle={
          result.mode === "fresh" ? "The setup wizard is open on an empty store." : "The next sale is invoice number 1."
        }
        onClose={() => onLive(result)}
        footer={<PrimaryButton onClick={() => onLive(result)}>Start selling</PrimaryButton>}
      >
        <div className="flex items-center gap-4 rounded-2xl bg-emerald-50 p-4 text-sm text-emerald-900">
          <Rocket size={22} aria-hidden="true" className="shrink-0" />
          <p>
            Cleared {result.sales_removed} practice sale{result.sales_removed === 1 ? "" : "s"},{" "}
            {result.sample_products_removed} sample item{result.sample_products_removed === 1 ? "" : "s"} and{" "}
            {result.sample_customers_removed} sample customer{result.sample_customers_removed === 1 ? "" : "s"}.
            {result.mode === "keep" ? stockNote : " Practice configuration was removed."}
          </p>
        </div>
      </Modal>
    );
  }

  const subtitle =
    step === "mode"
      ? "Choose what to carry into the live store. This can only be done once."
      : step === "stock"
        ? "Opening stock decides day-one inventory value."
        : step === "package"
          ? "Choose a package, then add the counter kit if you want hardware with it."
          : "Practice tax stamps cannot be used on live invoices.";

  return (
    <Modal
      title="Go live"
      subtitle={subtitle}
      width={step === "package" ? "xl" : "md"}
      onClose={onClose}
      footer={
        <>
          {step === "package" && quote ? (
            <p className="mr-auto text-sm">
              <span className="text-charcoal/60">Due now</span>
              <span className="ml-2 text-base font-semibold tabular-nums">{formatMoney(quote.total_fils, quote.currency)}</span>
            </p>
          ) : null}
          <GhostButton onClick={stepIndex === 0 ? onClose : () => setStepIndex(stepIndex - 1)} disabled={busy}>
            {stepIndex === 0 ? "Not yet" : "Back"}
          </GhostButton>
          {step !== "confirm" ? (
            <PrimaryButton onClick={() => setStepIndex(stepIndex + 1)} disabled={catalog === undefined || (step === "package" && !quote)}>
              Continue
            </PrimaryButton>
          ) : (
            <PrimaryButton onClick={() => void goLive()} disabled={!matches || !taxAck || busy || watching !== null}>
              {watching ? "Waiting for payment…" : busy ? "Going live…" : catalog ? "Pay and go live" : "Go live"}
            </PrimaryButton>
          )}
        </>
      }
    >
      {step === "mode" ? (
        <div className="grid gap-3">
          <Choice
            selected={mode === "keep"}
            title="Keep configuration"
            detail="Carry over your catalog, prices, staff, layout and registers. Practice sales are removed."
            onSelect={() => setMode("keep")}
          />
          <Choice
            selected={mode === "fresh"}
            title="Start fresh"
            detail="Drop the practice setup and open the wizard again on an empty live store."
            onSelect={() => setMode("fresh")}
          />
          <Lists cleared={mode === "keep" ? KEEP_CLEARED : FRESH_CLEARED} kept={mode === "keep" ? KEEP_KEPT : FRESH_KEPT} />
        </div>
      ) : null}
      {step === "stock" ? (
        <div className="grid gap-3">
          <Choice
            selected={openingStock === "keep"}
            title={`Keep opening stock (${units} units)`}
            detail="Practice sales are put back. Imported and counted quantities stay as the day-one baseline."
            onSelect={() => setOpeningStock("keep")}
          />
          <Choice
            selected={openingStock === "reset"}
            title="Reset to zero"
            detail="On-hand and serials go to zero so you can count the shelf. Reorder levels and shelf locations stay."
            onSelect={() => setOpeningStock("reset")}
          />
        </div>
      ) : null}
      {step === "package" && catalog ? (
        <PackageStep
          catalog={catalog}
          planCode={planCode}
          cycleCode={cycleCode}
          quantities={quantities}
          quote={quote}
          error={error}
          onPlan={setPlanCode}
          onCycle={setCycleCode}
          onQuantity={(code, quantity) => setQuantities({ ...quantities, [code]: quantity })}
        />
      ) : null}
      {step === "confirm" ? (
        <div>
          <p className="rounded-2xl bg-surface px-4 py-3 text-sm text-charcoal/70">
            Tax number kept: <strong className="font-semibold text-charcoal">{trn?.trim() || "none on file"}</strong>.
            Practice signing keys and the invoice chain are destroyed.
            {taxAuthority === "zatca"
              ? " Saudi invoices stay validated locally until the production tax portal is connected."
              : " UAE tax invoices are printed from the business profile, not from a practice stamp."}
          </p>
          <label className="mt-4 flex items-start gap-3 text-sm">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={taxAck}
              onChange={(event) => setTaxAck(event.target.checked)}
            />
            <span>I understand practice tax stamps will not be used on live invoices.</span>
          </label>
          <div className="mt-5">
            <TextField
              label={`Type "${storeName}" to confirm`}
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              autoComplete="off"
            />
          </div>
          <ErrorNote message={error} />
        </div>
      ) : null}
    </Modal>
  );
}

function Choice({
  selected,
  title,
  detail,
  onSelect,
}: {
  selected: boolean;
  title: string;
  detail: string;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`rounded-2xl border px-4 py-3 text-left text-sm ${
        selected ? "border-charcoal bg-surface" : "border-line bg-white hover:bg-surface"
      }`}
    >
      <p className="font-semibold">{title}</p>
      <p className="mt-1 text-charcoal/70">{detail}</p>
    </button>
  );
}

const KIT = [
  { src: "/hardware/pos-terminal.jpg", name: "Touchscreen till", detail: "Cashier screen" },
  { src: "/hardware/receipt-printer.jpg", name: "Receipt printer", detail: "Prints the slip" },
  { src: "/hardware/barcode-scanner.jpg", name: "Barcode scanner", detail: "Scans an item" },
  { src: "/hardware/cash-drawer.jpg", name: "Cash drawer", detail: "Counted each shift" },
  { src: "/hardware/card-terminal.jpg", name: "Card reader", detail: "Chip, tap and PIN" },
] as const;

function PackageStep({
  catalog,
  planCode,
  cycleCode,
  quantities,
  quote,
  error,
  onPlan,
  onCycle,
  onQuantity,
}: {
  catalog: BillingCatalog;
  planCode: string;
  cycleCode: string;
  quantities: Record<string, number>;
  quote: BillingQuote | null;
  error: string | null;
  onPlan: (code: string) => void;
  onCycle: (code: string) => void;
  onQuantity: (code: string, quantity: number) => void;
}) {
  const plans = catalog.plans.filter((row) => row.active).sort((a, b) => a.sort_order - b.sort_order);
  const cycles = catalog.cycles.filter((row) => row.active).sort((a, b) => a.sort_order - b.sort_order);
  const addons = catalog.addons.filter((row) => row.active).sort((a, b) => a.sort_order - b.sort_order);
  const plan = plans.find((row) => row.code === planCode);

  return (
    <div className="grid gap-6">
      <section>
        <h3 className="text-sm font-semibold">Package</h3>
        <div className="mt-2 grid gap-3 sm:grid-cols-3">
          {plans.map((row) => {
            const selected = row.code === planCode;
            return (
              <button
                key={row.id}
                type="button"
                aria-pressed={selected}
                onClick={() => onPlan(row.code)}
                className={`rounded-2xl border px-4 py-3 text-left ${
                  selected ? "border-accent bg-accent/5 ring-2 ring-accent" : "border-line bg-white hover:bg-surface"
                }`}
              >
                <p className="text-sm font-semibold">{row.name}</p>
                <p className="mt-1 text-lg font-semibold tabular-nums">
                  {formatMoney(row.monthly_fils, "AED")}
                  <span className="text-sm font-normal text-charcoal/60"> / month</span>
                </p>
                <p className="mt-1 text-sm text-charcoal/70">
                  {row.included_registers} {row.included_registers === 1 ? "register" : "registers"} included
                </p>
              </button>
            );
          })}
        </div>
      </section>
      <section>
        <h3 className="text-sm font-semibold">Billing cycle</h3>
        <div className="mt-2 flex flex-wrap gap-2">
          {cycles.map((row) => {
            const selected = row.code === cycleCode;
            return (
              <button
                key={row.id}
                type="button"
                aria-pressed={selected}
                onClick={() => onCycle(row.code)}
                className={`inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium ${
                  selected ? "border-accent bg-accent/5 text-charcoal ring-2 ring-accent" : "border-line bg-white hover:bg-surface"
                }`}
              >
                {row.name}
                {row.discount_bps > 0 ? (
                  <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
                    Save {row.discount_bps / 100}%
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>
      </section>
      <section className="grid gap-3">
        <h3 className="text-sm font-semibold">Hardware</h3>
        {addons.map((addon) => (
          <AddonCard
            key={addon.id}
            addon={addon}
            quantity={quantities[addon.code] ?? 0}
            registers={plan?.included_registers ?? 0}
            planName={plan?.name ?? "your package"}
            onQuantity={(quantity) => onQuantity(addon.code, quantity)}
          />
        ))}
      </section>
      {quote ? <QuoteSummary quote={quote} /> : null}
      <ErrorNote message={error} />
    </div>
  );
}

function AddonCard({
  addon,
  quantity,
  registers,
  planName,
  onQuantity,
}: {
  addon: BillingAddon;
  quantity: number;
  registers: number;
  planName: string;
  onQuantity: (quantity: number) => void;
}) {
  const kind =
    addon.code === "hardware_lease"
      ? "lease"
      : addon.code === "equipment_protection"
        ? "protect"
        : addon.code === "extra_register"
          ? "register"
          : "plain";
  const chosen = quantity > 0;
  return (
    <article className={`rounded-2xl border p-4 ${chosen ? "border-accent bg-accent/5" : "border-line bg-white"}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold">{addon.name}</p>
          <p className="mt-0.5 text-sm text-charcoal/70">{addonPrice(addon)}</p>
        </div>
        <QtyStepper label={addon.name} value={quantity} onChange={onQuantity} />
      </div>
      {kind === "lease" ? (
        <>
          <p className="mt-3 text-sm text-charcoal/70">Each kit is rented and includes the pieces below. The one-time amount is a deposit you get back.</p>
          <ul className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-5">
            {KIT.map((piece) => (
              <li key={piece.name} className="overflow-hidden rounded-2xl border border-line bg-white">
                <img src={piece.src} alt={piece.name} className="aspect-square w-full object-cover" />
                <p className="px-2 pb-2 pt-1.5 text-xs font-semibold">{piece.name}</p>
                <p className="px-2 pb-2 text-xs text-charcoal/60">{piece.detail}</p>
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {kind === "protect" ? (
        <div className="mt-3 flex gap-3">
          <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-accent" aria-hidden />
          <div>
            <p className="text-sm text-charcoal/70">Covers the leased till, printer, scanner, drawer and card reader: drops, spills, and a replacement while a piece is repaired.</p>
            <div className="mt-3 flex gap-2">
              {KIT.map((piece) => (
                <img key={piece.name} src={piece.src} alt="" className="h-14 w-14 rounded-xl border border-line object-cover" />
              ))}
            </div>
          </div>
        </div>
      ) : null}
      {kind === "register" ? (
        <div className="mt-3 flex gap-3">
          <img src="/hardware/pos-terminal.jpg" alt="Extra touchscreen till" className="h-28 w-28 shrink-0 rounded-2xl border border-line object-cover" />
          <p className="text-sm text-charcoal/70">
            Another till beyond the {registers} {registers === 1 ? "register" : "registers"} already included in {planName}. Same counter screen as the kit.
          </p>
        </div>
      ) : null}
      {kind === "plain" && addon.description ? <p className="mt-3 text-sm text-charcoal/70">{addon.description}</p> : null}
    </article>
  );
}

function addonPrice(addon: BillingAddon): string {
  const parts: string[] = [];
  if (addon.monthly_fils) parts.push(`${formatMoney(addon.monthly_fils, "AED")} / month`);
  if (addon.one_time_fils) {
    parts.push(`${formatMoney(addon.one_time_fils, "AED")} once${addon.refundable ? ", refundable" : ""}`);
  }
  return parts.join(" · ") || addon.description;
}

function QtyStepper({ label, value, onChange }: { label: string; value: number; onChange: (next: number) => void }) {
  return (
    <div className="inline-flex items-center rounded-full border border-line bg-white">
      <button
        type="button"
        className="grid h-11 w-11 place-items-center rounded-full hover:bg-surface disabled:opacity-30"
        aria-label={`Remove one ${label}`}
        disabled={value <= 0}
        onClick={() => onChange(value - 1)}
      >
        <Minus className="h-4 w-4" />
      </button>
      <span className="w-8 text-center text-sm font-semibold tabular-nums">{value}</span>
      <button
        type="button"
        className="grid h-11 w-11 place-items-center rounded-full hover:bg-surface"
        aria-label={`Add one ${label}`}
        onClick={() => onChange(Math.min(value + 1, 20))}
      >
        <Plus className="h-4 w-4" />
      </button>
    </div>
  );
}

function QuoteSummary({ quote }: { quote: BillingQuote }) {
  return (
    <div className="rounded-2xl bg-surface px-4 py-3 text-sm">
      <ul className="space-y-1">
        {quote.lines.map((line) => (
          <li key={line.code} className="flex justify-between gap-3">
            <span>
              {line.label}
              {line.quantity > 1 ? ` × ${line.quantity}` : ""}
              {line.refundable ? " · refundable" : ""}
            </span>
            <span className="tabular-nums">{formatMoney(line.amount_fils, quote.currency)}</span>
          </li>
        ))}
      </ul>
      <p className="mt-2 flex justify-between border-t border-line pt-2 text-base font-semibold">
        <span>Due now</span>
        <span className="tabular-nums">{formatMoney(quote.total_fils, quote.currency)}</span>
      </p>
    </div>
  );
}

function Lists({ cleared, kept }: { cleared: string[]; kept: string[] }) {
  return (
    <div className="grid gap-4 text-sm sm:grid-cols-2">
      <div>
        <p className="font-semibold">Cleared</p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-charcoal/70">
          {cleared.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </div>
      <div>
        <p className="font-semibold">Kept</p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-charcoal/70">
          {kept.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
