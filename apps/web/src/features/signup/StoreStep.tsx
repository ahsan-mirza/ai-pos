import {
  addressError,
  businessCodeLabel,
  businessCodePhrase,
  currencyForCountry,
  normalizeAddress,
  normalizeStoreCode,
  taxIdError,
  taxIdField,
  type SignupState,
} from "@ai-pos/shared-types";
import { CountryField, availabilityBlocksSubmit, normalizeStoreName, storeNameError, useLocale } from "@ai-pos/ui";
import { Check, Loader2, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { ErrorNote, TextField } from "../../components/ui/Field";
import { env } from "../../config/env";
import { ApiRequestError } from "../../lib/api";
import { StoreNameAvailabilityField, useSlugAvailability, useStoreNameAvailability } from "./availabilityFields";
import { signupApi, slugFromName, type SignupSession } from "./signupApi";
import { WizardFooter } from "./WizardFooter";

const STORE_EXAMPLES: Record<string, string> = {
  electronics_wholesale: "Al Noor Electronics",
  electronics_retail: "Al Noor Electronics",
  electronics_b2b: "Al Noor Wholesale",
  electronics_both: "Al Noor Electronics",
  wholesale_retail: "Al Noor Trading",
  wholesale_distributor: "Al Noor Trading",
  retail_shop: "Al Noor Store",
  retail_fashion: "Al Noor Boutique",
  fashion_boutique: "Al Noor Boutique",
  fashion_chain: "Al Noor Fashion",
  grocery: "Al Noor Market",
  restaurant: "Al Noor Restaurant",
  full_service: "Al Noor Restaurant",
  restaurant_delivery: "Al Noor Kitchen",
  cafe: "Al Noor Cafe",
  counter_cafe: "Al Noor Cafe",
  sit_down_cafe: "Al Noor Cafe",
  quick_service: "Al Noor Burger",
  qsr_counter: "Al Noor Burger",
  qsr_delivery: "Al Noor Wraps",
};

function storeExample(profile: string | null, subType: string | null): string {
  return STORE_EXAMPLES[subType ?? ""] ?? STORE_EXAMPLES[profile ?? ""] ?? "Al Noor Store";
}

export function StoreStep({
  session,
  profile,
  subType,
  country: initialCountry,
  onBack,
  onSubmitted,
}: {
  session: SignupSession;
  profile: string | null;
  subType: string | null;
  country: string;
  onBack: () => void;
  onSubmitted: (state: SignupState) => void;
}) {
  const { t } = useLocale();
  const codeLabel = t(businessCodeLabel(profile));
  const [storeName, setStoreName] = useState("");
  const [slug, setSlug] = useState("");
  const [address, setAddress] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [country, setCountry] = useState(initialCountry);
  const [trn, setTrn] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nameCheck = useStoreNameAvailability(storeName);
  const slugCheck = useSlugAvailability(slug);

  const currency = currencyForCountry(country);
  const nameValid = storeNameError(storeName, true) === undefined;
  const taxField = taxIdField(country);
  const taxError = taxIdError(country, trn);
  const trnValid = taxError === null;
  const slugReady = !availabilityBlocksSubmit(slugCheck.status, slug.length > 0);
  const nameReady = !availabilityBlocksSubmit(nameCheck.status, nameValid);
  const addressProblem = addressError(address, true);
  const ready = nameReady && slugReady && trnValid && addressProblem === undefined && !busy;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!ready || addressProblem) {
      if (addressProblem) setError(addressProblem);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onSubmitted(
        await signupApi.store(session, {
          store_name: normalizeStoreName(storeName),
          slug,
          address: normalizeAddress(address),
          currency,
          country,
          trn: trn === "" ? null : trn,
        }),
      );
    } catch (caught) {
      setError(t(caught instanceof ApiRequestError ? caught.message : "Could not create the store."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="flex min-h-0 w-full flex-auto flex-col overflow-hidden" onSubmit={(event) => void submit(event)}>
      <div className="signup-fields min-h-0 flex-auto overflow-y-auto overscroll-contain">
      <h2 className="text-xl font-semibold">{t("Name your store")}</h2>
      <p className="mt-1 text-sm text-charcoal/60">{t("This is what customers see on receipts and invoices.")}</p>
      <div className="mt-4 space-y-3">
        <StoreNameAvailabilityField
          value={storeName}
          status={nameCheck.status}
          onRetry={nameCheck.retry}
          placeholder={storeExample(profile, subType)}
          onChange={(value) => {
            setStoreName(value);
            if (!slugEdited) setSlug(slugFromName(value));
          }}
        />
        <div>
          <label className="block text-sm font-medium" htmlFor="signup-slug">
            {codeLabel}
          </label>
          <div className="mt-1.5 flex items-center rounded-xl border border-transparent bg-surface pr-3 focus-within:border-accent focus-within:bg-white">
            <input
              id="signup-slug"
              value={slug}
              onChange={(event) => {
                setSlugEdited(true);
                setSlug(normalizeStoreCode(event.target.value).replace(/[^a-z0-9-]/g, "").slice(0, 32));
              }}
              className="min-w-0 flex-1 bg-transparent px-4 py-3 text-sm focus:outline-none"
              aria-describedby="signup-slug-status"
              required
            />
            {env.storesShareThisHost ? null : (
              <span className="shrink-0 text-sm text-charcoal/50">.{env.tenantBaseDomain()}</span>
            )}
            <span className="ml-2 flex w-5 shrink-0 justify-center" aria-hidden="true">
              {slugCheck.status === "checking" ? (
                <Loader2 size={16} className="animate-spin text-charcoal/40" />
              ) : slugCheck.result?.available ? (
                <Check size={16} className="text-emerald-600" />
              ) : slugCheck.result ? (
                <X size={16} className="text-accent" />
              ) : null}
            </span>
          </div>
          <p id="signup-slug-status" className="mt-1.5 min-h-5 text-xs" aria-live="polite">
            {slugCheck.status === "checking" ? (
              <span className="text-charcoal/50">{t("Checking…")}</span>
            ) : slugCheck.status === "error" ? (
              <span className="text-accent">
                {t("We couldn't check this code.")}{" "}
                <button type="button" className="font-semibold underline" onClick={slugCheck.retry}>
                  {t("Retry")}
                </button>
              </span>
            ) : slugCheck.result === null ? (
              <span className="text-charcoal/50">
                {t(businessCodePhrase(profile, "staff"))}
              </span>
            ) : slugCheck.result.available ? (
              <span className="text-emerald-700">{t("Available")}</span>
            ) : (
              <span className="text-accent">
                {slugCheck.result.reason ? t(slugCheck.result.reason) : null}
                {slugCheck.result.suggestion ? (
                  <>
                    {" "}
                    <button
                      type="button"
                      className="font-semibold underline"
                      onClick={() => {
                        setSlugEdited(true);
                        setSlug(slugCheck.result?.suggestion ?? "");
                      }}
                    >
                      {t("Use {code}", { code: slugCheck.result.suggestion })}
                    </button>
                  </>
                ) : null}
              </span>
            )}
          </p>
        </div>
        <TextField
          label={t("Store address")}
          required
          value={address}
          autoComplete="street-address"
          dir="auto"
          placeholder="Shop 12, Building A, Main Street"
          error={address !== "" && addressProblem ? t(addressProblem) : undefined}
          onChange={(event) => setAddress(event.target.value)}
        />
        <div className="signup-pair">
          <CountryField label={t("Country")} value={country} onChange={setCountry} detail={currencyForCountry} required />
          <TextField label={t("Currency")} value={currency} readOnly disabled hint={t("Set by the country.")} />
        </div>
        <TextField
          label={t(taxField.label)}
          value={trn}
          maxLength={32}
          autoComplete="off"
          onChange={(event) => setTrn(event.target.value.slice(0, 32))}
          hint={taxError === null ? t(taxField.hint) : undefined}
          error={taxError ? t(taxError) : undefined}
          placeholder={taxField.placeholder || undefined}
        />
      </div>
      <ErrorNote message={error ? t(error) : null} />
      </div>
      <WizardFooter type="submit" continueLabel="Create my store" busyLabel="Creating…" busy={busy} disabled={!ready} onBack={onBack} />
    </form>
  );
}
