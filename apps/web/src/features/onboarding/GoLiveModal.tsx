import type {
  BillingAddon,
  BillingCatalog,
  BillingCheckout,
  BillingCheckoutStatus,
  BillingPlan,
  BillingQuote,
  HardwarePick,
  GoLiveMode,
  GoLiveResult,
  OpeningStockChoice,
} from "@ai-pos/shared-types";
import { formatMoney } from "@ai-pos/shared-types";
import { useLocale } from "@ai-pos/ui";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Minus, Plus, Rocket, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { WizardStepper } from "../../components/ui/WizardStepper";
import { ApiRequestError, apiGet, apiPost, apiUpload } from "../../lib/api";

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

type Step = "plan" | "cycle" | "extras" | "data" | "confirm";

/** Steps on screen. Billing and hardware exist only for a payable plan, so Free and Enterprise omit them. */
export function goLiveSteps(hasCatalog: boolean, payable: boolean): Step[] {
  const steps: Step[] = [];
  if (hasCatalog) steps.push("plan");
  if (payable) steps.push("cycle", "extras");
  steps.push("data", "confirm");
  return steps;
}

const CURRENT_CODES = new Set(["FREE", "GROWTH", "PRO_AI", "ENTERPRISE"]);

function planFamily(plan: BillingPlan): "current" | "legacy" {
  if (plan.catalog_family === "current" || plan.catalog_family === "legacy") return plan.catalog_family;
  return CURRENT_CODES.has(plan.code) ? "current" : "legacy";
}

function isCustom(plan: BillingPlan | undefined): boolean {
  return plan?.custom_pricing === true || plan?.code === "ENTERPRISE";
}

function isFreePlan(plan: BillingPlan | undefined): boolean {
  return plan?.code === "FREE";
}

