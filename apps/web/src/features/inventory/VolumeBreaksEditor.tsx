import {
  PRICE_TIERS,
  PRICE_TIER_LABELS,
  formatMoney,
  resolveUnitPrice,
  type PriceTier,
  type PricingRow,
  type ProductPrice,
  type TierPriceWrite,
  type VolumeBreak,
} from "@ai-pos/shared-types";
import { actionHoverClass } from "@ai-pos/ui";
import { Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { centsText, message, toCents } from "../customers/api";
import { pricingApi } from "./pricingApi";

export interface BreakDraft {
  minQty: string;
  price: string;
}

export function draftBreaks(breaks: VolumeBreak[]): BreakDraft[] {
  return breaks.map((item) => ({ minQty: String(item.min_qty), price: centsText(item.price_cents) }));
}

/** Parsed breaks, or the first problem found. */
export function parseBreaks(drafts: BreakDraft[]): VolumeBreak[] | string {
  const breaks: VolumeBreak[] = [];
  for (const draft of drafts) {
    if (draft.minQty.trim() === "" && draft.price.trim() === "") continue;
    const minQty = Number(draft.minQty);
    const price = toCents(draft.price);
    if (!Number.isInteger(minQty) || minQty < 2) return "Each break needs a minimum quantity of 2 or more.";
    if (price === null) return "Each break needs a price such as 9.50.";
    breaks.push({ min_qty: minQty, price_cents: price });
  }
  const quantities = breaks.map((item) => item.min_qty);
  if (new Set(quantities).size !== quantities.length) return "Each break needs a different minimum quantity.";
  return breaks.sort((left, right) => left.min_qty - right.min_qty);
}

const cell =
  "w-full rounded-xl border border-transparent bg-surface px-3 py-2 text-sm tabular-nums focus:border-accent focus:bg-white focus:outline-none";

export function BreakRows({
  breaks,
  currency,
  onChange,
}: {
  breaks: BreakDraft[];
  currency: string;
  onChange: (breaks: BreakDraft[]) => void;
}) {
  const update = (index: number, patch: Partial<BreakDraft>) =>
    onChange(breaks.map((item, position) => (position === index ? { ...item, ...patch } : item)));
  return (
    <div>
      <div className="grid grid-cols-[1fr_1fr_36px] gap-2 text-[11px] font-semibold uppercase tracking-wide text-charcoal/50">
        <span>From quantity (pcs)</span>
        <span>Unit price ({currency})</span>
        <span />
      </div>
      <ul className="mt-1.5 space-y-2">
        {breaks.map((item, index) => (
          <li key={index} className="grid grid-cols-[1fr_1fr_36px] items-center gap-2">
            <input
              aria-label="Minimum quantity"
              inputMode="numeric"
              value={item.minQty}
              placeholder="25"
              onChange={(event) => update(index, { minQty: event.target.value.replace(/\D/g, "") })}
              className={cell}
            />
            <input
              aria-label="Unit price"
              inputMode="decimal"
              value={item.price}
              placeholder="10.00"
              onChange={(event) => update(index, { price: event.target.value })}
              className={cell}
            />
            <button
              type="button"
              aria-label="Remove break"
              onClick={() => onChange(breaks.filter((_, position) => position !== index))}
              className={`flex h-9 w-9 items-center justify-center rounded-full text-charcoal/50 ${actionHoverClass("danger")}`}
            >
              <Trash2 size={15} aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
      <button
        type="button"
        onClick={() => onChange([...breaks, { minQty: "", price: "" }])}
        className="mt-2 inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold text-accent hover:bg-accent/10"
      >
        <Plus size={14} aria-hidden="true" /> Add quantity break
      </button>
    </div>
  );
}

interface TierDraft {
  price: string;
  moq: string;
  breaks: BreakDraft[];
}

function initialDrafts(row: PricingRow): Record<PriceTier, TierDraft> {
  const drafts = {} as Record<PriceTier, TierDraft>;
  for (const tier of PRICE_TIERS) {
    const existing = row.prices.find((item) => item.price_tier === tier);
    drafts[tier] = {
      price: tier === "RETAIL" ? centsText(row.retail_price_cents) : existing ? centsText(existing.price_cents) : "",
      moq: String(existing?.min_order_quantity ?? 1),
      breaks: draftBreaks(existing?.volume_discounts ?? []),
    };
  }
  return drafts;
}

const PREVIEW_QUANTITIES = [1, 5, 10, 25, 50, 100];

interface VolumeBreaksModalProps {
  row: PricingRow;
  currency: string;
  canEdit: boolean;
  onClose: () => void;
  onSaved: (row: PricingRow) => void;
}

export function VolumeBreaksModal({ row, currency, canEdit, onClose, onSaved }: VolumeBreaksModalProps) {
  const [tier, setTier] = useState<PriceTier>("TIER_1");
  const [drafts, setDrafts] = useState(() => initialDrafts(row));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const draft = drafts[tier];

  const built = useMemo((): { tiers: TierPriceWrite[]; retail: number } | string => {
    const retail = toCents(drafts.RETAIL.price);
    if (retail === null) return "Enter the retail price.";
    const tiers: TierPriceWrite[] = [];
    for (const name of PRICE_TIERS) {
      const item = drafts[name];
      const breaks = parseBreaks(item.breaks);
      if (typeof breaks === "string") return `${PRICE_TIER_LABELS[name]}: ${breaks}`;
      const moq = Number(item.moq);
      if (!Number.isInteger(moq) || moq < 1) return `${PRICE_TIER_LABELS[name]}: minimum order must be 1 or more.`;
      // A retail row only exists to carry retail volume breaks; the retail price itself lives on the product.
      const price =
        name === "RETAIL" ? (breaks.length > 0 ? retail : null) : item.price.trim() === "" ? null : toCents(item.price);
      if (name !== "RETAIL" && item.price.trim() !== "" && price === null) {
        return `${PRICE_TIER_LABELS[name]}: enter a price such as 12.00, or leave it empty to inherit.`;
      }
      tiers.push({ price_tier: name, price_cents: price, min_order_quantity: moq, volume_discounts: breaks });
    }
    return { tiers, retail };
  }, [drafts]);

  const previewPrices: ProductPrice[] =
    typeof built === "string"
      ? []
      : built.tiers
          .filter((item) => item.price_cents !== null)
          .map((item) => ({
            price_tier: item.price_tier,
            price_cents: item.price_cents ?? 0,
            min_order_quantity: item.min_order_quantity,
            volume_discounts: item.volume_discounts,
          }));

  const save = async () => {
    if (typeof built === "string") {
      setError(built);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onSaved(
        await pricingApi.updateProduct(row.product_id, { retail_price_cents: built.retail, tiers: built.tiers }),
      );
    } catch (caught) {
      setError(message(caught, "Could not save the prices."));
    } finally {
      setBusy(false);
    }
  };

  const patch = (next: Partial<TierDraft>) => setDrafts((current) => ({ ...current, [tier]: { ...current[tier], ...next } }));

  return (
    <Modal
      title={`${row.name} pricing`}
      subtitle={`${row.sku} · ${row.category}${row.brand ? ` · ${row.brand}` : ""}`}
      onClose={onClose}
      width="lg"
      footer={
        <>
          <GhostButton onClick={onClose}>{canEdit ? "Cancel" : "Close"}</GhostButton>
          {canEdit ? (
            <PrimaryButton disabled={busy} onClick={() => void save()}>
              {busy ? "Saving…" : "Save pricing"}
            </PrimaryButton>
          ) : null}
        </>
      }
    >
      <SegmentedControl
        label="Price tier"
        value={tier}
        options={PRICE_TIERS.map((value) => ({ value, label: PRICE_TIER_LABELS[value] }))}
        onChange={setTier}
      />
      <fieldset disabled={!canEdit} className="mt-5 space-y-5">
        <div className="grid gap-4 md:grid-cols-2">
          <TextField
            label={`${PRICE_TIER_LABELS[tier]} price per piece (${currency})`}
            inputMode="decimal"
            value={draft.price}
            placeholder={tier === "RETAIL" ? "" : "Empty inherits the next lower tier"}
            className="tabular-nums"
            onChange={(event) => patch({ price: event.target.value })}
          />
          <TextField
            label="Minimum order (pcs)"
            inputMode="numeric"
            value={draft.moq}
            hint={tier === "RETAIL" ? "Retail always sells from one piece." : "Below this the next lower tier applies."}
            disabled={tier === "RETAIL"}
            className="tabular-nums"
            onChange={(event) => patch({ moq: event.target.value.replace(/\D/g, "") })}
          />
        </div>
        <BreakRows breaks={draft.breaks} currency={currency} onChange={(breaks) => patch({ breaks })} />
      </fieldset>
      <div className="mt-6 rounded-2xl bg-surface p-4">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-charcoal/50">
          {PRICE_TIER_LABELS[tier]} customer pays per piece
        </p>
        <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-6">
          {PREVIEW_QUANTITIES.map((quantity) => {
            const resolved = resolveUnitPrice(toCents(drafts.RETAIL.price) ?? row.retail_price_cents, previewPrices, tier, quantity);
            return (
              <div key={quantity} className="rounded-xl bg-white px-3 py-2">
                <p className="text-[11px] text-charcoal/50 tabular-nums">{quantity} pcs</p>
                <p className="text-sm font-semibold tabular-nums">{formatMoney(resolved.price_cents, currency)}</p>
                <p className={`text-[10px] ${resolved.source === "volume" ? "text-accent" : "text-charcoal/40"}`}>
                  {resolved.source === "volume" ? "Bulk" : PRICE_TIER_LABELS[resolved.tier]}
                </p>
              </div>
            );
          })}
        </div>
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}
