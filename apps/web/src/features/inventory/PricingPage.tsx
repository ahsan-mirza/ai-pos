import {
  PRICE_TIERS,
  PRICE_TIER_LABELS,
  Permission,
  formatMoney,
  type PriceTier,
  type PricingMatrix,
  type PricingRow,
  type UnitType,
} from "@ai-pos/shared-types";
import { actionHoverClass } from "@ai-pos/ui";
import { Layers, Save, Tags } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { DataTable, type DataTableColumn } from "../../components/ui/DataTable";
import { ErrorNote, FilterSelect, PrimaryButton, SearchField } from "../../components/ui/Field";
import { Toast } from "../../components/ui/Toast";
import { useAuth } from "../../lib/auth";
import { useCurrency } from "../../lib/currency";
import { centsText, message, toCents } from "../customers/api";
import { BulkPriceModal, type BulkTarget } from "./BulkPriceModal";
import { pricingApi } from "./pricingApi";
import { useCategories } from "./shared";
import { useUnits } from "./units";
import { VolumeBreaksModal } from "./VolumeBreaksEditor";

/** Typed cell values per product; only rows the user touched are present. */
type Draft = Partial<Record<PriceTier, string>> & { units?: UnitType[] };

function tierPrice(row: PricingRow, tier: PriceTier): number | null {
  if (tier === "RETAIL") return row.retail_price_cents;
  return row.prices.find((item) => item.price_tier === tier)?.price_cents ?? null;
}

