import { CURRENCY_NAMES, SUPPORTED_CURRENCIES, formatMoney, profileSpec, type CurrencyCode } from "@ai-pos/shared-types";
import { AlertTriangle, Check, Coins } from "lucide-react";
import { useEffect, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { useCapabilities } from "../../lib/capabilities";
import { useCurrency } from "../../lib/currency";
import { errorMessage } from "../users/api";
import { AppearanceSettings } from "./AppearanceSettings";
import { BusinessProfileSettings } from "./BusinessProfileSettings";
import { ModuleSettingsPanel } from "./ModuleSettingsPanel";
import { ModuleShortcuts } from "./ModuleShortcuts";
import { ReceiptSettingsCard } from "./ReceiptSettings";
import { TillRulesSettings } from "./TillRulesSettings";
import { VatSettings } from "./VatSettings";

const PREVIEW_CENTS = 129_950;

function updatedLine(updatedAt: string, by: string | null): string {
  const when = new Date(updatedAt).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  return by ? `Last changed ${when} by ${by}` : `Set ${when}`;
}

function SectionHeading({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="mt-4 xl:col-span-2">
      <h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-charcoal/45">{title}</h2>
      <p className="mt-0.5 text-sm text-charcoal/60">{hint}</p>
    </div>
  );
}

export function SettingsPage() {
  const { currency, settings, loadError, saveCurrency } = useCurrency();
  const { profile, enabled } = useCapabilities();
  const spec = profileSpec(profile);
  const [choice, setChoice] = useState<CurrencyCode>(currency);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => setChoice(currency), [currency]);

  const options = settings?.supported_currencies ?? [...SUPPORTED_CURRENCIES];
  const changed = choice !== currency;

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const next = await saveCurrency(choice);
      setNotice(`The business now trades in ${CURRENCY_NAMES[next.currency]} (${next.currency}).`);
      setConfirming(false);
    } catch (caught) {
      setError(errorMessage(caught, "Could not change the currency."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
      <header className="flex flex-wrap items-end justify-between gap-3 xl:col-span-2">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">{spec.settingsLabel}</h1>
          <p className="mt-1 text-sm text-charcoal/60">Business-wide settings shared by every branch and register.</p>
        </div>
        <a
          href="#business-profile"
          className="inline-flex items-center gap-2 rounded-full border border-line bg-white px-3 py-1.5 text-sm font-medium hover:border-charcoal/20"
        >
          <span className="h-2 w-2 rounded-full bg-accent" aria-hidden="true" />
          {spec.shortLabel}
          <span className="text-charcoal/50">
            · {enabled.size} module{enabled.size === 1 ? "" : "s"} on
          </span>
        </a>
      </header>

      <SectionHeading title="General" hint="Currency, tax, receipts and the look of the portal and registers." />

      <div className="rounded-card border border-line bg-white p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent text-white">
              <Coins size={20} aria-hidden="true" />
            </span>
            <div>
              <h2 className="text-2xl font-semibold">Business currency</h2>
              <p className="text-sm text-charcoal/60">
                Used for every price, register, receipt and report across all stores.
              </p>
            </div>
          </div>
          <PrimaryButton
            disabled={!changed || settings === null}
            onClick={() => {
              setError(null);
              setNotice(null);
              setConfirming(true);
            }}
          >
            Save currency
          </PrimaryButton>
        </div>

        <fieldset className="mt-6">
          <legend className="sr-only">Currency</legend>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {options.map((code) => {
              const selected = choice === code;
              return (
                <label
                  key={code}
                  className={`relative flex cursor-pointer flex-col rounded-2xl border p-4 transition ${
                    selected ? "border-accent bg-accent/5" : "border-line hover:bg-surface"
                  }`}
                >
                  <input
                    type="radio"
                    name="currency"
                    value={code}
                    checked={selected}
                    onChange={() => setChoice(code)}
                    className="sr-only"
                  />
                  <span className="flex items-center justify-between">
                    <span className="text-lg font-semibold tracking-tight">{code}</span>
                    {code === currency ? (
                      <span className="rounded-full bg-charcoal px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-white">
                        Current
                      </span>
                    ) : selected ? (
                      <Check size={16} className="text-accent" aria-hidden="true" />
                    ) : null}
                  </span>
                  <span className="mt-0.5 text-xs text-charcoal/60">{CURRENCY_NAMES[code]}</span>
                  <span className="mt-3 text-sm font-medium tabular-nums">{formatMoney(PREVIEW_CENTS, code)}</span>
                </label>
              );
            })}
          </div>
        </fieldset>

        {notice ? (
          <p role="status" className="mt-4 rounded-2xl bg-surface px-4 py-3 text-sm text-charcoal/80">
            {notice}
          </p>
        ) : null}
        <ErrorNote message={confirming ? loadError : (error ?? loadError)} />
      </div>

      <aside className="flex flex-col gap-4">
        <div className="rounded-card bg-charcoal p-5 text-white">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-white/50">In use</p>
          <p className="mt-2 text-4xl font-semibold tracking-tight">{currency}</p>
          <p className="mt-1 text-sm text-white/70">{CURRENCY_NAMES[currency]}</p>
          <p className="mt-4 text-xs text-white/50">
            {settings ? updatedLine(settings.updated_at, settings.updated_by_name) : "Loading…"}
          </p>
        </div>
        <div className="rounded-card border border-line bg-white p-5 text-sm text-charcoal/70">
          <h3 className="font-semibold text-charcoal">What changes</h3>
          <ul className="mt-2 list-disc space-y-1.5 pl-4">
            <li>Every store and product is relabelled to the new currency. Amounts are not converted.</li>
            <li>Registers pick it up on their next sync and charge in it from then on.</li>
            <li>Past sales, returns and repairs keep the currency they were taken in.</li>
          </ul>
        </div>
      </aside>

      <div className="xl:col-span-2">
        <VatSettings />
      </div>

      <div className="xl:col-span-2">
        <ReceiptSettingsCard />
      </div>

      <div className="xl:col-span-2">
        <TillRulesSettings />
      </div>

      <div className="xl:col-span-2">
        <AppearanceSettings />
      </div>

      <SectionHeading
        title="Business type & modules"
        hint={`What your ${spec.shortLabel.toLowerCase()} business runs on: the portal and registers show only these modules.`}
      />

      <div className="xl:col-span-2">
        <BusinessProfileSettings />
      </div>

      <div className="xl:col-span-2">
        <ModuleSettingsPanel />
      </div>

      <div className="xl:col-span-2">
        <ModuleShortcuts />
      </div>

      {confirming ? (
        <Modal
          title={`Switch to ${choice}?`}
          subtitle={`${CURRENCY_NAMES[currency]} → ${CURRENCY_NAMES[choice]}`}
          onClose={() => (busy ? undefined : setConfirming(false))}
          footer={
            <>
              <GhostButton disabled={busy} onClick={() => setConfirming(false)}>
                Cancel
              </GhostButton>
              <PrimaryButton disabled={busy} onClick={() => void save()}>
                {busy ? "Switching…" : `Switch to ${choice}`}
              </PrimaryButton>
            </>
          }
        >
          <div className="flex gap-3 rounded-2xl bg-accent/10 p-4 text-sm text-charcoal">
            <AlertTriangle size={18} className="mt-0.5 shrink-0 text-accent" aria-hidden="true" />
            <p>
              Prices keep their numbers: {formatMoney(PREVIEW_CENTS, currency)} becomes{" "}
              <span className="font-semibold tabular-nums">{formatMoney(PREVIEW_CENTS, choice)}</span>. Make sure every
              register has synced first, because sales still queued in {currency} will be rejected.
            </p>
          </div>
          <ErrorNote message={error} />
        </Modal>
      ) : null}
    </section>
  );
}
