import { formatMoney, type BillingCheckout, type BillingPlan, type BillingQuote } from "@ai-pos/shared-types";
import { useLocale } from "@ai-pos/ui";
import { useEffect, useState } from "react";
import { ErrorNote, PrimaryButton } from "../../../components/ui/Field";
import { Modal } from "../../../components/ui/Modal";
import { ApiRequestError, apiPost } from "../../../lib/api";
import { OnboardingHelp } from "./OnboardingAssistance";
import type { PlanChangeRequest } from "./PlanChangeList";

/** Existing plan checkout. Issues the same transfer invoice. It does not confirm payment. */

export function PlanQuoteDialog({
  plan,
  cycleCode,
  quote,
  onboardingFils,
  currency,
  transferAvailable,
  storeName,
  onClose,
  onInvoiced,
  onRequested,
}: {
  plan: BillingPlan;
  cycleCode: string;
  quote: BillingQuote | null;
  onboardingFils: number;
  currency: string;
  transferAvailable: boolean;
  storeName: string;
  onClose: () => void;
  onInvoiced: () => void;
  onRequested?: () => void;
}) {
  const { t } = useLocale();
  const [assistance, setAssistance] = useState(false);
  const [liveQuote, setLiveQuote] = useState<BillingQuote | null>(quote);
  const [quoting, setQuoting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [issued, setIssued] = useState<BillingCheckout | null>(null);
  const amount = formatMoney(onboardingFils, currency);

  useEffect(() => {
    if (!assistance) {
      setLiveQuote(quote);
      setQuoting(false);
      setError(null);
      return;
    }
    let cancelled = false;
    setQuoting(true);
    setError(null);
    apiPost<BillingQuote>("/api/v1/billing/quote", {
      plan_code: plan.code,
      cycle_code: cycleCode,
      addons: [],
      hardware: [],
      onboarding: true,
    })
      .then((next) => {
        if (!cancelled) setLiveQuote(next);
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setAssistance(false);
        setError(caught instanceof ApiRequestError ? caught.message : t("Could not issue the invoice."));
      })
      .finally(() => {
        if (!cancelled) setQuoting(false);
      });
    return () => {
      cancelled = true;
    };
  }, [assistance, cycleCode, plan.code, quote]);

  const issue = async () => {
    if (!storeName.trim()) {
      setError(t("Set the legal name in settings before creating an invoice."));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await apiPost<PlanChangeRequest>("/api/v1/billing/subscription-changes", {
        plan_code: plan.code,
        cycle_code: cycleCode,
        onboarding: assistance,
      });
      onRequested?.();
      if (
        !liveQuote ||
        created.quote.total_fils !== liveQuote.total_fils ||
        created.quote.currency !== liveQuote.currency ||
        created.quote.discount_bps !== liveQuote.discount_bps
      ) {
        setError(t("The quote changed. Review the new amount before continuing."));
        return;
      }
      const result = await apiPost<{ checkout: BillingCheckout }>(
        `/api/v1/billing/subscription-changes/${created.id}/checkout`,
        {
          plan_code: plan.code,
          cycle_code: cycleCode,
          addons: [],
          hardware: [],
          onboarding: assistance,
          mode: "keep",
          opening_stock: "keep",
          confirm: storeName.trim(),
          tax_acknowledged: true,
          payment: "transfer",
        },
      );
      setIssued(result.checkout);
      onInvoiced();
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : t("Could not issue the invoice."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={t("Review quote")}
      onClose={onClose}
      footer={
        <PrimaryButton type="button" disabled={busy || quoting || !liveQuote || !transferAvailable || issued !== null} onClick={() => void issue()}>
          {busy ? t("Please wait…") : t("Generate invoice")}
        </PrimaryButton>
      }
    >
      {onboardingFils > 0 ? (
        <div className="mb-4 rounded-xl border border-line p-3 dark:border-zinc-800">
          <div className="flex items-center gap-1">
            <p className="text-sm font-semibold">{t("Need help getting started?")}</p>
            <OnboardingHelp amount={amount} />
          </div>
          <label className="mt-2 flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-1"
              checked={assistance}
              onChange={(event) => setAssistance(event.target.checked)}
            />
            <span>
              <span className="font-medium">{t("Add professional onboarding assistance — {amount} (one-time)", { amount })}</span>
              <span className="mt-1 block text-charcoal/70 dark:text-white/70">
                {t("Our team will help you configure your business and get started with AxizPOS.")}
              </span>
            </span>
          </label>
        </div>
      ) : null}
      {liveQuote ? (
        <>
          <p className="text-sm text-charcoal/70 dark:text-white/70">
            {liveQuote.plan_name} · {liveQuote.cycle_name} · <span dir="ltr">{formatMoney(liveQuote.total_fils, liveQuote.currency)}</span>
          </p>
          <ul className="mt-3 divide-y divide-line text-sm">
            {liveQuote.lines.map((line) => (
              <li key={line.code} className="flex justify-between gap-3 py-2">
                <span>
                  {t(line.label)}
                  {line.quantity > 1 ? ` × ${line.quantity}` : ""}
                  {line.code === "onboarding" ? ` · ${t("one-time")}` : ""}
                </span>
                <span className="tabular-nums" dir="ltr">
                  {formatMoney(line.amount_fils, liveQuote.currency)}
                </span>
              </li>
            ))}
          </ul>
          {liveQuote.discount_bps > 0 ? (
            <p className="mt-2 text-xs text-accent">{t("{percent}% off this cycle", { percent: liveQuote.discount_bps / 100 })}</p>
          ) : null}
        </>
      ) : (
        <p className="text-sm text-charcoal/60">{t("The quote is not available for this cycle.")}</p>
      )}
      {!transferAvailable ? <p className="mt-3 text-sm text-amber-800 dark:text-amber-200">{t("Bank transfer details have not been published yet.")}</p> : null}
      {issued ? (
        <p className="mt-3 text-sm font-medium">
          {t("Awaiting payment")} · <span dir="ltr">{formatMoney(issued.quote.total_fils, issued.quote.currency)}</span>. {t("Paid features stay locked until a payment is verified.")}
        </p>
      ) : null}
      <ErrorNote message={error} />
    </Modal>
  );
}