export function PricingPage() {
  const { can } = useAuth();
  const { currency } = useCurrency();
  const { categories } = useCategories();
  const canEdit = can(Permission.PortalPricingManage);
  const { units: packOptions } = useUnits();
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const [brand, setBrand] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [matrix, setMatrix] = useState<PricingMatrix | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [breaksFor, setBreaksFor] = useState<PricingRow | null>(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query), 150);
    return () => window.clearTimeout(timer);
  }, [query]);

  const load = useCallback(async () => {
    try {
      setMatrix(await pricingApi.matrix({ category_id: categoryId, brand, q: debounced.trim() || null }));
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not load prices."));
    }
  }, [categoryId, brand, debounced]);

  useEffect(() => {
    void load();
  }, [load]);

  const rows = matrix?.rows ?? [];
  const shown = matrix?.currency ?? currency;
  const dirty = Object.keys(drafts);
  const allSelected = rows.length > 0 && rows.every((row) => selected.has(row.product_id));

  const summary = useMemo(() => {
    const wholesale = rows.filter((row) => row.prices.some((item) => item.price_tier !== "RETAIL"));
    const margins = rows
      .map((row) => {
        const t1 = tierPrice(row, "TIER_1");
        return t1 !== null && row.retail_price_cents > 0 ? 1 - t1 / row.retail_price_cents : null;
      })
      .filter((value): value is number => value !== null);
    const breaks = rows.reduce((sum, row) => sum + row.prices.reduce((count, item) => count + item.volume_discounts.length, 0), 0);
    return {
      priced: wholesale.length,
      discount: margins.length ? Math.round((margins.reduce((a, b) => a + b, 0) / margins.length) * 1000) / 10 : null,
      breaks,
    };
  }, [rows]);

  const setCell = (row: PricingRow, tier: PriceTier, value: string) =>
    setDrafts((current) => ({ ...current, [row.product_id]: { ...current[row.product_id], [tier]: value } }));

  const toggleUnit = (row: PricingRow, unit: UnitType) => {
    if (unit === "PIECE" || row.is_serialized) return;
    const base = drafts[row.product_id]?.units ?? row.sellable_units;
    const units = base.includes(unit) ? base.filter((item) => item !== unit) : [...base, unit];
    setDrafts((current) => ({ ...current, [row.product_id]: { ...current[row.product_id], units } }));
  };

  const saveRow = async (row: PricingRow): Promise<boolean> => {
    const draft = drafts[row.product_id];
    if (!draft) return true;
    const body: Parameters<typeof pricingApi.updateProduct>[1] = {};
    if (draft.RETAIL !== undefined) {
      const cents = toCents(draft.RETAIL);
      if (cents === null) {
        setError(`${row.name}: enter a retail price such as 15.00.`);
        return false;
      }
      body.retail_price_cents = cents;
    }
    const tiers = [];
    for (const tier of PRICE_TIERS.filter((item) => item !== "RETAIL")) {
      const typed = draft[tier];
      if (typed === undefined) continue;
      const existing = row.prices.find((item) => item.price_tier === tier);
      const cents = typed.trim() === "" ? null : toCents(typed);
      if (typed.trim() !== "" && cents === null) {
        setError(`${row.name}: ${PRICE_TIER_LABELS[tier]} needs a price such as 12.00, or empty to inherit.`);
        return false;
      }
      tiers.push({
        price_tier: tier,
        price_cents: cents,
        min_order_quantity: existing?.min_order_quantity ?? 1,
        volume_discounts: existing?.volume_discounts ?? [],
      });
    }
    if (tiers.length) body.tiers = tiers;
    if (draft.units) body.sellable_units = draft.units.length ? draft.units : ["PIECE"];
    try {
      const saved = await pricingApi.updateProduct(row.product_id, body);
      setMatrix((current) =>
        current ? { ...current, rows: current.rows.map((item) => (item.product_id === saved.product_id ? saved : item)) } : current,
      );
      setDrafts((current) => {
        const next = { ...current };
        delete next[row.product_id];
        return next;
      });
      return true;
    } catch (caught) {
      setError(message(caught, `Could not save ${row.name}.`));
      return false;
    }
  };

  const saveAll = async () => {
    setSaving(true);
    setError(null);
    let saved = 0;
    for (const row of rows.filter((item) => drafts[item.product_id])) {
      if (await saveRow(row)) saved += 1;
    }
    setSaving(false);
    if (saved) setToast(`Prices saved for ${saved} ${saved === 1 ? "product" : "products"}.`);
  };

  const bulkTarget: BulkTarget = {
    productIds: selected.size ? [...selected] : null,
    categoryId,
    categoryName: categories.find((item) => item.id === categoryId)?.name ?? null,
    brand,
    count: selected.size || rows.length,
  };

  const toggleSelected = (productId: string) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(productId)) next.delete(productId);
      else next.add(productId);
      return next;
    });

  const columns: DataTableColumn<PricingRow>[] = [
    ...(canEdit
      ? [
          {
            id: "select",
            width: 40,
            header: (
              <input
                type="checkbox"
                aria-label="Select all"
                checked={allSelected}
                onChange={() => setSelected(allSelected ? new Set() : new Set(rows.map((row) => row.product_id)))}
                className="h-4 w-4 accent-accent"
              />
            ),
            cell: (row: PricingRow) => (
              <input
                type="checkbox"
                aria-label={`Select ${row.name}`}
                checked={selected.has(row.product_id)}
                onChange={() => toggleSelected(row.product_id)}
                className="h-4 w-4 accent-accent"
              />
            ),
          },
        ]
      : []),
    {
      id: "product",
      header: "Product",
      cell: (row) => (
        <>
          <span className="block font-medium">{row.name}</span>
          <span className="block text-xs text-charcoal/50">
            <span className="font-mono">{row.sku}</span> · {[row.brand, row.category].filter(Boolean).join(" · ")}
          </span>
        </>
      ),
    },
    ...PRICE_TIERS.map(
      (tier): DataTableColumn<PricingRow> => ({
        id: tier,
        header: PRICE_TIER_LABELS[tier],
        align: "right",
        cell: (row) => {
          const current = tierPrice(row, tier);
          const typed = drafts[row.product_id]?.[tier];
          const tierRow = row.prices.find((item) => item.price_tier === tier);
          return (
            <>
              {canEdit ? (
                <input
                  aria-label={`${row.name} ${PRICE_TIER_LABELS[tier]} price`}
                  inputMode="decimal"
                  value={typed ?? (current === null ? "" : centsText(current))}
                  placeholder="Inherits"
                  onChange={(event) => setCell(row, tier, event.target.value)}
                  className={`ml-auto block w-28 rounded-xl border px-3 py-2 text-right text-sm font-semibold tabular-nums transition-colors placeholder:font-normal placeholder:text-charcoal/30 focus:border-accent focus:bg-white focus:outline-none ${
                    typed !== undefined ? "border-accent bg-white" : "border-transparent bg-surface"
                  }`}
                />
              ) : (
                <span className="font-semibold tabular-nums">{current === null ? "—" : formatMoney(current, shown)}</span>
              )}
              {tierRow && tierRow.min_order_quantity > 1 ? (
                <span className="mt-1 block text-[11px] tabular-nums text-charcoal/50">min {tierRow.min_order_quantity}</span>
              ) : null}
            </>
          );
        },
      }),
    ),
    {
      id: "units",
      header: "Sold as",
      className: "pl-6",
      cell: (row) => {
        const units = drafts[row.product_id]?.units ?? row.sellable_units;
        return (
          <div className="flex gap-1">
            {packOptions.filter((unit) => unit.is_active || units.includes(unit.code)).map((unit) => {
              const on = units.includes(unit.code);
              const locked = unit.code === "PIECE" || row.is_serialized || !canEdit;
              return (
                <button
                  key={unit.code}
                  type="button"
                  aria-pressed={on}
                  disabled={locked}
                  title={`${unit.name} (${unit.factor} pcs)`}
                  onClick={() => toggleUnit(row, unit.code)}
                  className={`h-8 rounded-full px-3 text-xs font-semibold transition-colors ${
                    on ? "bg-charcoal text-white" : "border border-line text-charcoal/50 hover:text-charcoal"
                  } ${locked && unit.code !== "PIECE" ? "cursor-not-allowed opacity-40" : ""}`}
                >
                  {unit.short_name}
                </button>
              );
            })}
          </div>
        );
      },
    },
    {
      id: "breaks",
      header: "Breaks",
      align: "right",
      cell: (row) => {
        const breakCount = row.prices.reduce((sum, item) => sum + item.volume_discounts.length, 0);
        return (
          <button
            type="button"
            onClick={() => setBreaksFor(row)}
            className={`inline-flex h-9 items-center gap-1.5 whitespace-nowrap rounded-full border border-line px-3.5 text-xs font-semibold ${actionHoverClass("primary")}`}
          >
            {breakCount ? `${breakCount} ${breakCount === 1 ? "break" : "breaks"}` : canEdit ? "Add breaks" : "None"}
          </button>
        );
      },
    },
  ];

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">Products with wholesale tiers</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">
            {summary.priced}
            <span className="text-xl text-white/50"> / {rows.length}</span>
          </p>
          <p className="mt-2 text-xs text-white/50">Products without tiers sell at retail to everyone</p>
        </article>
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">Average Tier 1 discount</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{summary.discount === null ? "—" : `${summary.discount}%`}</p>
          <p className="mt-2 text-xs text-white/80">Below retail, across products with a Tier 1 price</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Quantity break rules</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{summary.breaks}</p>
          <p className="mt-2 text-xs text-charcoal/50">Applied automatically at the register as carts grow</p>
        </article>
      </div>

      <div className="overflow-hidden rounded-card border border-line bg-white">
        <div className="flex flex-wrap items-end gap-3 p-6 pb-5">
          <FilterSelect
            label="Category"
            className="min-w-[200px]"
            value={categoryId ?? ""}
            options={[{ value: "", label: "All categories" }, ...categories.map((item) => ({ value: item.id, label: item.name }))]}
            onChange={(next) => setCategoryId(next === "" ? null : next)}
          />
          <FilterSelect
            label="Brand"
            className="min-w-[180px]"
            value={brand ?? ""}
            options={[{ value: "", label: "All brands" }, ...(matrix?.brands ?? []).map((item) => ({ value: item, label: item }))]}
            onChange={(next) => setBrand(next === "" ? null : next)}
          />
          <SearchField
            className="min-w-[220px] flex-1"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Product name or SKU"
          />
          {canEdit ? (
            <>
              <button
                type="button"
                onClick={() => setBulkOpen(true)}
                disabled={rows.length === 0}
                className={`inline-flex h-11 items-center gap-2 rounded-full border border-line bg-white px-5 text-sm font-semibold disabled:opacity-40 ${actionHoverClass("primary")}`}
              >
                <Layers size={16} aria-hidden="true" />
                Bulk update{selected.size ? ` (${selected.size})` : ""}
              </button>
              <PrimaryButton disabled={dirty.length === 0 || saving} onClick={() => void saveAll()}>
                <Save size={16} aria-hidden="true" className="-ml-2 mr-2" />
                {saving ? "Saving…" : dirty.length ? `Save ${dirty.length} ${dirty.length === 1 ? "change" : "changes"}` : "Saved"}
              </PrimaryButton>
            </>
          ) : null}
        </div>
        {error ? (
          <div className="px-6 pb-5">
            <ErrorNote message={error} />
          </div>
        ) : null}
        <DataTable
          aria-label="Price tier matrix"
          variant="flush"
          minWidth="1180px"
          columns={columns}
          data={rows}
          getRowId={(row) => row.product_id}
          isLoading={matrix === null && error === null}
          rowClassName={(row) => (drafts[row.product_id] ? "bg-accent/[0.04]" : "")}
          emptyState={{ icon: Tags, title: "No products match these filters" }}
          pagination={{ mode: "client", resetKey: [categoryId, brand, debounced] }}
        />
        {canEdit ? (
          <p className="border-t border-line px-5 py-3 text-xs text-charcoal/50">
            Empty tier prices inherit the next lower tier. Volume breaks and minimum orders are edited per product.
          </p>
        ) : null}
      </div>

      {breaksFor ? (
        <VolumeBreaksModal
          row={breaksFor}
          currency={shown}
          canEdit={canEdit}
          onClose={() => setBreaksFor(null)}
          onSaved={(saved) => {
            setBreaksFor(null);
            setMatrix((current) =>
              current ? { ...current, rows: current.rows.map((item) => (item.product_id === saved.product_id ? saved : item)) } : current,
            );
            setToast(`${saved.name} pricing saved.`);
          }}
        />
      ) : null}
      {bulkOpen ? (
        <BulkPriceModal
          target={bulkTarget}
          currency={shown}
          onClose={() => setBulkOpen(false)}
          onDone={(result) => {
            setBulkOpen(false);
            setSelected(new Set());
            setToast(`Updated ${result.updated} ${result.updated === 1 ? "product" : "products"}${result.skipped ? `, skipped ${result.skipped}` : ""}.`);
            void load();
          }}
        />
      ) : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}
