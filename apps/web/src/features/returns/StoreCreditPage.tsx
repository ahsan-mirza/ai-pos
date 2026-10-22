import { formatMoney, type StoreCreditList } from "@ai-pos/shared-types";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote } from "../../components/ui/Field";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { apiGet } from "../../lib/api";
import { useCurrency } from "../../lib/currency";
import { message } from "../customers/api";

const filters = [
  { value: "open", label: "With balance" },
  { value: "all", label: "All" },
] as const;

const shortDate = (value: string) =>
  new Date(value).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

export function StoreCreditPage() {
  const { currency } = useCurrency();
  const [filter, setFilter] = useState<(typeof filters)[number]["value"]>("open");
  const [data, setData] = useState<StoreCreditList | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await apiGet<StoreCreditList>(`/api/v1/store-credits?open_only=${filter === "open"}`));
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not load store credit."));
    }
  }, [filter]);

  useEffect(() => {
    void load();
  }, [load]);

  const spentCents = (data?.items ?? []).reduce((sum, item) => sum + item.initial_cents - item.balance_cents, 0);

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">Outstanding store credit</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{data ? formatMoney(data.outstanding_cents, currency) : "—"}</p>
          <p className="mt-2 text-xs text-white/50">Owed to customers until they spend it</p>
        </article>
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">Open vouchers</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{data?.open_count ?? "—"}</p>
          <p className="mt-2 text-xs text-white/80">Accepted at every branch</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Spent from listed vouchers</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{data ? formatMoney(spentCents, currency) : "—"}</p>
          <p className="mt-2 text-xs text-charcoal/50">Redeemed as a tender at checkout</p>
        </article>
      </div>

      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Store credit vouchers</h2>
            <p className="text-sm text-charcoal/60">Issued when a return is refunded to store credit; cashiers enter the code at checkout.</p>
          </div>
          <SegmentedControl label="Vouchers" value={filter} options={filters} onChange={setFilter} />
        </div>
        <ErrorNote message={error} />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="pb-3 font-medium">Voucher</th>
                <th className="pb-3 font-medium">Issued</th>
                <th className="pb-3 text-right font-medium">Issued for</th>
                <th className="pb-3 text-right font-medium">Balance</th>
                <th className="pb-3 pl-6 font-medium">Used on</th>
              </tr>
            </thead>
            <tbody>
              {(data?.items ?? []).map((voucher) => (
                <tr key={voucher.id} className="border-t border-line align-top">
                  <td className="py-3 font-mono text-xs font-semibold">{voucher.code}</td>
                  <td className="py-3">
                    <span className="block tabular-nums">{shortDate(voucher.issued_at)}</span>
                    <span className="block text-xs text-charcoal/50">{voucher.store_name}</span>
                  </td>
                  <td className="py-3 text-right tabular-nums">{formatMoney(voucher.initial_cents, voucher.currency)}</td>
                  <td className={`py-3 text-right font-semibold tabular-nums ${voucher.balance_cents > 0 ? "" : "text-charcoal/40"}`}>
                    {formatMoney(voucher.balance_cents, voucher.currency)}
                  </td>
                  <td className="py-3 pl-6 text-xs text-charcoal/60">
                    {voucher.uses.length === 0
                      ? "Not used yet"
                      : voucher.uses.map((use) => (
                          <span key={use.sale_id} className="block tabular-nums">
                            {use.invoice_number ?? use.sale_id.slice(0, 8).toUpperCase()} · {formatMoney(use.amount_cents, voucher.currency)} ·{" "}
                            {shortDate(use.used_at)}
                          </span>
                        ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {data !== null && data.items.length === 0 ? (
            <p className="py-8 text-sm text-charcoal/60">No store credit vouchers{filter === "open" ? " with a balance" : ""}.</p>
          ) : null}
        </div>
      </div>
    </section>
  );
}
