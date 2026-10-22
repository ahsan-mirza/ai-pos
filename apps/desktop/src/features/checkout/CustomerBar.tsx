import { PAYMENT_TERMS_LABELS, PRICE_TIER_LABELS } from "@ai-pos/shared-types";
import { Building2, UserRound, X } from "lucide-react";
import { useEffect, useState } from "react";
import { customerHistory } from "../../lib/api";
import type { RegisterCustomer } from "../../lib/tauri";
import type { CashierSession } from "../auth/session";
import { CreditBadge } from "./CreditBadge";
import { CustomerSearchPopover } from "./CustomerSearchPopover";
import { QuickAddCustomerModal } from "./QuickAddCustomerModal";

interface CustomerBarProps {
  session: CashierSession;
  customer: RegisterCustomer | null;
  currency: string;
  disabled?: boolean;
  /** On-account portion of the current sale, previewed on the credit badge. */
  pendingCents: number;
  onAttach: (customer: RegisterCustomer | null) => void;
}

function CustomerProfile({ customer }: { customer: RegisterCustomer }) {
  const [recent, setRecent] = useState<string[]>([]);
  const sizes = Object.entries(customer.preferred_sizes ?? {})
    .map(([key, value]) => `${key} ${value}`)
    .join(" · ");
  const birthday = customer.birthday?.slice(5, 10);
  const today = new Date().toISOString().slice(5, 10);
  useEffect(() => {
    let live = true;
    customerHistory(customer.id)
      .then((rows) => {
        if (live) {
          setRecent(rows.map((row) => [row.name, row.size, row.color].filter(Boolean).join(" ")));
        }
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [customer.id]);
  if (!sizes && !customer.notes && !birthday && recent.length === 0) return null;
  return (
    <div className="mt-2 space-y-1 text-xs text-zinc-600 dark:text-white/60">
      {birthday === today ? <p className="font-semibold text-primary">Birthday today</p> : null}
      {sizes ? <p>Sizes {sizes}</p> : null}
      {customer.notes ? <p className="line-clamp-2">{customer.notes}</p> : null}
      {recent.length ? <p className="line-clamp-2">Last: {recent.join(", ")}</p> : null}
    </div>
  );
}

export function CustomerBar({ session, customer, currency, disabled = false, pendingCents, onAttach }: CustomerBarProps) {
  const [adding, setAdding] = useState<string | null>(null);

  if (customer !== null) {
    const wholesale = customer.customer_type === "WHOLESALE";
    return (
      <div className="space-y-2">
        <div className="flex items-start gap-3 rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-800/40 p-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary text-white">
            {wholesale ? <Building2 size={18} aria-hidden="true" /> : <UserRound size={18} aria-hidden="true" />}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate font-semibold">{customer.company_name ?? customer.name}</p>
            <p className="truncate text-xs text-zinc-600 dark:text-white/60">
              {[customer.company_name ? customer.name : null, customer.code, customer.trn_vat_number && `TRN ${customer.trn_vat_number}`]
                .filter(Boolean)
                .join(" · ")}
            </p>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              <span className="rounded-full bg-primary px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
                {PRICE_TIER_LABELS[customer.price_tier]}
              </span>
              {wholesale ? (
                <span className="rounded-full bg-zinc-100 dark:bg-white/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-700 dark:text-white/80">
                  {PAYMENT_TERMS_LABELS[customer.payment_terms]}
                </span>
              ) : null}
            </div>
            <CustomerProfile customer={customer} />
          </div>
          <button
            type="button"
            aria-label="Detach customer"
            disabled={disabled}
            onClick={() => onAttach(null)}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-zinc-600 dark:text-white/60 hover:bg-zinc-100 dark:hover:bg-white/10 hover:text-zinc-900 dark:hover:text-white disabled:opacity-40"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>
        {wholesale ? <CreditBadge customer={customer} currency={currency} pendingCents={pendingCents} /> : null}
      </div>
    );
  }

  return (
    <>
      <CustomerSearchPopover disabled={disabled} onSelect={onAttach} onQuickAdd={setAdding} />
      {adding !== null ? (
        <QuickAddCustomerModal
          session={session}
          query={adding}
          onClose={() => setAdding(null)}
          onCreated={(created) => {
            setAdding(null);
            onAttach(created);
          }}
        />
      ) : null}
    </>
  );
}
