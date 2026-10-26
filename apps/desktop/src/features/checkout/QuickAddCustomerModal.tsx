import { PAYMENT_TERMS_LABELS, PRICE_TIERS, PRICE_TIER_LABELS, Permission, type PaymentTerms, type PriceTier } from "@ai-pos/shared-types";
import { PhoneField, Select, phoneError } from "@ai-pos/ui";
import { Building2, UserRound, X } from "lucide-react";
import { useEffect, useId, useState } from "react";
import type { RegisterCustomer } from "../../lib/tauri";
import type { CashierSession } from "../auth/session";
import { createCustomer } from "./wholesaleClient";

type Kind = "RETAIL" | "WHOLESALE";

const TERMS: PaymentTerms[] = ["DUE_ON_RECEIPT", "NET_15", "NET_30", "NET_60"];

/** Digits with the usual phone punctuation are a phone number; anything with letters is a name. */
export function looksLikePhone(query: string): boolean {
  const trimmed = query.trim();
  return /^[+\d][\d\s()-]{5,}$/.test(trimmed) && /\d{6,}/.test(trimmed.replace(/\D/g, ""));
}

interface QuickAddCustomerModalProps {
  session: CashierSession;
  query: string;
  onClose: () => void;
  onCreated: (customer: RegisterCustomer) => void;
}

export function QuickAddCustomerModal({ session, query, onClose, onCreated }: QuickAddCustomerModalProps) {
  const titleId = useId();
  const phoneFirst = looksLikePhone(query);
  const manager = session.user.permissions.includes(Permission.CustomersManage);
  const [kind, setKind] = useState<Kind>("RETAIL");
  const [name, setName] = useState(phoneFirst ? "" : query.trim());
  const [phone, setPhone] = useState(phoneFirst ? query.trim() : "");
  const [email, setEmail] = useState("");
  const [company, setCompany] = useState("");
  const [trn, setTrn] = useState("");
  const [tier, setTier] = useState<PriceTier>("TIER_1");
  const [credit, setCredit] = useState("");
  const [terms, setTerms] = useState<PaymentTerms>("NET_30");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [phoneProblem, setPhoneProblem] = useState<string | undefined>();

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  const save = async () => {
    const wholesale = kind === "WHOLESALE";
    if (wholesale && !company.trim()) return setError("Enter the company name.");
    const phoneProblemNext = phoneError(phone);
    setPhoneProblem(phoneProblemNext);
    if (phoneProblemNext) return setError(null);
    if (!name.trim() && !phone.trim()) return setError("Enter a name or a phone number.");
    if (trn.trim() && !/^\d{15}$/.test(trn.trim())) return setError("A UAE TRN is 15 digits.");
    const creditCents = Math.round(Number(credit || "0") * 100);
    if (!Number.isFinite(creditCents) || creditCents < 0) return setError("Enter the credit limit as an amount, e.g. 5000.");
    setBusy(true);
    setError(null);
    try {
      const created = await createCustomer(session, {
        name: name.trim() || (wholesale ? company.trim() : `Walk-in ${phone.trim()}`),
        phone: phone.trim() || null,
        email: email.trim() || null,
        customer_type: kind,
        company_name: wholesale ? company.trim() : null,
        trn_vat_number: wholesale ? trn.trim() || null : null,
        price_tier: wholesale && manager ? tier : "RETAIL",
        credit_limit_cents: wholesale && manager ? creditCents : 0,
        payment_terms: wholesale && manager ? terms : "DUE_ON_RECEIPT",
      });
      onCreated(created);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      setBusy(false);
    }
  };

  const field = "modal-input mt-1.5 text-sm font-normal tabular-nums";
  return (
    <div className="modal-backdrop" role="presentation">
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="modal-card max-w-lg">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id={titleId} className="text-xl font-semibold">
              New customer
            </h2>
            <p className="mt-0.5 text-sm text-charcoal/60 dark:text-zinc-400">Saved on this register now and attached to the sale.</p>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} disabled={busy} className="modal-close">
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        <div role="radiogroup" aria-label="Customer type" className="mt-5 grid grid-cols-2 gap-1 rounded-full bg-surface p-1 dark:bg-zinc-800/60">
          {(
            [
              ["RETAIL", "Retail customer", UserRound],
              ["WHOLESALE", "Wholesale / B2B", Building2],
            ] as const
          ).map(([value, label, Icon]) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={kind === value}
              onClick={() => setKind(value)}
              className={`flex items-center justify-center gap-2 rounded-full px-4 py-2.5 text-sm font-semibold transition-colors ${
                kind === value ? "bg-primary text-white shadow-sm" : "text-charcoal/70 hover:text-charcoal dark:text-zinc-400 dark:hover:text-white"
              }`}
            >
              <Icon size={15} aria-hidden="true" /> {label}
            </button>
          ))}
        </div>

        <form
          className="mt-5 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          {kind === "WHOLESALE" ? (
            <label className="block text-sm font-medium">
              Company name
              <input autoFocus value={company} maxLength={160} onChange={(event) => setCompany(event.target.value)} className={field} />
            </label>
          ) : null}
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-sm font-medium">
              {kind === "WHOLESALE" ? "Contact name" : "Name"}
              <input
                autoFocus={kind === "RETAIL" && !phoneFirst}
                value={name}
                maxLength={120}
                placeholder={kind === "RETAIL" ? "Optional with a phone" : ""}
                onChange={(event) => setName(event.target.value)}
                className={field}
              />
            </label>
            <PhoneField label="Phone" value={phone} error={phoneProblem} onChange={setPhone} />
          </div>
          {kind === "RETAIL" ? (
            <label className="block text-sm font-medium">
              Email (optional)
              <input type="email" value={email} maxLength={254} onChange={(event) => setEmail(event.target.value)} className={field} />
            </label>
          ) : (
            <>
              <label className="block text-sm font-medium">
                TRN / VAT number (optional)
                <input inputMode="numeric" value={trn} maxLength={15} onChange={(event) => setTrn(event.target.value.replace(/\D/g, ""))} className={field} />
              </label>
              <fieldset disabled={!manager} className="grid gap-4 sm:grid-cols-3 disabled:opacity-50">
                <label className="block text-sm font-medium">
                  Price tier
                  <Select
                    className="mt-1"
                    aria-label="Price tier"
                    value={tier}
                    onChange={(value) => setTier(value as PriceTier)}
                    options={PRICE_TIERS.map((value) => ({ value, label: PRICE_TIER_LABELS[value] }))}
                  />
                </label>
                <label className="block text-sm font-medium">
                  Credit limit
                  <input inputMode="decimal" value={credit} placeholder="0.00" onChange={(event) => setCredit(event.target.value)} className={field} />
                </label>
                <label className="block text-sm font-medium">
                  Terms
                  <Select
                    className="mt-1"
                    aria-label="Terms"
                    value={terms}
                    onChange={(value) => setTerms(value as PaymentTerms)}
                    options={TERMS.map((value) => ({ value, label: PAYMENT_TERMS_LABELS[value] }))}
                  />
                </label>
              </fieldset>
              {manager ? null : (
                <p className="-mt-2 text-xs text-charcoal/60 dark:text-zinc-400">
                  Starts on retail pricing with no credit; a manager sets the tier and terms from the portal.
                </p>
              )}
            </>
          )}
          {error ? (
            <p role="alert" className="text-sm font-medium text-red-600 dark:text-red-400">
              {error}
            </p>
          ) : null}
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} disabled={busy} className="modal-cancel">
              Cancel
            </button>
            <button type="submit" disabled={busy} className="modal-save">
              {busy ? "Saving…" : "Add and attach"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
