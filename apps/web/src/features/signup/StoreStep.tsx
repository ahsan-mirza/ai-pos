import { SIGNUP_COUNTRIES, type SignupState, type SlugCheck } from "@ai-pos/shared-types";
import { Check, Loader2, X } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { ErrorNote, SelectField, TextField } from "../../components/ui/Field";
import { env } from "../../config/env";
import { ApiRequestError } from "../../lib/api";
import { signupApi, slugFromName, type SignupSession } from "./signupApi";

const SLUG_DEBOUNCE_MS = 350;

const STORE_EXAMPLES: Record<string, string> = {
  electronics_wholesale: "Al Noor Electronics",
  electronics_retail: "Al Noor Electronics",
  electronics_b2b: "Al Noor Wholesale",
  electronics_both: "Al Noor Electronics",
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
  onBack,
  onSubmitted,
}: {
  session: SignupSession;
  profile: string | null;
  subType: string | null;
  onBack: () => void;
  onSubmitted: (state: SignupState) => void;
}) {
  const [storeName, setStoreName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [check, setCheck] = useState<SlugCheck | null>(null);
  const [checking, setChecking] = useState(false);
  const [country, setCountry] = useState("AE");
  const [trn, setTrn] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const currency = SIGNUP_COUNTRIES.find((option) => option.code === country)?.currency ?? "AED";

  useEffect(() => {
    if (slug === "") {
      setCheck(null);
      return;
    }
    setChecking(true);
    let cancelled = false;
    const timer = window.setTimeout(() => {
      signupApi
        .slugCheck(slug)
        .then((result) => {
          if (!cancelled) setCheck(result);
        })
        .catch(() => {
          if (!cancelled) setCheck(null);
        })
        .finally(() => {
          if (!cancelled) setChecking(false);
        });
    }, SLUG_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [slug]);

  const trnValid = trn === "" || /^\d{15}$/.test(trn);
  const ready = storeName.trim().length >= 2 && check?.available === true && check.slug === slug && trnValid && !checking;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onSubmitted(
        await signupApi.store(session, {
          store_name: storeName.trim(),
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
    <form className="mx-auto max-w-md" onSubmit={(event) => void submit(event)}>
      <h2 className="text-2xl font-semibold">Name your store</h2>
      <p className="mt-1 text-sm text-charcoal/60">This is what customers see on receipts and invoices.</p>
      <div className="mt-6 space-y-4">
        <TextField
          label="Store name"
          value={storeName}
          onChange={(event) => {
            setStoreName(event.target.value);
            if (!slugEdited) setSlug(slugFromName(event.target.value));
          }}
          placeholder={storeExample(profile, subType)}
          required
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
                setSlug(event.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "").slice(0, 32));
              }}
              className="min-w-0 flex-1 bg-transparent px-4 py-3 text-sm focus:outline-none"
              aria-describedby="signup-slug-status"
              required
            />
            {env.storesShareThisHost ? null : (
              <span className="shrink-0 text-sm text-charcoal/50">.{env.tenantBaseDomain()}</span>
            )}
            <span className="ml-2 flex w-5 shrink-0 justify-center" aria-hidden="true">
              {checking ? (
                <Loader2 size={16} className="animate-spin text-charcoal/40" />
              ) : check?.available ? (
                <Check size={16} className="text-emerald-600" />
              ) : check ? (
                <X size={16} className="text-accent" />
              ) : null}
            </span>
          </div>
          <p id="signup-slug-status" className="mt-1.5 text-xs" aria-live="polite">
            {checking || check === null ? (
              <span className="text-charcoal/50">
                {env.storesShareThisHost
                  ? "Your staff sign in on this site with this store code."
                  : "Your staff sign in at this address."}
              </span>
            ) : check.available ? (
              <span className="text-emerald-700">Available</span>
            ) : (
              <span className="text-accent">
                {check.reason}
                {check.suggestion ? (
                  <>
                    {" "}
                    <button
                      type="button"
                      className="font-semibold underline"
                      onClick={() => {
                        setSlugEdited(true);
                        setSlug(check.suggestion ?? "");
                      }}
                    >
                      Use {check.suggestion}
                    </button>
                  </>
                ) : null}
              </span>
            )}
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <SelectField
            label="Country"
            value={country}
            onChange={setCountry}
            options={SIGNUP_COUNTRIES.map((option) => ({ value: option.code, label: option.name }))}
          />
          <TextField label="Currency" value={currency} readOnly disabled hint="Set by the country." />
        </div>
        <TextField
          label="VAT number (TRN)"
          inputMode="numeric"
          value={trn}
          onChange={(event) => setTrn(event.target.value.replace(/\D/g, "").slice(0, 15))}
          hint={trnValid ? "Optional. 15 digits; add it later if you are not registered yet." : "A TRN has 15 digits."}
          placeholder="100123456700003"
        />
      </div>
      <ErrorNote message={error} />
      <div className="mt-6 flex items-center justify-between gap-3">
        <button type="button" onClick={onBack} className="text-sm text-charcoal/60 hover:text-charcoal">
          Back
        </button>
        <button
          type="submit"
          disabled={!ready || busy}
          className="h-12 rounded-2xl bg-accent px-8 font-semibold text-white transition-colors hover:bg-accent-hover disabled:opacity-40"
        >
          {busy ? "Creating…" : "Create my store"}
        </button>
      </div>
    </form>
  );
}
