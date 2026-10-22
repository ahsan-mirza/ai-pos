import {
  CURRENCY_NAMES,
  PROFILE_PRESETS,
  SUPPORTED_CURRENCIES,
  capabilitySpec,
  resolveCapabilities,
  type BusinessProfile,
  type CurrencyCode,
} from "@ai-pos/shared-types";
import { Check } from "lucide-react";
import { useEffect, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { useCapabilities } from "../../lib/capabilities";
import { useCanManageSettings, useCurrency } from "../../lib/currency";
import { saveProfile } from "../settings/BusinessProfileSettings";
import { ComingSoonBadge, ProfilePicker, plannedModules } from "../settings/profileParts";
import { errorMessage } from "../users/api";

const STEPS = ["Business type", "Currency", "Review"] as const;
const DISMISSED_KEY = "ai-pos.onboarding-dismissed";

/** First sign-in of a new business: pick a business type and currency. Only business-wide admins see it. */
export function OnboardingWizard() {
  const { settings, currency, saveCurrency, applySettings } = useCurrency();
  const { onboarded, profile: currentProfile } = useCapabilities();
  const canManageSettings = useCanManageSettings();
  const [dismissed, setDismissed] = useState(() => sessionStorage.getItem(DISMISSED_KEY) === "1");
  const [step, setStep] = useState(0);
  const [profile, setProfile] = useState<BusinessProfile>(currentProfile);
  const [chosenCurrency, setChosenCurrency] = useState<CurrencyCode>(currency);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setProfile(currentProfile);
    setChosenCurrency(currency);
  }, [currentProfile, currency]);

  if (settings === null || onboarded || !canManageSettings || dismissed) return null;

  const resolved = resolveCapabilities(profile);
  const currencies = settings.supported_currencies ?? [...SUPPORTED_CURRENCIES];
  const dismiss = () => {
    sessionStorage.setItem(DISMISSED_KEY, "1");
    setDismissed(true);
  };

  const finish = async () => {
    setBusy(true);
    setError(null);
    try {
      if (chosenCurrency !== settings.currency) await saveCurrency(chosenCurrency);
      applySettings(await saveProfile({ business_profile: profile, capabilities: null, complete_onboarding: true }));
    } catch (caught) {
      setError(errorMessage(caught, "Could not finish setup."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      width="lg"
      title="Set up your business"
      subtitle={`Step ${step + 1} of ${STEPS.length}: ${STEPS[step]}`}
      onClose={() => (busy ? undefined : dismiss())}
      footer={
        <>
          {step === 0 ? (
            <GhostButton disabled={busy} onClick={dismiss}>
              Decide later
            </GhostButton>
          ) : (
            <GhostButton disabled={busy} onClick={() => setStep(step - 1)}>
              Back
            </GhostButton>
          )}
          {step < STEPS.length - 1 ? (
            <PrimaryButton onClick={() => setStep(step + 1)}>Continue</PrimaryButton>
          ) : (
            <PrimaryButton disabled={busy} onClick={() => void finish()}>
              {busy ? "Saving…" : "Finish setup"}
            </PrimaryButton>
          )}
        </>
      }
    >
      <ol className="mb-6 flex gap-2" aria-label="Setup progress">
        {STEPS.map((label, index) => (
          <li
            key={label}
            className={`h-1.5 flex-1 rounded-full ${index <= step ? "bg-accent" : "bg-line"}`}
            aria-current={index === step ? "step" : undefined}
          >
            <span className="sr-only">{label}</span>
          </li>
        ))}
      </ol>

      {step === 0 ? (
        <>
          <p className="mb-4 text-sm text-charcoal/70">
            This decides which modules start switched on. You can change it, or switch single modules, any time in{" "}
            {PROFILE_PRESETS[profile].settingsLabel}.
          </p>
          <ProfilePicker value={profile} onChange={setProfile} />
          <PlannedNote profile={profile} />
        </>
      ) : null}

      {step === 1 ? (
        <fieldset>
          <legend className="mb-4 text-sm text-charcoal/70">
            Every price, register, receipt and report uses this currency.
          </legend>
          <div className="grid gap-3 sm:grid-cols-3">
            {currencies.map((code) => {
              const selected = chosenCurrency === code;
              return (
                <label
                  key={code}
                  className={`flex cursor-pointer items-center justify-between rounded-2xl border p-4 transition ${
                    selected ? "border-accent bg-accent/5" : "border-line hover:bg-surface"
                  }`}
                >
                  <input
                    type="radio"
                    name="onboarding-currency"
                    value={code}
                    checked={selected}
                    onChange={() => setChosenCurrency(code)}
                    className="sr-only"
                  />
                  <span>
                    <span className="block text-lg font-semibold tracking-tight">{code}</span>
                    <span className="block text-xs text-charcoal/60">{CURRENCY_NAMES[code]}</span>
                  </span>
                  {selected ? <Check size={16} className="text-accent" aria-hidden="true" /> : null}
                </label>
              );
            })}
          </div>
        </fieldset>
      ) : null}

      {step === 2 ? (
        <div className="space-y-4 text-sm">
          <p className="text-charcoal/70">
            <span className="font-semibold text-charcoal">{PROFILE_PRESETS[profile].label}</span>, trading in{" "}
            <span className="font-semibold text-charcoal">
              {CURRENCY_NAMES[chosenCurrency]} ({chosenCurrency})
            </span>
            .
          </p>
          <div>
            <h3 className="mb-2 font-semibold">Switched on</h3>
            {resolved.enabled.length > 0 ? (
              <ul className="flex flex-wrap gap-2">
                {resolved.enabled.map((capability) => (
                  <li key={capability} className="rounded-full bg-accent/10 px-3 py-1 text-xs font-medium text-charcoal">
                    {capabilitySpec(capability).label}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-charcoal/60">Only the core register, inventory, customers and reports.</p>
            )}
          </div>
          {resolved.planned.length > 0 ? (
            <div>
              <h3 className="mb-2 flex items-center gap-2 font-semibold">
                Planned <ComingSoonBadge />
              </h3>
              <ul className="flex flex-wrap gap-2">
                {resolved.planned.map((capability) => (
                  <li key={capability} className="rounded-full bg-surface px-3 py-1 text-xs text-charcoal/70">
                    {capabilitySpec(capability).label}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <ErrorNote message={error} />
        </div>
      ) : null}
    </Modal>
  );
}

function PlannedNote({ profile }: { profile: BusinessProfile }) {
  const planned = plannedModules(profile);
  if (planned.length === 0) return null;
  return (
    <p className="mt-4 rounded-2xl bg-amber-50 px-4 py-3 text-sm text-amber-900">
      Still on the way: {planned.join(", ")}. You can start selling today; those modules switch on by themselves when
      they ship.
    </p>
  );
}
