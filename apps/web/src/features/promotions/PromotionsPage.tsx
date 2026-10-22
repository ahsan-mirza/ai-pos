import { formatMoney, type ProductSearchHit, type Promotion, type PromotionKind } from "@ai-pos/shared-types";
import { Plus, Tag, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, FilterSelect, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { Toast } from "../../components/ui/Toast";
import { Toggle } from "../../components/ui/Toggle";
import { apiGet, apiPost, apiPut } from "../../lib/api";
import { useCurrency } from "../../lib/currency";
import { toCents } from "../customers/api";
import { useCategories } from "../inventory/shared";
import { errorMessage } from "../users/api";

const kindLabels: Record<PromotionKind, string> = {
  PERCENT_OFF: "% off",
  BUY_X_GET_Y: "Buy X get Y",
  MIX_MATCH: "Mix & match",
  BUNDLE: "Bundle",
};

function summary(promo: Promotion, currency: string): string {
  switch (promo.kind) {
    case "PERCENT_OFF":
      return `${(promo.percent_bps ?? 0) / 100}% off`;
    case "BUY_X_GET_Y":
      return promo.get_discount_bps === 10000 || promo.get_discount_bps == null
        ? `Buy ${promo.buy_qty}, get ${promo.get_qty} free`
        : `Buy ${promo.buy_qty}, get ${promo.get_qty} at ${(promo.get_discount_bps ?? 0) / 100}% off`;
    case "MIX_MATCH":
      return `Any ${promo.group_qty} for ${formatMoney(promo.group_price_cents ?? 0, currency)}`;
    case "BUNDLE":
      return `${(promo.components ?? []).length} products for ${formatMoney(promo.bundle_price_cents ?? 0, currency)}`;
  }
}

function schedule(promo: Promotion): string {
  const day = (value: string) => new Date(value).toLocaleDateString(undefined, { day: "numeric", month: "short" });
  if (promo.starts_at && promo.ends_at) return `${day(promo.starts_at)} – ${day(promo.ends_at)}`;
  if (promo.ends_at) return `Until ${day(promo.ends_at)}`;
  if (promo.starts_at) return `From ${day(promo.starts_at)}`;
  return "Always on";
}

function live(promo: Promotion): boolean {
  const now = Date.now();
  return (
    promo.is_active &&
    (!promo.starts_at || new Date(promo.starts_at).getTime() <= now) &&
    (!promo.ends_at || new Date(promo.ends_at).getTime() > now) &&
    (promo.max_uses === null || promo.uses_count < promo.max_uses)
  );
}

export function PromotionsPage() {
  const { currency } = useCurrency();
  const [rows, setRows] = useState<Promotion[]>([]);
  const [editing, setEditing] = useState<Promotion | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);

  const load = useCallback(async () => {
    try {
      setRows(await apiGet<Promotion[]>("/api/v1/promotions"));
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load promotions."));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const running = rows.filter(live);
  const given = rows.reduce((sum, row) => sum + row.discount_given_cents, 0);
  const uses = rows.reduce((sum, row) => sum + row.uses_count, 0);

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">Running now</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{running.length}</p>
          <p className="mt-2 text-xs text-white/50">{running.filter((row) => row.coupon_code).length} need a coupon code</p>
        </article>
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">Discount given</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{formatMoney(given, currency)}</p>
          <p className="mt-2 text-xs text-white/80">Across every promotion, before VAT</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Sales using a promotion</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{uses}</p>
          <p className="mt-2 text-xs text-charcoal/50">Mismatched claims from offline registers are flagged in the audit trail</p>
        </article>
      </div>

      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Promotions</h2>
            <p className="text-sm text-charcoal/60">Retail only. Registers apply the best promotion to each line automatically, online or offline.</p>
          </div>
          <PrimaryButton onClick={() => setEditing("new")}>
            <Plus size={16} aria-hidden="true" className="-ml-1 mr-1.5" /> New promotion
          </PrimaryButton>
        </div>
        <ErrorNote message={error} />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="pb-3 font-medium">Promotion</th>
                <th className="pb-3 font-medium">Deal</th>
                <th className="pb-3 font-medium">When</th>
                <th className="pb-3 font-medium">Coupon</th>
                <th className="pb-3 text-right font-medium">Uses</th>
                <th className="pb-3 text-right font-medium">Given</th>
                <th className="pb-3 pl-6 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} onClick={() => setEditing(row)} className="cursor-pointer border-t border-line align-top hover:bg-surface/60">
                  <td className="py-3">
                    <span className="block font-medium">{row.name}</span>
                    <span className="block text-xs text-charcoal/50">{kindLabels[row.kind]}</span>
                  </td>
                  <td className="py-3">{summary(row, currency)}</td>
                  <td className="py-3 text-charcoal/70">{schedule(row)}</td>
                  <td className="py-3 font-mono text-xs">{row.coupon_code ?? "—"}</td>
                  <td className="py-3 text-right tabular-nums">
                    {row.uses_count}
                    {row.max_uses ? <span className="text-charcoal/40"> / {row.max_uses}</span> : null}
                  </td>
                  <td className="py-3 text-right tabular-nums">{formatMoney(row.discount_given_cents, currency)}</td>
                  <td className="py-3 pl-6">
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                        live(row) ? "bg-accent text-white" : row.is_active ? "bg-surface text-charcoal ring-1 ring-line" : "bg-white text-charcoal/40 ring-1 ring-line"
                      }`}
                    >
                      {live(row) ? "Running" : row.is_active ? "Scheduled / ended" : "Off"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 ? <p className="py-8 text-sm text-charcoal/60">No promotions yet. Create one to start a sale or bundle.</p> : null}
        </div>
      </div>

      {editing ? (
        <PromotionModal
          promotion={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={(saved) => {
            setEditing(null);
            setToast(`${saved.name} saved. Registers pick it up on their next refresh.`);
            void load();
          }}
        />
      ) : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}

interface PickedProduct {
  id: string;
  name: string;
}

function ProductPicker({ label, picked, onChange }: { label: string; picked: PickedProduct[]; onChange: (next: PickedProduct[]) => void }) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<ProductSearchHit[]>([]);
  useEffect(() => {
    if (query.trim().length < 2) return;
    const timer = window.setTimeout(() => {
      apiGet<ProductSearchHit[]>(`/api/v1/products/search?${new URLSearchParams({ q: query.trim(), limit: "8" }).toString()}`)
        .then(setHits)
        .catch(() => setHits([]));
    }, 200);
    return () => window.clearTimeout(timer);
  }, [query]);
  return (
    <div>
      <TextField label={label} value={query} placeholder="Search products" onChange={(event) => setQuery(event.target.value)} />
      {query.trim().length >= 2 && hits.length ? (
        <ul className="mt-1 divide-y divide-line rounded-2xl border border-line">
          {hits
            .filter((hit) => !picked.some((row) => row.id === hit.product.id))
            .map((hit) => (
              <li key={hit.product.id}>
                <button
                  type="button"
                  onClick={() => {
                    onChange([...picked, { id: hit.product.id, name: hit.product.name }]);
                    setQuery("");
                    setHits([]);
                  }}
                  className="w-full px-4 py-2 text-left text-sm hover:bg-surface"
                >
                  {hit.product.name}
                </button>
              </li>
            ))}
        </ul>
      ) : null}
      {picked.length ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {picked.map((row) => (
            <span key={row.id} className="inline-flex items-center gap-1 rounded-full bg-surface px-2.5 py-1 text-xs font-medium">
              {row.name}
              <button type="button" aria-label={`Remove ${row.name}`} onClick={() => onChange(picked.filter((item) => item.id !== row.id))}>
                <X size={12} aria-hidden="true" />
              </button>
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

const toLocal = (value: string | null) => (value ? new Date(value).toISOString().slice(0, 16) : "");

function PromotionModal({ promotion, onClose, onSaved }: { promotion: Promotion | null; onClose: () => void; onSaved: (promotion: Promotion) => void }) {
  const { categories } = useCategories();
  const [name, setName] = useState(promotion?.name ?? "");
  const [kind, setKind] = useState<PromotionKind>(promotion?.kind ?? "PERCENT_OFF");
  const [percent, setPercent] = useState(promotion?.percent_bps ? String(promotion.percent_bps / 100) : "10");
  const [buy, setBuy] = useState(String(promotion?.buy_qty ?? 2));
  const [get, setGet] = useState(String(promotion?.get_qty ?? 1));
  const [getPercent, setGetPercent] = useState(promotion?.get_discount_bps ? String(promotion.get_discount_bps / 100) : "100");
  const [groupQty, setGroupQty] = useState(String(promotion?.group_qty ?? 3));
  const [groupPrice, setGroupPrice] = useState(promotion?.group_price_cents != null ? (promotion.group_price_cents / 100).toFixed(2) : "");
  const [bundlePrice, setBundlePrice] = useState(promotion?.bundle_price_cents != null ? (promotion.bundle_price_cents / 100).toFixed(2) : "");
  const nameOf = (id: string) => promotion?.product_names?.[id] ?? "Product";
  const [products, setProducts] = useState<PickedProduct[]>((promotion?.product_ids ?? []).map((id) => ({ id, name: nameOf(id) })));
  const [components, setComponents] = useState<PickedProduct[]>(
    (promotion?.components ?? []).map((part) => ({ id: part.product_id, name: nameOf(part.product_id) })),
  );
  const [categoryId, setCategoryId] = useState(promotion?.category_ids[0] ?? "");
  const [startsAt, setStartsAt] = useState(toLocal(promotion?.starts_at ?? null));
  const [endsAt, setEndsAt] = useState(toLocal(promotion?.ends_at ?? null));
  const [coupon, setCoupon] = useState(promotion?.coupon_code ?? "");
  const [maxUses, setMaxUses] = useState(promotion?.max_uses ? String(promotion.max_uses) : "");
  const [minSpend, setMinSpend] = useState(promotion?.min_spend_cents ? (promotion.min_spend_cents / 100).toFixed(2) : "");
  const [active, setActive] = useState(promotion?.is_active ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    const body: Record<string, unknown> = {
      name: name.trim(),
      kind,
      is_active: active,
      product_ids: kind === "BUNDLE" ? [] : products.map((row) => row.id),
      category_ids: kind === "BUNDLE" || !categoryId ? [] : [categoryId],
      starts_at: startsAt ? new Date(startsAt).toISOString() : null,
      ends_at: endsAt ? new Date(endsAt).toISOString() : null,
      coupon_code: coupon.trim() || null,
      max_uses: maxUses ? Number(maxUses) : null,
      min_spend_cents: minSpend ? (toCents(minSpend) ?? 0) : 0,
    };
    if (kind === "PERCENT_OFF") body.percent_bps = Math.round(Number(percent) * 100);
    if (kind === "BUY_X_GET_Y") Object.assign(body, { buy_qty: Number(buy), get_qty: Number(get), get_discount_bps: Math.round(Number(getPercent) * 100) });
    if (kind === "MIX_MATCH") Object.assign(body, { group_qty: Number(groupQty), group_price_cents: toCents(groupPrice) });
    if (kind === "BUNDLE") Object.assign(body, { components: components.map((row) => ({ product_id: row.id, quantity: 1 })), bundle_price_cents: toCents(bundlePrice) });
    setBusy(true);
    setError(null);
    try {
      onSaved(promotion ? await apiPut<Promotion>(`/api/v1/promotions/${promotion.id}`, body) : await apiPost<Promotion>("/api/v1/promotions", body));
    } catch (caught) {
      setError(errorMessage(caught, "Could not save the promotion."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={promotion ? `Edit ${promotion.name}` : "New promotion"}
      subtitle="Applies to retail sales at every register; the best deal per line wins."
      width="lg"
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            <Tag size={15} aria-hidden="true" className="-ml-1 mr-1.5" /> {busy ? "Saving…" : "Save promotion"}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        <TextField label="Name" value={name} maxLength={80} placeholder="Eid accessory sale" onChange={(event) => setName(event.target.value)} />
        <SegmentedControl label="Deal" value={kind} options={(Object.keys(kindLabels) as PromotionKind[]).map((value) => ({ value, label: kindLabels[value] }))} onChange={setKind} />
        {kind === "PERCENT_OFF" ? <TextField label="Percent off" inputMode="decimal" value={percent} onChange={(event) => setPercent(event.target.value)} /> : null}
        {kind === "BUY_X_GET_Y" ? (
          <div className="grid gap-4 md:grid-cols-3">
            <TextField label="Buy" inputMode="numeric" value={buy} onChange={(event) => setBuy(event.target.value)} />
            <TextField label="Get" inputMode="numeric" value={get} onChange={(event) => setGet(event.target.value)} />
            <TextField label="At % off (100 = free)" inputMode="decimal" value={getPercent} onChange={(event) => setGetPercent(event.target.value)} />
          </div>
        ) : null}
        {kind === "MIX_MATCH" ? (
          <div className="grid gap-4 md:grid-cols-2">
            <TextField label="Any how many" inputMode="numeric" value={groupQty} onChange={(event) => setGroupQty(event.target.value)} />
            <TextField label="For (price, VAT as on the shelf)" inputMode="decimal" value={groupPrice} onChange={(event) => setGroupPrice(event.target.value)} />
          </div>
        ) : null}
        {kind === "BUNDLE" ? (
          <>
            <ProductPicker label="Bundle products (one of each)" picked={components} onChange={setComponents} />
            <TextField label="Bundle price" inputMode="decimal" value={bundlePrice} onChange={(event) => setBundlePrice(event.target.value)} />
          </>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            <ProductPicker label="Products (empty = everything)" picked={products} onChange={setProducts} />
            <FilterSelect
              label="Or a whole category"
              value={categoryId}
              options={[{ value: "", label: "No category" }, ...categories.map((row) => ({ value: row.id, label: row.name }))]}
              onChange={setCategoryId}
            />
          </div>
        )}
        <div className="grid gap-4 md:grid-cols-2">
          <TextField label="Starts (optional)" type="datetime-local" value={startsAt} onChange={(event) => setStartsAt(event.target.value)} />
          <TextField label="Ends (optional)" type="datetime-local" value={endsAt} onChange={(event) => setEndsAt(event.target.value)} />
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <TextField label="Coupon code (optional)" value={coupon} maxLength={32} onChange={(event) => setCoupon(event.target.value.toUpperCase())} />
          <TextField label="Max uses (optional)" inputMode="numeric" value={maxUses} onChange={(event) => setMaxUses(event.target.value.replace(/\D/g, ""))} />
          <TextField label="Minimum spend (optional)" inputMode="decimal" value={minSpend} onChange={(event) => setMinSpend(event.target.value)} />
        </div>
        <Toggle checked={active} onChange={setActive} label="Promotion on" description="Switch off to stop it at every register on their next refresh." />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}
