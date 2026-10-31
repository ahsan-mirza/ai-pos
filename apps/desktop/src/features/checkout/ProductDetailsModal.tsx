import { formatMoney, formatWeight, Permission, type Availability, type ComboSlot, type ModifierGroup, type ProductUpsert } from "@ai-pos/shared-types";
import { Info, X } from "lucide-react";
import { useEffect, useState } from "react";
import { branchAvailability, productCost, productRecipe } from "../../lib/api";
import { stockTone, stockUnit, type StockTone } from "./catalogCard";
import { ProductPhoto } from "./ProductPhoto";

const TONE_LABEL: Record<StockTone, string> = {
  in: "In stock",
  low: "Low stock",
  out: "Out of stock",
  untracked: "Not tracked",
};

const TAX_LABEL: Record<string, string> = {
  STANDARD: "Standard VAT",
  ZERO: "Zero-rated",
  EXEMPT: "Exempt",
};

const ITEM_LABEL: Record<string, string> = {
  MADE_TO_ORDER: "Made to order",
  RAW_INGREDIENT: "Ingredient",
  PRE_PACKAGED: "Pre-packaged",
};

function tracked(product: ProductUpsert): boolean {
  return product.is_stock_tracked !== false && !product.is_service && !product.has_recipe;
}

function quantityText(product: ProductUpsert, quantity: number): string {
  if (product.sold_by_weight) return formatWeight(quantity);
  const unit = stockUnit(product);
  return unit ? `${quantity} ${unit}` : String(quantity);
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">{label}</dt>
      <dd className="mt-0.5 break-words text-sm text-zinc-900 dark:text-zinc-100">{value}</dd>
    </div>
  );
}

