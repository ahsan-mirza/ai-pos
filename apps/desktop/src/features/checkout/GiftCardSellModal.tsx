import { formatMoney, type GiftCardProduct, type ProductUpsert } from "@ai-pos/shared-types";
import { Gift, Loader2, X } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { giftCardsApi, newGiftCardCode } from "../../lib/retailClient";
import { parseCents } from "./tenders";

interface GiftCardSellModalProps {
  currency: string;
  storeId: string;
  onClose: () => void;
  onAdd: (product: ProductUpsert, amountCents: number, code: string) => void;
}

const PRESETS = [10_000, 20_000, 50_000, 100_000];

/** The gift card service product as a cart product; it came from the API, so the sale never re-creates it. */
function asProduct(product: GiftCardProduct, storeId: string, currency: string): ProductUpsert {
  return {
    id: product.product_id,
    store_id: storeId,
    sku: product.sku,
    barcode: product.sku,
    name: product.name,
    category: "Gift cards",
    price_cents: 0,
    currency,
    is_serialized: false,
    stock_quantity: 0,
    is_service: true,
    tax_category: "ZERO",
    origin: "api",
  } as ProductUpsert;
}

/** Loads a new gift card: pick the amount, the register draws the code, the card is live once the sale syncs. */
export function GiftCardSellModal({ currency, storeId, onClose, onAdd }: GiftCardSellModalProps) {
  const titleId = useId();
  const [product, setProduct] = useState<GiftCardProduct | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [amount, setAmount] = useState("");

  useEffect(() => {
    giftCardsApi
      .product()
      .then(setProduct)
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : String(caught)));
  }, []);

  const cents = parseCents(amount);
  const inRange = product !== null && cents !== null && cents >= product.min_cents && cents <= product.max_cents;

  return (
    <div className="modal-backdrop" role="presentation">
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="modal-card max-w-md">
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-primary/15 text-primary">
            <Gift size={20} aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-xl font-semibold">
              Sell a gift card
            </h2>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              {product
                ? `${formatMoney(product.min_cents, currency)} to ${formatMoney(product.max_cents, currency)}${
                    product.expiry_months ? ` · valid ${product.expiry_months} months` : " · never expires"
                  }`
                : "Loading the gift card rules…"}
            </p>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} className="modal-close">
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        {product === null && error === null ? (
          <p className="mt-6 flex items-center gap-2 text-sm text-zinc-500">
            <Loader2 size={16} className="animate-spin" aria-hidden="true" /> Connecting…
          </p>
        ) : null}
        {error && product === null ? (
          <p role="alert" className="mt-5 text-sm font-medium text-red-600 dark:text-red-400">
            Gift cards need the server the first time: {error}
          </p>
        ) : null}
        {product ? (
          <form
            className="mt-5 space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (inRange && cents !== null) onAdd(asProduct(product, storeId, currency), cents, newGiftCardCode());
            }}
          >
            <div className="grid grid-cols-4 gap-2">
              {PRESETS.filter((preset) => preset >= product.min_cents && preset <= product.max_cents).map((preset) => (
                <button
                  key={preset}
                  type="button"
                  onClick={() => setAmount((preset / 100).toFixed(2))}
                  className={`h-11 rounded-xl border text-sm font-semibold tabular-nums ${
                    cents === preset ? "border-primary bg-primary/10" : "border-zinc-200 dark:border-zinc-700"
                  }`}
                >
                  {formatMoney(preset, currency)}
                </button>
              ))}
            </div>
            <label className="block text-sm font-medium">
              Amount
              <input
                autoFocus
                inputMode="decimal"
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
                placeholder="250.00"
                className="modal-input mt-1.5 text-lg font-semibold tabular-nums"
              />
            </label>
            {cents !== null && !inRange ? (
              <p role="alert" className="text-sm text-red-600 dark:text-red-400">
                Load between {formatMoney(product.min_cents, currency)} and {formatMoney(product.max_cents, currency)}.
              </p>
            ) : null}
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              The card's code prints on the receipt. It carries no VAT; VAT is charged on what it later buys.
            </p>
            <div className="flex justify-end gap-3 pt-2">
              <button type="button" onClick={onClose} className="modal-cancel">
                Cancel
              </button>
              <button type="submit" className="modal-save" disabled={!inRange}>
                Add {cents !== null && inRange ? formatMoney(cents, currency) : "card"}
              </button>
            </div>
          </form>
        ) : null}
      </div>
    </div>
  );
}
