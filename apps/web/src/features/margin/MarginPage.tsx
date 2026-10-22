import {
  Permission,
  formatMoney,
  type MarginExceptionList,
  type MarginPolicy,
  type MarginPolicyWrite,
  type MarginScope,
  type Product,
} from "@ai-pos/shared-types";
import { Plus, ShieldCheck, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { Toast } from "../../components/ui/Toast";
import { apiDelete, apiGet, apiPut } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCurrency } from "../../lib/currency";
import { inventoryApi } from "../inventory/api";
import { formatDate, useCategories } from "../inventory/shared";
import { errorMessage } from "../users/api";

const scopeLabels: Record<MarginScope, string> = { GLOBAL: "Everything", CATEGORY: "Category", PRODUCT: "Product" };
const percent = (bps: number) => `${(bps / 100).toLocaleString(undefined, { maximumFractionDigits: 2 })}%`;

export function MarginPage() {
  const { can } = useAuth();
  const { currency } = useCurrency();
  const manage = can(Permission.PortalPricingManage);
  const [policies, setPolicies] = useState<MarginPolicy[]>([]);
  const [report, setReport] = useState<MarginExceptionList | null>(null);
  const [days, setDays] = useState<"7" | "30" | "90">("30");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);

  const load = useCallback(async () => {
    try {
      const [nextPolicies, nextReport] = await Promise.all([
        apiGet<MarginPolicy[]>("/api/v1/margin/policies"),
        apiGet<MarginExceptionList>(`/api/v1/margin/exceptions?days=${days}`),
      ]);
      setPolicies(nextPolicies);
      setReport(nextReport);
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load margin settings."));
    }
  }, [days]);

  useEffect(() => {
    void load();
  }, [load]);

  const remove = async (policy: MarginPolicy) => {
    try {
      setPolicies(await apiDelete(`/api/v1/margin/policies/${policy.id}`).then(() => apiGet<MarginPolicy[]>("/api/v1/margin/policies")));
      setToast("Policy removed.");
    } catch (caught) {
      setError(errorMessage(caught, "Could not remove the policy."));
    }
  };

  const unapproved = report?.exceptions.filter((row) => row.approved_by_name === null).length ?? 0;

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">Margin given away</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{report ? formatMoney(report.total_shortfall_cents, currency) : "—"}</p>
          <p className="mt-2 text-xs text-white/50">Below-floor sales in the last {days} days</p>
        </article>
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">Without approval</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{unapproved}</p>
          <p className="mt-2 text-xs text-white/80">Rung offline or from a stale floor list</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Active policies</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{policies.filter((row) => row.is_active).length}</p>
          <p className="mt-2 text-xs text-charcoal/50">Product beats category beats everything</p>
        </article>
      </div>

      <ErrorNote message={error} />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.4fr)]">
        <article className="rounded-card border border-line bg-white p-6">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-xl font-semibold">Minimum margins</h2>
              <p className="text-sm text-charcoal/60">Floor = cost of the next unit (FIFO) plus this margin.</p>
            </div>
            {manage ? (
              <PrimaryButton onClick={() => setAdding(true)}>
                <Plus size={16} aria-hidden="true" className="-ml-2 mr-1.5" /> Add
              </PrimaryButton>
            ) : null}
          </div>
          <ul className="mt-4 space-y-2">
            {policies.length === 0 ? (
              <li className="rounded-2xl border border-dashed border-line p-6 text-center text-sm text-charcoal/60">
                No floors yet. Registers sell at any price a manager approves.
              </li>
            ) : null}
            {policies.map((policy) => (
              <li key={policy.id} className="flex items-center gap-3 rounded-2xl bg-surface p-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-charcoal text-white">
                  <ShieldCheck size={16} aria-hidden="true" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold">
                    {policy.scope === "GLOBAL" ? "Everything" : (policy.product_name ?? policy.category_name)}
                  </p>
                  <p className="text-xs text-charcoal/50">{scopeLabels[policy.scope]}{policy.is_active ? "" : " · paused"}</p>
                </div>
                <span className="text-lg font-semibold tabular-nums">{percent(policy.min_margin_bps)}</span>
                {manage ? (
                  <button
                    type="button"
                    aria-label="Remove policy"
                    onClick={() => void remove(policy)}
                    className="flex h-9 w-9 items-center justify-center rounded-full text-charcoal/50 hover:bg-charcoal/10 hover:text-charcoal"
                  >
                    <Trash2 size={15} aria-hidden="true" />
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </article>

        <article className="rounded-card border border-line bg-white p-6">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-xl font-semibold">Below-floor sales</h2>
              <p className="text-sm text-charcoal/60">Every line sold under its margin floor, and who allowed it.</p>
            </div>
            <SegmentedControl
              label="Period"
              value={days}
              options={[
                { value: "7", label: "7 days" },
                { value: "30", label: "30 days" },
                { value: "90", label: "90 days" },
              ]}
              onChange={setDays}
            />
          </div>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-charcoal/50">
                <tr>
                  <th className="pb-3 font-medium">Sale</th>
                  <th className="pb-3 font-medium">Product</th>
                  <th className="pb-3 text-right font-medium">Price / floor</th>
                  <th className="pb-3 text-right font-medium">Given away</th>
                  <th className="pb-3 pl-6 font-medium">Approved by</th>
                </tr>
              </thead>
              <tbody>
                {(report?.exceptions ?? []).map((row) => (
                  <tr key={`${row.sale_id}-${row.product_name}-${row.unit_price_cents}`} className="border-t border-line">
                    <td className="py-3">
                      <span className="block font-mono text-xs font-semibold">{row.invoice}</span>
                      <span className="block text-xs text-charcoal/50">
                        {row.store_code} · {formatDate(row.sold_at)}
                      </span>
                    </td>
                    <td className="py-3">
                      {row.product_name}
                      <span className="text-charcoal/50"> × {row.quantity}</span>
                    </td>
                    <td className="py-3 text-right tabular-nums">
                      {formatMoney(row.unit_price_cents, row.currency)}
                      <span className="block text-xs text-charcoal/50">floor {formatMoney(row.floor_cents, row.currency)}</span>
                    </td>
                    <td className="py-3 text-right font-semibold tabular-nums text-accent">
                      {formatMoney(row.shortfall_cents, row.currency)}
                    </td>
                    <td className="py-3 pl-6">
                      {row.approved_by_name ?? (
                        <span className="rounded-full bg-accent px-2.5 py-0.5 text-[11px] font-semibold text-white">Not approved</span>
                      )}
                      <span className="block text-xs text-charcoal/50">rung by {row.cashier_name ?? "—"}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {report !== null && report.exceptions.length === 0 ? (
              <p className="py-8 text-sm text-charcoal/60">No below-floor sales in this period.</p>
            ) : null}
          </div>
        </article>
      </div>
      {adding ? (
        <PolicyModal
          onClose={() => setAdding(false)}
          onSaved={(next) => {
            setPolicies(next);
            setAdding(false);
            setToast("Margin policy saved. Registers pick it up on their next refresh.");
          }}
        />
      ) : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}

function PolicyModal({ onClose, onSaved }: { onClose: () => void; onSaved: (policies: MarginPolicy[]) => void }) {
  const { categories } = useCategories();
  const [scope, setScope] = useState<MarginScope>("GLOBAL");
  const [categoryId, setCategoryId] = useState("");
  const [productId, setProductId] = useState("");
  const [products, setProducts] = useState<Product[]>([]);
  const [margin, setMargin] = useState("15");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (scope === "PRODUCT" && products.length === 0) void inventoryApi.products({ limit: 500 }).then(setProducts).catch(() => undefined);
  }, [products.length, scope]);

  const save = async () => {
    const value = Number(margin);
    if (!Number.isFinite(value) || value < 0 || value > 1000) return setError("Enter a margin between 0 and 1000%.");
    const body: MarginPolicyWrite = {
      scope,
      category_id: scope === "CATEGORY" ? categoryId || null : null,
      product_id: scope === "PRODUCT" ? productId || null : null,
      min_margin_bps: Math.round(value * 100),
    };
    setBusy(true);
    setError(null);
    try {
      onSaved(await apiPut<MarginPolicy[]>("/api/v1/margin/policies", body));
    } catch (caught) {
      setError(errorMessage(caught, "Could not save the policy."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Minimum margin"
      subtitle="Sales below cost plus this margin need a manager's approval at the register."
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : "Save"}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        <SegmentedControl
          label="Applies to"
          value={scope}
          options={[
            { value: "GLOBAL", label: "Everything" },
            { value: "CATEGORY", label: "Category" },
            { value: "PRODUCT", label: "Product" },
          ]}
          onChange={setScope}
        />
        {scope === "CATEGORY" ? (
          <SelectField
            label="Category"
            value={categoryId}
            placeholder="Choose a category"
            options={categories.map((item) => ({ value: item.id, label: item.name }))}
            onChange={setCategoryId}
          />
        ) : null}
        {scope === "PRODUCT" ? (
          <SelectField
            label="Product"
            value={productId}
            placeholder="Choose a product"
            searchable
            options={products.map((item) => ({ value: item.id, label: item.name, hint: item.sku }))}
            onChange={setProductId}
          />
        ) : null}
        <TextField
          label="Minimum margin over cost (%)"
          inputMode="decimal"
          value={margin}
          className="tabular-nums"
          onChange={(event) => setMargin(event.target.value)}
        />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}
