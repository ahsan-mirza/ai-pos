import { currencyForCountry, normalizeStoreCode, taxIdError, taxIdField, type SignupState } from "@ai-pos/shared-types";
import { CountryField, availabilityBlocksSubmit, normalizeStoreName, storeNameError } from "@ai-pos/ui";
import { Check, Loader2, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { ErrorNote, TextField } from "../../components/ui/Field";
import { env } from "../../config/env";
import { ApiRequestError } from "../../lib/api";
import { StoreNameAvailabilityField, useSlugAvailability, useStoreNameAvailability } from "./availabilityFields";
import { signupApi, slugFromName, type SignupSession } from "./signupApi";

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
  const [storeName, setStoreName] = useState("");
  const [slug, setSlug] = useState("");
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
  const ready = nameReady && slugReady && trnValid && !busy;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!ready) return;
    setBusy(true);
    setError(null);
    try {
      onSubmitted(
        await signupApi.store(session, {
          store_name: normalizeStoreName(storeName),
          slug,
          currency,
          country,
          trn: trn === "" ? null : trn,
        }),
      );
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Could not create the store.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="w-full" onSubmit={(event) => void submit(event)}>
      <h2 className="text-2xl font-semibold">Name your store</h2>
      <p className="mt-1 text-sm text-charcoal/60">This is what customers see on receipts and invoices.</p>
      <div className="mt-6 space-y-4">
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
            Store address
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
              <span className="text-charcoal/50">Checking…</span>
            ) : slugCheck.status === "error" ? (
              <span className="text-accent">
                We couldn&apos;t check this address.{" "}
                <button type="button" className="font-semibold underline" onClick={slugCheck.retry}>
                  Retry
                </button>
              </span>
            ) : slugCheck.result === null ? (
              <span className="text-charcoal/50">
                {env.storesShareThisHost
                  ? "Your staff sign in on this site with this store code."
                  : "Your staff sign in at this address."}
              </span>
            ) : slugCheck.result.available ? (
              <span className="text-emerald-700">Available</span>
            ) : (
              <span className="text-accent">
                {slugCheck.result.reason}
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
                      Use {slugCheck.result.suggestion}
                    </button>
                  </>
                ) : null}
              </span>
            )}
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <CountryField label="Country" value={country} onChange={setCountry} detail={currencyForCountry} required />
          <TextField label="Currency" value={currency} readOnly disabled hint="Set by the country." />
        </div>
        <TextField
          label={taxField.label}
          value={trn}
          maxLength={32}
          autoComplete="off"
          onChange={(event) => setTrn(event.target.value.slice(0, 32))}
          hint={taxError === null ? taxField.hint : undefined}
          error={taxError ?? undefined}
          placeholder={taxField.placeholder || undefined}
        />
      </div>
      <ErrorNote message={error} />
      <div className="mt-6 flex items-center justify-between gap-3">
        <button type="button" onClick={onBack} className="text-sm text-charcoal/60 hover:text-charcoal">
          Back
        </button>
        <button
          type="submit"
          disabled={!ready}
          className="h-12 rounded-2xl bg-accent px-8 font-semibold text-white transition-colors hover:bg-accent-hover disabled:opacity-40"
        >
          {busy ? "Creating…" : "Create my store"}
        </button>
      </div>
    </form>
  );
}
