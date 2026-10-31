import { formatMoney, variantAttributeLabel, type ProductUpsert } from "@ai-pos/shared-types";
import { Grid3x3, Package, X } from "lucide-react";
import { useMemo, useState } from "react";
import { stockPill } from "../../components/shell/tokens";
import { CatalogTile } from "./ProductCard";
import { ProductPhoto } from "./ProductPhoto";
import { findVariant, swatchFor, variantAxes, type ModelGroup } from "./variants";

export function ModelCard({
  group,
  currency,
  disabled,
  onOpen,
  onInfo,
}: {
  group: ModelGroup;
  currency: string;
  disabled: boolean;
  onOpen: () => void;
  onInfo: () => void;
}) {
  const out = group.stock <= 0;
  const first = group.variants[0];
  const stockLabel = out ? "Out of stock" : "In stock";
  return (
    <CatalogTile
      imageSrc={group.variants.find((variant) => variant.thumb_url)?.thumb_url}
      imageIcon={<Package size={28} aria-hidden="true" />}
      imageDimmed={out}
      category={[first?.category ?? "Uncategorized", first?.season, first?.collection].filter(Boolean).join(" · ")}
      marker={<Grid3x3 size={14} aria-label="Has sizes or colours" className="shrink-0 text-primary" />}
      title={group.name}
      price={
        <span className="text-zinc-900 dark:text-white">
          {group.fromCents === group.toCents
            ? formatMoney(group.fromCents, currency)
            : `${formatMoney(group.fromCents, currency)} – ${formatMoney(group.toCents, currency)}`}
        </span>
      }
      badge={
        <span title={stockLabel} className={`inline-flex h-7 max-w-full items-center truncate rounded-full px-2.5 text-[11px] font-semibold tabular-nums ${stockPill[out ? "out" : "in"]}`}>
          {stockLabel}
        </span>
      }
      disabled={disabled}
      onSelect={onOpen}
      onInfo={onInfo}
      action={
        <button
          type="button"
          disabled={disabled}
          onClick={onOpen}
          className="flex h-12 shrink-0 items-center justify-center border-t border-zinc-200 text-sm font-semibold text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/70 disabled:opacity-50 dark:border-zinc-800"
        >
          Choose size & colour
        </button>
      }
    />
  );
}

/** Size x colour grid with this register's stock; tapping a cell adds that variant. */
export function VariantPickerModal({
  group,
  currency,
  title,
  onPick,
  onClose,
}: {
  group: ModelGroup;
  currency: string;
  title?: string;
  onPick: (product: ProductUpsert) => void;
  onClose: () => void;
}) {
  const axes = useMemo(() => variantAxes(group.variants), [group.variants]);
  const [rowAxis, columnAxis, pageAxis] = axes;
  const [page, setPage] = useState(pageAxis?.values[0] ?? null);
  // The colour's own photo, so the picture follows the colour column (or the colour tab).
  const photoFor = (key: string, value: string | null) =>
    value === null
      ? null
      : (group.variants.find((variant) => variant.variant_attributes?.[key] === value && variant.thumb_url)?.thumb_url ?? null);
  const pagePhoto = pageAxis ? photoFor(pageAxis.key, page) : null;

  return (
    <div
      className="modal-backdrop fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title ?? `Choose ${group.name}`}
        className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-3xl bg-white p-6 shadow-2xl dark:bg-zinc-900"
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <ProductPhoto
              src={pagePhoto ?? group.variants.find((variant) => variant.thumb_url)?.thumb_url}
              className="h-16 w-16 shrink-0 rounded-xl object-cover"
            />
            <div>
              <h2 className="text-lg font-semibold">{title ?? group.name}</h2>
              <p className="text-sm text-zinc-500 dark:text-white/50">
                Tap a size and colour. Numbers are units in stock at this register's branch.
              </p>
            </div>
          </div>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="flex h-10 w-10 items-center justify-center rounded-full text-zinc-500 hover:bg-zinc-100 dark:hover:bg-white/10"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        {pageAxis ? (
          <div className="mb-3 flex flex-wrap gap-1.5" role="tablist" aria-label={variantAttributeLabel(pageAxis.key)}>
            {pageAxis.values.map((value) => (
              <button
                key={value}
                type="button"
                role="tab"
                aria-selected={value === page}
                onClick={() => setPage(value)}
                className={`h-9 rounded-full px-4 text-sm font-semibold ${value === page ? "bg-primary text-white" : "bg-zinc-100 text-zinc-700 dark:bg-white/10 dark:text-white/70"}`}
              >
                {value}
              </button>
            ))}
          </div>
        ) : null}

        {rowAxis ? (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr>
                  <th className="pb-2 pr-2 text-left text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
                    {variantAttributeLabel(rowAxis.key)}
                  </th>
                  {(columnAxis?.values ?? [""]).map((column) => {
                    const swatch = columnAxis ? swatchFor(group.variants, columnAxis.key, column) : null;
                    return (
                    <th key={column} className="px-1 pb-2 text-center text-xs font-semibold">
                      {columnAxis ? (
                        <ProductPhoto
                          src={photoFor(columnAxis.key, column)}
                          className="mx-auto mb-1 h-12 w-12 rounded-lg object-cover"
                        />
                      ) : null}
                      <span className="inline-flex items-center justify-center gap-1">
                        {swatch ? (
                          <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-full border border-black/10" style={{ backgroundColor: swatch }} />
                        ) : null}
                        {column}
                      </span>
                    </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {rowAxis.values.map((row) => (
                  <tr key={row}>
                    <th scope="row" className="pr-2 text-left text-sm font-semibold">
                      {row}
                    </th>
                    {(columnAxis?.values ?? [""]).map((column) => {
                      const wanted: Record<string, string> = { [rowAxis.key]: row };
                      if (columnAxis) wanted[columnAxis.key] = column;
                      if (pageAxis && page) wanted[pageAxis.key] = page;
                      const product = findVariant(group.variants, wanted);
                      if (!product) {
                        return (
                          <td key={column} className="p-1">
                            <span className="flex h-16 items-center justify-center rounded-xl border border-dashed border-zinc-200 text-xs text-zinc-300 dark:border-zinc-800 dark:text-zinc-600">
                              —
                            </span>
                          </td>
                        );
                      }
                      const out = product.stock_quantity <= 0;
                      return (
                        <td key={column} className="p-1">
                          <button
                            type="button"
                            disabled={out}
                            onClick={() => onPick(product)}
                            title={`${product.name} · ${product.sku}`}
                            className={`flex h-16 w-full min-w-[84px] flex-col items-center justify-center rounded-xl border text-center transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 ${
                              out
                                ? "cursor-not-allowed border-zinc-200 bg-zinc-50 text-zinc-400 dark:border-zinc-800 dark:bg-white/[0.02]"
                                : "border-zinc-200 hover:border-primary hover:bg-primary/5 dark:border-zinc-700"
                            }`}
                          >
                            <span className="text-base font-bold tabular-nums">{out ? "0" : product.stock_quantity}</span>
                            <span className="text-[10px] tabular-nums text-zinc-500 dark:text-white/50">
                              {out ? "out" : formatMoney(product.price_cents, currency)}
                            </span>
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    </div>
  );
}