export function ProductDetailsModal({
  product,
  variants,
  title,
  perVariant = false,
  currency,
  online,
  storeId,
  permissions,
  groups,
  combos,
  onClose,
}: {
  product: ProductUpsert;
  /** Other sellable variants of the same model. Each row uses that variant's own stock. */
  variants: ProductUpsert[];
  title?: string;
  /** A style with several sizes or colours. Stock is shown on each variant, not as one total. */
  perVariant?: boolean;
  currency: string;
  online: boolean;
  storeId: string;
  permissions: readonly string[];
  groups: ModifierGroup[];
  combos: ComboSlot[];
  onClose: () => void;
}) {
  const [live, setLive] = useState<Availability | null>(null);
  const [stale, setStale] = useState(!online);
  const [costCents, setCostCents] = useState<number | null>(null);
  const [recipe, setRecipe] = useState<{ notes: string | null; lines: { name: string; quantity: number; weighed: boolean }[] } | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    let cancelled = false;
    setLive(null);
    setCostCents(null);
    setRecipe(null);
    setStale(!online);
    if (!online) return;
    void branchAvailability({ productId: product.id })
      .then((result) => {
        if (!cancelled) setLive(result);
      })
      .catch(() => {
        if (!cancelled) setStale(true);
      });
    if (permissions.includes(Permission.InventoryAdjustStock)) {
      void productCost(product.id, storeId).then((row) => {
        if (cancelled || row === null) return;
        const cents = row.weighted_average_cost_cents ?? row.last_purchase_cost_cents ?? row.default_cost_cents;
        if (cents != null) setCostCents(cents);
      });
    }
    if (permissions.includes(Permission.PortalInventoryManage) && product.has_recipe) {
      void productRecipe(product.id).then((row) => {
        if (cancelled || row === null) return;
        setRecipe({
          notes: row.notes,
          lines: row.lines.map((line) => ({ name: line.ingredient_name, quantity: line.quantity, weighed: line.sold_by_weight })),
        });
      });
    }
    return () => {
      cancelled = true;
    };
  }, [online, permissions, product, storeId]);

  const here = live?.branches.find((branch) => branch.store_id === storeId) ?? null;
  const available = here?.quantity_available ?? product.stock_quantity;
  const tone = stockTone({
    tracked: tracked(product),
    available,
    onHand: here?.quantity_on_hand,
    reorder: here?.min_reorder_level,
  });
  const specs = Object.entries(product.specifications ?? {}).filter(([, value]) => value.trim() !== "");
  const siblings = variants.filter((item) => item.id !== product.id);
  const heading = title ?? product.name;

  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div role="dialog" aria-modal="true" aria-labelledby="product-details-title" className="modal-card max-w-lg">
        <div className="mb-4 flex items-start gap-3">
          <ProductPhoto src={product.thumb_url ?? product.image_url} className="h-16 w-16 shrink-0 rounded-xl object-cover" />
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">{product.category || "Uncategorized"}</p>
            <h2 id="product-details-title" className="text-lg font-semibold leading-snug">{heading}</h2>
            {perVariant ? (
              <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">{variants.length} sizes and colours</p>
            ) : (
              <p className="mt-0.5 font-mono text-xs text-zinc-500 dark:text-zinc-400">{product.sku}</p>
            )}
          </div>
          <button type="button" aria-label="Close" onClick={onClose} className="modal-close">
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${product.is_active === false ? "bg-zinc-200 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300" : "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"}`}>
            {product.is_active === false ? "Inactive" : "Active"}
          </span>
          {perVariant ? null : (
            <span className="rounded-full bg-zinc-100 px-2.5 py-1 text-[11px] font-semibold text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">{TONE_LABEL[tone]}</span>
          )}
          {stale && !perVariant ? <span className="text-[11px] text-amber-700 dark:text-amber-300">Last synchronized stock</span> : null}
        </div>

        <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
          <Field
            label="Selling price"
            value={
              perVariant
                ? (() => {
                    const amounts = variants.map((item) => item.price_cents);
                    const low = Math.min(...amounts);
                    const high = Math.max(...amounts);
                    return low === high ? formatMoney(low, currency) : `${formatMoney(low, currency)} – ${formatMoney(high, currency)}`;
                  })()
                : product.sold_by_weight
                  ? `${formatMoney(product.price_cents, currency)} /kg`
                  : formatMoney(product.price_cents, currency)
            }
          />
          {!perVariant && costCents != null ? <Field label="Cost" value={formatMoney(costCents, currency)} /> : null}
          {!perVariant && product.barcode ? <Field label="Barcode" value={product.barcode} /> : null}
          {product.brand ? <Field label="Brand" value={product.brand} /> : null}
          {!perVariant && product.model_number ? <Field label="Model" value={product.model_number} /> : null}
          {!perVariant && !product.sold_by_weight && stockUnit(product) ? <Field label="Unit" value={stockUnit(product)} /> : null}
          {!perVariant && product.tax_category ? <Field label="Tax" value={TAX_LABEL[product.tax_category] ?? product.tax_category} /> : null}
          {!perVariant ? <Field label="Price includes tax" value={product.price_includes_tax ? "Yes" : "No"} /> : null}
          {!perVariant && product.item_type ? <Field label="Type" value={ITEM_LABEL[product.item_type] ?? product.item_type} /> : null}
          {!perVariant && product.plu_code ? <Field label="PLU" value={product.plu_code} /> : null}
          {!perVariant && product.is_serialized ? <Field label="Tracking" value="IMEI / serial" /> : null}
        </dl>

        <section className="mt-5">
          <h3 className="text-sm font-semibold">Inventory</h3>
          {perVariant ? (
            <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">Each size and colour has its own stock, listed below.</p>
          ) : tracked(product) ? (
            <>
              <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-3">
                <Field label="Available" value={quantityText(product, available)} />
                {here ? <Field label="On hand" value={quantityText(product, here.quantity_on_hand)} /> : null}
                {here && here.quantity_reserved > 0 ? <Field label="Reserved" value={quantityText(product, here.quantity_reserved)} /> : null}
                {here && here.min_reorder_level > 0 ? <Field label="Reorder level" value={quantityText(product, here.min_reorder_level)} /> : null}
              </dl>
              {live && live.branches.length > 0 ? (
                <ul className="mt-3 divide-y divide-zinc-200 text-sm dark:divide-zinc-800">
                  {live.branches.map((branch) => (
                    <li key={branch.store_id} className="flex items-baseline justify-between gap-3 py-1.5">
                      <span className="min-w-0 truncate">{branch.store_name}{branch.is_warehouse ? " · warehouse" : ""}</span>
                      <span className="shrink-0 tabular-nums text-zinc-500">{quantityText(product, branch.quantity_available)}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </>
          ) : (
            <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">Stock tracking not applicable.</p>
          )}
        </section>

        {siblings.length > 0 ? (
          <section className="mt-5">
            <h3 className="text-sm font-semibold">Variants</h3>
            <ul className="mt-2 divide-y divide-zinc-200 text-sm dark:divide-zinc-800">
              {variants.map((item) => (
                <li key={item.id} className="flex items-baseline justify-between gap-3 py-1.5">
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{Object.values(item.variant_attributes ?? {}).join(" · ") || item.name}</span>
                    <span className="block truncate font-mono text-[11px] text-zinc-500">{item.sku}</span>
                  </span>
                  <span className="shrink-0 text-right tabular-nums">
                    <span className="block">{formatMoney(item.price_cents, currency)}</span>
                    <span className="block text-[11px] text-zinc-500">{tracked(item) ? quantityText(item, item.stock_quantity) : "Not tracked"}</span>
                  </span>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {groups.length > 0 ? (
          <section className="mt-5">
            <h3 className="text-sm font-semibold">Modifiers</h3>
            <ul className="mt-2 space-y-2 text-sm">
              {groups.map((group) => (
                <li key={group.id}>
                  <p className="font-medium">{group.name}</p>
                  <p className="text-zinc-500 dark:text-zinc-400">{group.options.filter((option) => option.is_active).map((option) => option.name).join(", ")}</p>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {combos.length > 0 ? (
          <section className="mt-5">
            <h3 className="text-sm font-semibold">Meal choices</h3>
            <ul className="mt-2 space-y-2 text-sm">
              {combos.map((slot) => (
                <li key={slot.id}>
                  <p className="font-medium">{slot.name}</p>
                  <p className="text-zinc-500 dark:text-zinc-400">{slot.options.map((option) => option.name).join(", ")}</p>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {specs.length > 0 ? (
          <section className="mt-5">
            <h3 className="text-sm font-semibold">Details</h3>
            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-3">
              {specs.map(([key, value]) => (
                <Field key={key} label={key.replaceAll("_", " ")} value={value} />
              ))}
            </dl>
          </section>
        ) : null}

        {recipe ? (
          <section className="mt-5">
            <h3 className="text-sm font-semibold">Recipe</h3>
            {recipe.notes ? <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-300">{recipe.notes}</p> : null}
            <ul className="mt-2 text-sm">
              {recipe.lines.map((line) => (
                <li key={line.name} className="flex justify-between gap-3 py-0.5">
                  <span>{line.name}</span>
                  <span className="tabular-nums text-zinc-500">{line.weighed ? formatWeight(line.quantity) : line.quantity}</span>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        <p className="mt-5 flex items-start gap-2 text-[11px] text-zinc-500 dark:text-zinc-400">
          <Info size={14} aria-hidden="true" className="mt-0.5 shrink-0" />
          This view does not change the order.
        </p>
      </div>
    </div>
  );
}
