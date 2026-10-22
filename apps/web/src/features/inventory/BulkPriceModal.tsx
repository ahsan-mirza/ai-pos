import {
  PRICE_TIERS,
  PRICE_TIER_LABELS,
  type BulkPriceMode,
  type BulkPriceResult,
  type BulkPriceUpdate,
  type PriceTier,
} from "@ai-pos/shared-types";
import { useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { Toggle } from "../../components/ui/Toggle";
import { message, toCents } from "../customers/api";
import { pricingApi } from "./pricingApi";
import { BreakRows, parseBreaks, type BreakDraft } from "./VolumeBreaksEditor";

const modes = [
  { value: "percent_of_retail", label: "% of retail" },
  { value: "adjust_percent", label: "Adjust by %" },
  { value: "set", label: "Set exact price" },
] as const;

export interface BulkTarget {
  productIds: string[] | null;
  categoryId: string | null;
  categoryName: string | null;
  brand: string | null;
  count: number;
}

interface BulkPriceModalProps {
  target: BulkTarget;
  currency: string;
  onClose: () => void;
  onDone: (result: BulkPriceResult) => void;
}

export function BulkPriceModal({ target, currency, onClose, onDone }: BulkPriceModalProps) {
  const [tier, setTier] = useState<PriceTier>("TIER_1");
  const [mode, setMode] = useState<BulkPriceMode>("percent_of_retail");
  const [value, setValue] = useState("85");
  const [moq, setMoq] = useState("");
  const [replaceBreaks, setReplaceBreaks] = useState(false);
  const [breaks, setBreaks] = useState<BreakDraft[]>([{ minQty: "25", price: "" }]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scope = target.productIds
    ? `${target.productIds.length} selected ${target.productIds.length === 1 ? "product" : "products"}`
    : [target.categoryName, target.brand].filter(Boolean).join(" · ") || "all products";

  const save = async () => {
    const body: BulkPriceUpdate = {
      product_ids: target.productIds,
      category_id: target.productIds ? null : target.categoryId,
      brand: target.productIds ? null : target.brand,
      price_tier: tier,
      mode,
    };
    if (mode === "set") {
      const cents = toCents(value);
      if (cents === null) {
        setError("Enter the new price, such as 12.50.");
        return;
      }
      body.price_cents = cents;
    } else {
      const percent = Number(value);
      if (!Number.isFinite(percent) || value.trim() === "") {
        setError("Enter a percentage, such as 85 or -5.");
        return;
      }
      body.percent_bps = Math.round(percent * 100);
    }
    if (moq.trim() !== "") {
      const parsed = Number(moq);
      if (!Number.isInteger(parsed) || parsed < 1) {
        setError("Minimum order must be a whole number of pieces.");
        return;
      }
      body.min_order_quantity = parsed;
    }
    if (replaceBreaks) {
      const parsed = parseBreaks(breaks);
      if (typeof parsed === "string") {
        setError(parsed);
        return;
      }
      body.volume_discounts = parsed;
    }
    setBusy(true);
    setError(null);
    try {
      onDone(await pricingApi.bulk(body));
    } catch (caught) {
      setError(message(caught, "Could not update the prices."));
    } finally {
      setBusy(false);
    }
  };

  const hint =
    mode === "percent_of_retail"
      ? "85 sets the tier to 85% of each product's retail price."
      : mode === "adjust_percent"
        ? "-5 lowers each product's current tier price by 5%; 3 raises it by 3%."
        : `Every product in scope gets this exact price (${currency}).`;

  return (
    <Modal
      title="Bulk price update"
      subtitle={`Applies to ${scope} (${target.count} listed)`}
      onClose={onClose}
      width="lg"
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Updating…" : "Apply to products"}
          </PrimaryButton>
        </>
      }
    >
      <div className="grid gap-4 md:grid-cols-2">
        <SelectField
          label="Price tier"
          value={tier}
          options={PRICE_TIERS.map((item) => ({ value: item, label: PRICE_TIER_LABELS[item] }))}
          onChange={setTier}
        />
        <TextField
          label="Minimum order (pcs)"
          inputMode="numeric"
          value={moq}
          placeholder="Leave empty to keep"
          disabled={tier === "RETAIL"}
          onChange={(event) => setMoq(event.target.value.replace(/\D/g, ""))}
        />
      </div>
      <div className="mt-5">
        <SegmentedControl label="Rule" value={mode} options={modes} onChange={setMode} />
      </div>
      <div className="mt-4">
        <TextField
          label={mode === "set" ? `New price (${currency})` : "Percentage"}
          inputMode="decimal"
          value={value}
          hint={hint}
          className="text-lg font-semibold tabular-nums"
          onChange={(event) => setValue(event.target.value)}
        />
      </div>
      <div className="mt-5 space-y-3">
        <Toggle
          label="Replace quantity breaks"
          description="Overwrite the tier's volume discounts on every product in scope"
          checked={replaceBreaks}
          onChange={setReplaceBreaks}
        />
        {replaceBreaks ? <BreakRows breaks={breaks} currency={currency} onChange={setBreaks} /> : null}
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}