function cycleDiscountBps(plan: BillingPlan | undefined, cycleCode: string, cycleBps: number, catalog: BillingCatalog): number {
  if (plan && planFamily(plan) === "current" && cycleCode === "ANNUAL" && catalog.current_annual_discount_bps != null) {
    return catalog.current_annual_discount_bps;
  }
  return cycleBps;
}

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
  const [currentPlanCode, setCurrentPlanCode] = useState<string | null>(null);
  const [accessReady, setAccessReady] = useState(false);
  const planTouched = useRef(false);
  const reduceMotion = useReducedMotion();
  const { locale } = useLocale();
  const [quantities, setQuantities] = useState<Record<string, number>>({});
  const [stores, setStores] = useState<{ id: string; name: string }[]>([]);
  const [picks, setPicks] = useState<HardwarePick[]>([]);
  const [quote, setQuote] = useState<BillingQuote | null>(null);
  const [watching, setWatching] = useState<string | null>(null);
  const [transfer, setTransfer] = useState<BillingCheckout | null>(null);
  const [receiptFile, setReceiptFile] = useState<File | null>(null);
  const [transferDate, setTransferDate] = useState("");
  const [transferRef, setTransferRef] = useState("");
  const [receiptSent, setReceiptSent] = useState(false);
  const [idempotencyKey] = useState(() => crypto.randomUUID());

  useEffect(() => {
    let cancelled = false;
    apiGet<BillingCatalog>("/api/v1/billing/catalog")
      .then((found) => {
        if (cancelled) return;
        setCatalog(found);
        const cycle = found.cycles.find((row) => row.code === "MONTHLY" && row.active) ?? found.cycles.find((row) => row.active);
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

  useEffect(() => {
    let cancelled = false;
    apiGet<{ subscription: { plan_code: string } | null }>("/api/v1/billing/access")
      .then((found) => {
        if (cancelled) return;
        setCurrentPlanCode(found.subscription?.plan_code ?? null);
      })
      .catch(() => {
        if (!cancelled) setCurrentPlanCode(null);
      })
      .finally(() => {
        if (!cancelled) setAccessReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!catalog || !accessReady || planTouched.current) return;
    const active = catalog.plans.filter((row) => row.active);
    const current = active.find((row) => row.code === currentPlanCode);
    const free = active.find((row) => row.code === "FREE");
    const next = current ?? free ?? active.find((row) => planFamily(row) === "current") ?? active[0];
    if (next) setPlanCode(next.code);
  }, [catalog, accessReady, currentPlanCode]);

  useEffect(() => {
    apiGet<{ id: string; name: string }[]>("/api/v1/stores?limit=50")
      .then((rows) => setStores(rows.map((row) => ({ id: row.id, name: row.name }))))
      .catch(() => setStores([]));
  }, []);

  const selectedPlan = catalog?.plans.find((row) => row.code === planCode);
  const freePlan = isFreePlan(selectedPlan);
  const customPlan = isCustom(selectedPlan);
  const payable = Boolean(catalog && selectedPlan && !freePlan && !customPlan);
  const steps = goLiveSteps(Boolean(catalog), payable);
  const step = steps[Math.min(stepIndex, steps.length - 1)] ?? "confirm";
  const currentIndex = Math.max(0, steps.indexOf(step));
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
    if (!catalog || !payable || !planCode || !cycleCode) {
      setQuote(null);
      return;
    }
    const timer = window.setTimeout(() => {
      apiPost<BillingQuote>("/api/v1/billing/quote", { plan_code: planCode, cycle_code: cycleCode, addons, hardware: picks })
        .then((priced) => {
          setQuote(priced);
          setError(null);
        })
        .catch((caught: unknown) => setError(caught instanceof ApiRequestError ? caught.message : "Could not price this package."));
    }, 200);
    return () => window.clearTimeout(timer);
  }, [catalog, payable, planCode, cycleCode, addons, picks]);

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
      if (!catalog || freePlan) {
        setResult(
          await apiPost<GoLiveResult>("/api/v1/onboarding/go-live", {
            confirm,
            mode,
            opening_stock: mode === "keep" ? openingStock : "reset",
            tax_acknowledged: true,
            plan_code: freePlan ? "FREE" : undefined,
          }),
        );
        return;
      }
      const checkout = await apiPost<BillingCheckout>("/api/v1/billing/checkout", {
        plan_code: planCode,
        cycle_code: cycleCode,
        addons,
        hardware: picks,
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

  const payByTransfer = async () => {
    setBusy(true);
    setError(null);
    try {
      const checkout = await apiPost<BillingCheckout>("/api/v1/billing/checkout", {
        plan_code: planCode,
        cycle_code: cycleCode,
        addons,
        hardware: picks,
        mode,
        opening_stock: mode === "keep" ? openingStock : "reset",
        confirm,
        tax_acknowledged: true,
        payment: "transfer",
      });
      setTransfer(checkout);
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Could not issue the invoice.");
    } finally {
      setBusy(false);
    }
  };

  const sendReceipt = async () => {
    if (transfer === null || receiptFile === null || transferDate === "") return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.set("invoice_id", transfer.checkout_id);
      form.set("amount_fils", String(transfer.quote.total_fils));
      form.set("transferred_on", transferDate);
      form.set("idempotency_key", idempotencyKey);
      form.set("bank_reference", transferRef);
      form.set("receipt", receiptFile);
      await apiUpload<{ id: string; status: string }>("/api/v1/billing/transfers", form);
      setReceiptSent(true);
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Could not submit the receipt.");
    } finally {
      setBusy(false);
    }
  };

  if (transfer !== null) {
    const bank = transfer.bank;
    return (
      <Modal
        title={receiptSent ? "Receipt received" : "Pay by bank transfer"}
        subtitle="Review your invoice and transfer the amount to the bank account listed on it. Then submit your payment proof. Your subscription features will be activated after our team verifies your payment."
        onClose={onClose}
        footer={
          receiptSent ? (
            <PrimaryButton onClick={onClose}>Close</PrimaryButton>
          ) : (
            <>
              <GhostButton onClick={() => setTransfer(null)} disabled={busy}>
                Back
              </GhostButton>
              <PrimaryButton onClick={() => void sendReceipt()} disabled={busy || receiptFile === null || transferDate === ""}>
                {busy ? "Submitting…" : "Submit receipt"}
              </PrimaryButton>
            </>
          )
        }
      >
        <ErrorNote message={error} />
        <p className="text-sm text-charcoal/70">
          {transfer.quote.plan_name} · {transfer.quote.cycle_name} · Invoice {transfer.checkout_id.slice(0, 8)} ·{" "}
          {formatMoney(transfer.quote.total_fils, transfer.quote.currency)}
        </p>
        <p className="mt-3 text-sm text-charcoal/70">
          Payment is by bank transfer. Opening this invoice or uploading a receipt does not activate the subscription.
        </p>
        {bank ? (
          <dl className="mt-4 grid gap-1 text-sm">
            <div>
              <dt className="inline text-charcoal/50">Account name </dt>
              <dd className="inline">{bank.holder_name}</dd>
            </div>
            <div>
              <dt className="inline text-charcoal/50">Bank </dt>
              <dd className="inline">{bank.bank_name}</dd>
            </div>
            {bank.iban ? (
              <div>
                <dt className="inline text-charcoal/50">IBAN </dt>
                <dd className="inline font-mono">{bank.iban}</dd>
              </div>
            ) : null}
            {bank.account_number ? (
              <div>
                <dt className="inline text-charcoal/50">Account number </dt>
                <dd className="inline font-mono">{bank.account_number}</dd>
              </div>
            ) : null}
            {bank.swift ? (
              <div>
                <dt className="inline text-charcoal/50">SWIFT </dt>
                <dd className="inline font-mono">{bank.swift}</dd>
              </div>
            ) : null}
            {bank.country || bank.currency ? (
              <div>
                <dt className="inline text-charcoal/50">Account </dt>
                <dd className="inline">{[bank.country, bank.currency].filter(Boolean).join(" · ")}</dd>
              </div>
            ) : null}
            {bank.instructions ? <p className="mt-2 text-charcoal/70">{bank.instructions}</p> : null}
            <p className="mt-2 text-charcoal/70">Use the invoice reference in the transfer description.</p>
          </dl>
        ) : (
          <p className="mt-4 text-sm text-charcoal/70">Bank details were not copied onto this invoice.</p>
        )}
        {receiptSent ? (
          <p className="mt-4 rounded-2xl bg-amber-50 p-4 text-sm text-amber-950">
            The transfer is awaiting verification. The store stays on the unpaid plan until it is approved.
          </p>
        ) : (
          <div className="mt-4 grid gap-3">
            <label className="grid gap-1 text-sm">
              Transfer date
              <input
                type="date"
                value={transferDate}
                onChange={(event) => setTransferDate(event.target.value)}
                className="h-10 rounded-xl border border-line px-3"
              />
            </label>
            <label className="grid gap-1 text-sm">
              Bank reference
              <input
                value={transferRef}
                onChange={(event) => setTransferRef(event.target.value)}
                className="h-10 rounded-xl border border-line px-3"
              />
            </label>
            <label className="grid gap-1 text-sm">
              Receipt (PNG, JPEG, or PDF)
              <input
                type="file"
                accept="image/png,image/jpeg,application/pdf"
                onChange={(event) => setReceiptFile(event.target.files?.[0] ?? null)}
              />
            </label>
          </div>
        )}
      </Modal>
    );
  }

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

  if (catalog === undefined) {
    return (
      <Modal title="Go live" subtitle="Loading the plan catalog." onClose={onClose} footer={<GhostButton onClick={onClose}>Not yet</GhostButton>}>
        <p className="text-sm text-charcoal/70">Checking the published plans.</p>
      </Modal>
    );
  }

  const subtitle =
    step === "plan"
      ? "Choose the plan this store goes live on."
      : step === "cycle"
        ? "The billing period changes the amount due now. The quote is the invoice amount."
        : step === "extras"
          ? "Hardware is optional. Software plugins stay in Plans & add-ons and are not added to this invoice."
          : step === "data"
            ? "Choose what to carry into the live store. This can only be done once."
            : "Practice tax stamps cannot be used on live invoices.";
  const transferReady = catalog?.transfer_available !== false;
  const continueDisabled =
    catalog === undefined ||
    (step === "plan" && (planCode === "" || customPlan)) ||
    ((step === "cycle" || step === "extras") && payable && quote === null);

  return (
    <Modal
      title="Go live"
      subtitle={subtitle}
      width={step === "plan" || step === "cycle" || step === "extras" ? "xl" : "md"}
      onClose={onClose}
      headerExtra={
        <WizardStepper
          steps={steps.map((id) => ({ id, label: stepLabel(id) }))}
          currentStep={step}
          completedSteps={steps.slice(0, currentIndex)}
          dir={locale === "ar" ? "rtl" : "ltr"}
          invalid={error !== null && step !== "data"}
          canNavigate={() => !busy}
          onNavigate={(id) => {
            const index = steps.indexOf(id as Step);
            if (busy || index < 0 || index >= currentIndex) return;
            setStepIndex(index);
          }}
        />
      }
      footer={
        <>
          {payable && quote && step !== "plan" ? (
            <p className="mr-auto text-sm">
              <span className="text-charcoal/60">Due now</span>
              <span className="ml-2 text-base font-semibold tabular-nums">{formatMoney(quote.total_fils, quote.currency)}</span>
            </p>
          ) : null}
          <GhostButton onClick={stepIndex === 0 ? onClose : () => setStepIndex(stepIndex - 1)} disabled={busy}>
            {stepIndex === 0 ? "Not yet" : "Back"}
          </GhostButton>
          {step !== "confirm" ? (
            <PrimaryButton onClick={() => setStepIndex(stepIndex + 1)} disabled={continueDisabled}>
              Continue
            </PrimaryButton>
          ) : payable ? (
            <>
              <GhostButton onClick={() => void goLive()} disabled={!matches || !taxAck || busy || watching !== null}>
                {watching ? "Waiting for card payment…" : "Pay by card"}
              </GhostButton>
              <PrimaryButton
                onClick={() => void payByTransfer()}
                disabled={!matches || !taxAck || busy || watching !== null || !transferReady}
              >
                {busy ? "Preparing…" : "Review invoice"}
              </PrimaryButton>
            </>
          ) : (
            <PrimaryButton onClick={() => void goLive()} disabled={!matches || !taxAck || busy}>
              {busy ? "Preparing…" : "Go live"}
            </PrimaryButton>
          )}
        </>
      }
    >
      <AnimatePresence mode="wait">
        <motion.div
          key={step}
          initial={reduceMotion ? false : { opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={reduceMotion ? undefined : { opacity: 0 }}
          transition={{ duration: 0.18 }}
        >
      {step === "data" ? (
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
          {mode === "keep" ? (
            <>
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
            </>
          ) : null}
          <Lists cleared={mode === "keep" ? KEEP_CLEARED : FRESH_CLEARED} kept={mode === "keep" ? KEEP_KEPT : FRESH_KEPT} />
        </div>
      ) : null}
      {step === "plan" && catalog ? (
        <PackageStep
          section="plan"
          catalog={catalog}
          planCode={planCode}
          cycleCode={cycleCode}
          quantities={quantities}
          quote={quote}
          error={error}
          currentPlanCode={currentPlanCode}
          onPlan={(code) => {
            planTouched.current = true;
            setPlanCode(code);
            setQuote(null);
            setError(null);
          }}
          onCycle={setCycleCode}
          onQuantity={(code, quantity) => setQuantities({ ...quantities, [code]: quantity })}
          stores={stores}
          picks={picks}
          onPicks={setPicks}
        />
      ) : null}
      {step === "cycle" && catalog ? (
        <PackageStep
          section="cycle"
          catalog={catalog}
          planCode={planCode}
          cycleCode={cycleCode}
          quantities={quantities}
          quote={quote}
          error={error}
          currentPlanCode={currentPlanCode}
          onPlan={setPlanCode}
          onCycle={setCycleCode}
          onQuantity={(code, quantity) => setQuantities({ ...quantities, [code]: quantity })}
          stores={stores}
          picks={picks}
          onPicks={setPicks}
        />
      ) : null}
      {step === "extras" && catalog ? (
        <PackageStep
          section="extras"
          catalog={catalog}
          planCode={planCode}
          cycleCode={cycleCode}
          quantities={quantities}
          quote={quote}
          error={error}
          currentPlanCode={currentPlanCode}
          onPlan={setPlanCode}
          onCycle={setCycleCode}
          onQuantity={(code, quantity) => setQuantities({ ...quantities, [code]: quantity })}
          stores={stores}
          picks={picks}
          onPicks={setPicks}
        />
      ) : null}
      {step === "confirm" ? (
        <div>
          {payable && quote ? (
            <>
              <QuoteSummary quote={quote} />
              <p className="mb-4 mt-4 text-sm text-charcoal/70">
                Due now is {formatMoney(quote.total_fils, quote.currency)}. That is the invoice total, including the plan
                for {quote.cycle_name}
                {quote.one_time_fils > 0 ? " and the one-time lines above" : ""}. Transfer that amount, then submit proof.
                The store stays in practice until the payment is verified.
              </p>
              {catalog && !transferReady ? (
                <p className="mb-4 rounded-2xl bg-amber-50 p-4 text-sm text-amber-950">
                  Bank transfer details have not been published, so reviewing an invoice is closed. An administrator
                  publishes the account in the console. This does not block Free.
                </p>
              ) : null}
            </>
          ) : null}
          {freePlan ? (
            <p className="mb-4 text-sm text-charcoal/70">
              Free does not create an invoice and does not ask for a bank transfer. Confirm the practice-data change to
              go live.
            </p>
          ) : null}
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
        </motion.div>
      </AnimatePresence>
    </Modal>
  );
}

function stepLabel(step: Step): string {
  if (step === "plan") return "Plan";
  if (step === "cycle") return "Billing";
  if (step === "extras") return "Hardware";
  if (step === "data") return "Your data";
  return "Confirm";
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
  section,
  catalog,
  planCode,
  cycleCode,
  quantities,
  quote,
  error,
  currentPlanCode,
  onPlan,
  onCycle,
  onQuantity,
  stores,
  picks,
  onPicks,
}: {
  section: "plan" | "cycle" | "extras";
  catalog: BillingCatalog;
  planCode: string;
  cycleCode: string;
  quantities: Record<string, number>;
  quote: BillingQuote | null;
  error: string | null;
  currentPlanCode: string | null;
  onPlan: (code: string) => void;
  onCycle: (code: string) => void;
  onQuantity: (code: string, quantity: number) => void;
  stores: { id: string; name: string }[];
  picks: HardwarePick[];
  onPicks: (next: HardwarePick[]) => void;
}) {
  const plans = catalog.plans
    .filter((row) => row.active && (planFamily(row) === "current" || row.code === currentPlanCode))
    .sort((a, b) => a.sort_order - b.sort_order);
  const cycles = catalog.cycles.filter((row) => row.active).sort((a, b) => a.sort_order - b.sort_order);
  const addons = catalog.addons
    .filter((row) => row.active && row.module_keys.length === 0)
    .sort((a, b) => a.sort_order - b.sort_order);
  const plan = catalog.plans.find((row) => row.code === planCode);
  const showsLegacy = plans.some((row) => planFamily(row) === "legacy");

  return (
    <div className="grid gap-6">
      {section === "plan" ? (
        <section>
          <h3 className="text-sm font-semibold">Plan</h3>
          <div className="mt-2 grid gap-3 sm:grid-cols-2">
            {plans.map((row) => {
              const selected = row.code === planCode;
              const custom = isCustom(row);
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
                  <p className="text-sm font-semibold">
                    {row.name}
                    {row.code === currentPlanCode ? <span className="ml-2 text-xs font-medium text-charcoal/50">Current plan</span> : null}
                  </p>
                  <p className="mt-1 text-lg font-semibold tabular-nums">
                    {custom ? "Custom" : formatMoney(row.monthly_fils, "AED")}
                    {custom ? null : <span className="text-sm font-normal text-charcoal/60">{row.monthly_fils === 0 ? " forever" : " / month"}</span>}
                  </p>
                  <p className="mt-1 text-sm text-charcoal/70">
                    {custom
                      ? "Priced on a contract. Contact sales to continue on Enterprise."
                      : `${row.included_registers} ${row.included_registers === 1 ? "register" : "registers"} included`}
                  </p>
                </button>
              );
            })}
          </div>
          {showsLegacy ? (
            <p className="mt-3 text-sm text-charcoal/60">
              Lite, Standard, and Pro stay here only because this store is already on one of them.
            </p>
          ) : null}
          {isCustom(plan) ? (
            <p className="mt-3 text-sm text-charcoal/70">Choose Free, Growth, or Pro AI to continue. Enterprise is not billed at zero.</p>
          ) : null}
        </section>
      ) : null}
      {section === "cycle" ? (
        <section>
          <h3 className="text-sm font-semibold">Billing cycle</h3>
          <div className="mt-2 flex flex-wrap gap-2">
            {cycles.map((row) => {
              const selected = row.code === cycleCode;
              const save = cycleDiscountBps(plan, row.code, row.discount_bps, catalog);
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
                  {save > 0 ? (
                    <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
                      Save {save / 100}%
                    </span>
                  ) : null}
                </button>
              );
            })}
          </div>
          {quote ? <div className="mt-4"><QuoteSummary quote={quote} /></div> : null}
        </section>
      ) : null}
      {section === "extras" ? (
        <>
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
          <HardwarePicker items={catalog.hardware ?? []} stores={stores} picks={picks} onPicks={onPicks} />
          {quote ? <QuoteSummary quote={quote} /> : null}
        </>
      ) : null}
      <ErrorNote message={error} />
    </div>
  );
}

function HardwarePicker({
  items,
  stores,
  picks,
  onPicks,
}: {
  items: NonNullable<BillingCatalog["hardware"]>;
  stores: { id: string; name: string }[];
  picks: HardwarePick[];
  onPicks: (next: HardwarePick[]) => void;
}) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const categories = [...new Set(items.map((item) => item.category_name))];
  const visible = items.filter((item) => {
    const text = `${item.name} ${item.model} ${item.sku} ${item.manufacturer}`.toLowerCase();
    return (category === "" || item.category_name === category) && text.includes(query.trim().toLowerCase());
  });
  if (items.length === 0) {
    return (
      <section>
        <h3 className="text-sm font-semibold">Hardware for your stores</h3>
        <p className="mt-1 text-sm text-charcoal/60">Hardware is optional. Nothing is selected, and no bundle is added for you.</p>
      </section>
    );
  }
  const add = (itemId: string) => {
    const item = items.find((row) => row.id === itemId);
    if (!item) return;
    onPicks([
      ...picks,
      {
        item_id: itemId,
        quantity: item.min_qty,
        mode: item.lease_available ? "lease" : "purchase",
        store_id: null,
        store_label: "Pending store",
      },
    ]);
  };
  return (
    <section className="grid gap-3">
      <div>
        <h3 className="text-sm font-semibold">Hardware for your stores</h3>
        <p className="mt-1 text-sm text-charcoal/60">
          Choose what each store needs. Lease rent and refundable deposits are shown separately. You can skip this.
        </p>
      </div>
      <div className="grid gap-2 sm:grid-cols-[1fr_12rem]">
        <input
          className="rounded-xl border border-line bg-white px-3 py-2 text-sm"
          placeholder="Search hardware"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <select
          className="rounded-xl border border-line bg-white px-3 py-2 text-sm"
          value={category}
          onChange={(event) => setCategory(event.target.value)}
        >
          <option value="">All categories</option>
          {categories.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </div>
      {visible.length === 0 ? <p className="text-sm text-charcoal/60">No hardware matches that search.</p> : null}
      {visible.map((item) => (
        <article key={item.id} className="rounded-2xl border border-line bg-white p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="font-semibold">{item.name}</p>
              <p className="text-sm text-charcoal/60">
                {item.manufacturer} {item.model} · {item.sku} · {item.category_name}
              </p>
              {item.lease_available ? (
                <p className="mt-1 text-sm">
                  {formatMoney(item.monthly_fils, item.currency)} / month
                  {item.deposit_fils ? ` · ${formatMoney(item.deposit_fils, item.currency)} refundable deposit` : ""}
                </p>
              ) : null}
              {item.purchase_available && item.purchase_fils != null ? (
                <p className="text-sm">Buy for {formatMoney(item.purchase_fils, item.currency)}</p>
              ) : null}
              {item.compatibility ? <p className="mt-1 text-xs text-charcoal/60">{item.compatibility}</p> : null}
            </div>
            <button type="button" className="rounded-full border border-line px-3 py-1.5 text-sm" onClick={() => add(item.id)}>
              Add
            </button>
          </div>
        </article>
      ))}
      {picks.map((pick, index) => {
        const item = items.find((row) => row.id === pick.item_id);
        return (
          <div key={`${pick.item_id}-${index}`} className="grid gap-2 rounded-2xl bg-surface p-3 sm:grid-cols-4">
            <p className="text-sm font-medium sm:col-span-4">{item?.name ?? "Hardware"}</p>
            <label className="text-xs">
              Store
              <select
                className="mt-1 w-full rounded-xl border border-line bg-white px-2 py-2 text-sm"
                value={pick.store_id ?? ""}
                onChange={(event) => {
                  const next = [...picks];
                  next[index] = { ...pick, store_id: event.target.value || null, store_label: event.target.value ? "" : "Pending store" };
                  onPicks(next);
                }}
              >
                <option value="">Pending store</option>
                {stores.map((store) => (
                  <option key={store.id} value={store.id}>
                    {store.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs">
              Quantity
              <input
                className="mt-1 w-full rounded-xl border border-line bg-white px-2 py-2 text-sm"
                type="number"
                min={item?.min_qty ?? 1}
                max={item?.max_qty ?? 20}
                value={pick.quantity}
                onChange={(event) => {
                  const next = [...picks];
                  next[index] = { ...pick, quantity: Number(event.target.value) || 1 };
                  onPicks(next);
                }}
              />
            </label>
            <label className="text-xs">
              Offer
              <select
                className="mt-1 w-full rounded-xl border border-line bg-white px-2 py-2 text-sm"
                value={pick.mode}
                onChange={(event) => {
                  const next = [...picks];
                  next[index] = { ...pick, mode: event.target.value === "purchase" ? "purchase" : "lease" };
                  onPicks(next);
                }}
              >
                {item?.lease_available ? <option value="lease">Lease</option> : null}
                {item?.purchase_available ? <option value="purchase">Purchase</option> : null}
              </select>
            </label>
            <button
              type="button"
              className="self-end text-sm text-danger"
              onClick={() => onPicks(picks.filter((_, itemIndex) => itemIndex !== index))}
            >
              Remove
            </button>
          </div>
        );
      })}
    </section>
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
      {quote.deposit_fils ? (
        <p className="mt-2 flex justify-between text-charcoal/70">
          <span>Refundable deposits</span>
          <span className="tabular-nums">{formatMoney(quote.deposit_fils, quote.currency)}</span>
        </p>
      ) : null}
      {quote.hardware_monthly_fils ? (
        <p className="mt-1 flex justify-between text-charcoal/70">
          <span>Hardware lease each month</span>
          <span className="tabular-nums">{formatMoney(quote.hardware_monthly_fils, quote.currency)}</span>
        </p>
      ) : null}
      <p className="mt-2 flex justify-between text-charcoal/70">
        <span>Recurring this period</span>
        <span className="tabular-nums">{formatMoney(quote.recurring_fils, quote.currency)}</span>
      </p>
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
