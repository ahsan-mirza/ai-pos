import type {
  BillingCatalog,
  BillingCheckout,
  BillingCheckoutStatus,
  BillingQuote,
  GoLiveMode,
  GoLiveResult,
  OpeningStockChoice,
} from "@ai-pos/shared-types";
import { formatMoney } from "@ai-pos/shared-types";
import { Select, billingCycleOption } from "@ai-pos/ui";
import { Rocket } from "lucide-react";
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
          ? "The amount is priced from the company catalog."
          : "Practice tax stamps cannot be used on live invoices.";

  return (
    <Modal
      title="Go live"
      subtitle={subtitle}
      onClose={onClose}
      footer={
        <>
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
        <div className="grid gap-3">
          <label className="text-sm font-medium">
            Package
            <Select
              className="mt-1.5"
              aria-label="Package"
              value={planCode}
              onChange={setPlanCode}
              options={catalog.plans
                .filter((row) => row.active)
                .map((row) => ({
                  value: row.code,
                  label: `${row.name} · ${formatMoney(row.monthly_fils, "AED")} / month · ${row.included_registers} registers`,
                }))}
            />
          </label>
          <label className="text-sm font-medium">
            Billing cycle
            <Select
              className="mt-1.5"
              aria-label="Billing cycle"
              value={cycleCode}
              onChange={setCycleCode}
              options={catalog.cycles
                .filter((row) => row.active)
                .map((row) => billingCycleOption(row.code, row.name, row.discount_bps))}
            />
          </label>
          {catalog.addons.filter((row) => row.active).map((addon) => (
            <label key={addon.id} className="flex items-center justify-between gap-3 text-sm">
              <span>
                <span className="font-medium">{addon.name}</span>
                <span className="mt-0.5 block text-charcoal/60">
                  {addon.monthly_fils ? `${formatMoney(addon.monthly_fils, "AED")} / month` : ""}
                  {addon.one_time_fils ? ` · ${formatMoney(addon.one_time_fils, "AED")} once${addon.refundable ? ", refundable" : ""}` : ""}
                </span>
              </span>
              <input
                className="h-11 w-20 rounded-2xl border border-line px-3 text-right"
                inputMode="numeric"
                value={quantities[addon.code] ?? 0}
                onChange={(event) => setQuantities({ ...quantities, [addon.code]: Math.max(0, Number(event.target.value) || 0) })}
              />
            </label>
          ))}
          {quote ? (
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
              <p className="mt-2 flex justify-between border-t border-line pt-2 font-semibold">
                <span>Due now</span>
                <span className="tabular-nums">{formatMoney(quote.total_fils, quote.currency)}</span>
              </p>
            </div>
          ) : null}
          <ErrorNote message={error} />
        </div>
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
