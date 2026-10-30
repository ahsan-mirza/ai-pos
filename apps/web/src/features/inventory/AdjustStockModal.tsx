import {
  ADD_ONLY_REASONS,
  ADJUSTMENT_NOTE_MIN_LENGTH,
  AdjustmentReason,
  REMOVE_ONLY_REASONS,
  adjustmentReasonLabels,
  formatMoney,
  isValidImei,
  type AdjustmentMode,
  type CostLayerRow,
  type ManualAdjustmentResult,
  type ProductCosting,
  type SerialInput,
  type StockRow,
  type StoreSerial,
} from "@ai-pos/shared-types";
import { Minus, Plus, ScanLine, Search, X } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { ErrorNote, GhostButton, PrimaryButton, SelectField } from "../../components/ui/Field";
import { modalBody, modalFooter, modalHeader } from "../../components/ui/Modal";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { apiGet } from "../../lib/api";
import { useCapabilities } from "../../lib/capabilities";
import { useCurrency } from "../../lib/currency";
import { inventoryApi, message } from "./api";

const modes = [
  { value: "add", label: "+ Add Stock" },
  { value: "remove", label: "− Remove / Deduct Stock" },
  { value: "set", label: "= Set Exact Count" },
] as const;

function majorToCents(raw: string): number | null {
  const trimmed = raw.trim();
  if (!/^\d+(\.\d{0,2})?$/.test(trimmed)) return null;
  const [whole, fraction = ""] = trimmed.split(".");
  return Number(whole) * 100 + Number((fraction + "00").slice(0, 2));
}

function moneyOf(quantity: number, unitCents: number, scale: number): number {
  if (scale === 1) return quantity * unitCents;
  return Math.round((quantity * unitCents) / scale);
}

function removalCost(
  layers: CostLayerRow[],
  quantity: number,
  method: string,
  average: number | null,
  scale: number,
): { cost: number; uncosted: number } {
  const units = Math.abs(quantity);
  if (method === "WEIGHTED_AVERAGE" && average !== null) return { cost: moneyOf(units, average, scale), uncosted: 0 };
  let left = units;
  let cost = 0;
  const ordered = [...layers].sort((leftLayer, rightLayer) => leftLayer.receipt_date.localeCompare(rightLayer.receipt_date));
  for (const layer of ordered) {
    if (left <= 0) break;
    const take = Math.min(left, layer.remaining_quantity);
    cost += moneyOf(take, layer.unit_cost_cents, scale);
    left -= take;
  }
  return { cost, uncosted: left };
}

function serialFor(raw: string): SerialInput | null {
  const value = raw.trim();
  if (value.length < 4 || !/^[A-Za-z0-9-]+$/.test(value)) return null;
  return isValidImei(value) ? { kind: "imei", value } : { kind: "serial", value: value.toUpperCase() };
}

/**
 * Manual override of one branch's stock. The API records each unit change as an immutable ledger row with the
 * reason, explanation, and signed-in user; `adjustmentId` makes accidental double submits a no-op.
 */
export function AdjustStockModal({
  row,
  onClose,
  onAdjusted,
}: {
  row: StockRow;
  onClose: () => void;
  onAdjusted: (result: ManualAdjustmentResult) => void;
}) {
  const titleId = useId();
  const adjustmentId = useRef(crypto.randomUUID());
  const { currency: businessCurrency } = useCurrency();
  const { has } = useCapabilities();
  const trackLots = has("fefo");
  const [mode, setMode] = useState<AdjustmentMode>("add");
  const [quantity, setQuantity] = useState(row.is_serialized ? 0 : 1);
  const [reason, setReason] = useState<AdjustmentReason | "">("");
  const [note, setNote] = useState("");
  const [costing, setCosting] = useState<ProductCosting | null>(null);
  const [unitCost, setUnitCost] = useState("");
  const [landedCost, setLandedCost] = useState("");
  const [supplierRef, setSupplierRef] = useState("");
  const [lotNumber, setLotNumber] = useState("");
  const [expiry, setExpiry] = useState("");
  const [receiptDate, setReceiptDate] = useState("");
  const [historyOpen, setHistoryOpen] = useState(false);
  const costTouched = useRef(false);
  const [scan, setScan] = useState("");
  const [scanned, setScanned] = useState<SerialInput[]>([]);
  const [units, setUnits] = useState<StoreSerial[] | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const serialized = row.is_serialized;
  const storeId = row.store_id;

  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [busy, onClose]);

  useEffect(() => {
    if (storeId === null) return;
    let live = true;
    apiGet<ProductCosting>(`/api/v1/inventory/adjust/cost?product_id=${row.product_id}&store_id=${storeId}`)
      .then((snapshot) => {
        if (!live) return;
        setCosting(snapshot);
        if (!costTouched.current && snapshot.last_purchase_cost_cents !== null) {
          setUnitCost((snapshot.last_purchase_cost_cents / 100).toFixed(2));
        }
      })
      .catch(() => {
        if (live) setCosting(null);
      });
    return () => {
      live = false;
    };
  }, [row.product_id, storeId]);

  useEffect(() => {
    if (!serialized || storeId === null) return;
    inventoryApi
      .storeSerials(row.product_id, storeId)
      .then(setUnits)
      .catch((caught: unknown) => setError(message(caught, "Could not load the IMEIs at this branch.")));
  }, [serialized, row.product_id, storeId]);

  const onHand = row.quantity_on_hand;
  const target = mode === "set" ? quantity : null;
  const change = mode === "add" ? quantity : mode === "remove" ? -quantity : quantity - onHand;
  const after = onHand + change;
  const removable = row.quantity_on_hand - row.quantity_reserved;

  // Serialized stock moves unit by unit: the scanned or selected IMEIs define the quantity.
  useEffect(() => {
    if (!serialized) return;
    if (mode === "add") setQuantity(scanned.length);
    if (mode === "remove") setQuantity(selected.size);
  }, [serialized, mode, scanned.length, selected.size]);

  const reasons = useMemo(
    () =>
      Object.values(AdjustmentReason).filter((value) => {
        if (change > 0) return !REMOVE_ONLY_REASONS.includes(value);
        if (change < 0) return !ADD_ONLY_REASONS.includes(value);
        return true;
      }),
    [change],
  );
  useEffect(() => {
    if (reason !== "" && !reasons.includes(reason)) setReason("");
  }, [reason, reasons]);

  const needScans = serialized && change > 0 ? change : 0;
  const needPicks = serialized && change < 0 ? -change : 0;
  const trimmedNote = note.trim().replace(/\s+/g, " ");
  const scale = row.sold_by_weight ? 1000 : 1;
  const currency = costing?.currency || businessCurrency;
  const unitCents = majorToCents(unitCost);
  const landedCents = landedCost.trim() === "" ? 0 : majorToCents(landedCost);
  const adding = change > 0;
  const layers = costing?.layers ?? [];
  const newest = [...layers].sort((left, right) => right.receipt_date.localeCompare(left.receipt_date));
  const lastLayer = newest[0];
  const previousLayer = newest[1];
  const branch = costing?.stores.find((store) => store.store_id === storeId) ?? costing?.stores[0];
  const removal = change < 0 ? removalCost(layers, change, costing?.method ?? "FIFO", branch?.weighted_average_cost_cents ?? costing?.weighted_average_cost_cents ?? null, scale) : null;
  const acquisition = adding && unitCents !== null && landedCents !== null ? moneyOf(change, unitCents, scale) + landedCents : null;
  const problem = (() => {
    if (storeId === null) return "Select a specific store branch to adjust stock levels.";
    if (!Number.isInteger(quantity) || quantity < 0) return "Enter a whole number.";
    if (change === 0) return mode === "set" ? `The branch already holds ${onHand} units.` : "Adjust by at least one unit.";
    if (change < 0 && -change > removable) {
      return `Only ${removable} units can be removed; ${row.quantity_reserved} are reserved for transfers.`;
    }
    if (needScans && scanned.length !== needScans) return `Scan ${needScans} IMEI/serial number${needScans === 1 ? "" : "s"}.`;
    if (needPicks && selected.size !== needPicks) return `Select ${needPicks} unit${needPicks === 1 ? "" : "s"} to write off.`;
    if (adding && unitCents === null) return "Enter the unit acquisition cost.";
    if (adding && landedCents === null) return "Enter the additional landed cost as a number, or leave it blank.";
    if (reason === "") return "Choose an adjustment reason.";
    if (trimmedNote.length < ADJUSTMENT_NOTE_MIN_LENGTH) {
      return `Explain the adjustment in at least ${ADJUSTMENT_NOTE_MIN_LENGTH} characters.`;
    }
    return null;
  })();

  const addScan = () => {
    const parsed = serialFor(scan);
    if (parsed === null) return setError("That doesn't look like an IMEI or serial number.");
    if (scanned.some((item) => item.value === parsed.value)) return setError(`${parsed.value} is already listed.`);
    if (units?.some((unit) => unit.value === parsed.value)) {
      return setError(`${parsed.value} is already in stock at ${row.store_code}.`);
    }
    setError(null);
    setScanned((current) => [...current, parsed]);
    setScan("");
  };

  const onScanKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      addScan();
    }
  };

  const toggleUnit = (id: string) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else if (!(mode === "set" && next.size >= needPicks)) next.add(id);
      return next;
    });

  const confirm = async () => {
    if (problem !== null || storeId === null || reason === "") return;
    setBusy(true);
    setError(null);
    try {
      onAdjusted(
        await inventoryApi.adjust({
          adjustment_id: adjustmentId.current,
          product_id: row.product_id,
          store_id: storeId,
          mode,
          quantity,
          reason_code: reason,
          note: trimmedNote,
          new_serials: needScans ? scanned : [],
          remove_serial_ids: needPicks ? [...selected] : [],
          unit_cost_cents: adding ? unitCents : null,
          landed_cost_cents: adding ? (landedCents ?? 0) : 0,
          lot_number: adding && trackLots ? lotNumber.trim() || null : null,
          expiry_date: adding && trackLots && expiry ? expiry : null,
          supplier_reference: adding ? supplierRef.trim() || null : null,
          receipt_date: adding && receiptDate ? receiptDate : null,
        }),
      );
    } catch (caught) {
      setError(message(caught, "The adjustment was not recorded."));
    } finally {
      setBusy(false);
    }
  };

  const visibleUnits = (units ?? []).filter((unit) => unit.value.toLowerCase().includes(filter.trim().toLowerCase()));

  return (
    <div className="modal-backdrop fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4 backdrop-blur-sm" role="presentation">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="modal-card flex max-h-[90vh] w-full max-w-[600px] flex-col overflow-hidden rounded-3xl bg-white shadow-2xl"
      >
        <header className={modalHeader}>
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-charcoal/50">Manual stock adjustment</p>
            <h2 id={titleId} className="mt-1 truncate text-xl font-semibold">
              {row.name}
            </h2>
            <p className="mt-0.5 text-sm text-charcoal/60">
              <span className="font-mono text-xs">{row.sku}</span>
              {row.model_name ? ` · ${row.model_name}` : ""} · {row.store_code} · {row.store_name}
              {row.sold_by_weight ? " · weighed, in grams" : ""}
            </p>
          </div>
          <div className="shrink-0 rounded-2xl bg-charcoal px-4 py-2 text-right text-white">
            <p className="text-[10px] uppercase tracking-[0.14em] text-white/60">On hand</p>
            <p className="text-2xl font-semibold tabular-nums">{onHand}</p>
          </div>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            disabled={busy}
            className="-mr-1 -mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-charcoal/70 hover:bg-gray-100"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </header>

        <div className={modalBody}>
        <div>
          <SegmentedControl
            label="Adjustment type"
            value={mode}
            options={modes}
            onChange={(next) => {
              setMode(next);
              setQuantity(next === "set" ? onHand : serialized ? 0 : 1);
              setScanned([]);
              setSelected(new Set());
              setError(null);
            }}
          />
        </div>

        <CostSummary
          costing={costing}
          currency={currency}
          onHand={onHand}
          valueCents={branch?.inventory_value_cents ?? costing?.inventory_value_cents ?? null}
          averageCents={branch?.weighted_average_cost_cents ?? costing?.weighted_average_cost_cents ?? null}
          lastCents={lastLayer?.unit_cost_cents ?? costing?.last_purchase_cost_cents ?? null}
          previousCents={previousLayer?.unit_cost_cents ?? null}
          lastDate={lastLayer?.receipt_date ?? null}
          historyOpen={historyOpen}
          layers={newest}
          weighed={Boolean(row.sold_by_weight)}
          onToggleHistory={() => setHistoryOpen((open) => !open)}
        />

        <div className="mt-5">
          <p className="text-sm font-medium">{mode === "set" ? "Exact counted quantity" : "Adjustment quantity"}</p>
          <div className="mt-1.5 flex items-center gap-3">
            <button
              type="button"
              aria-label="Decrease"
              disabled={(serialized && mode !== "set") || quantity <= 0}
              onClick={() => setQuantity((value) => Math.max(0, value - 1))}
              className="flex h-14 w-14 items-center justify-center rounded-2xl border border-line text-charcoal hover:border-accent hover:text-accent disabled:opacity-30"
            >
              <Minus size={20} aria-hidden="true" />
            </button>
            <input
              type="number"
              inputMode="numeric"
              min={0}
              step={1}
              value={Number.isNaN(quantity) ? "" : quantity}
              readOnly={serialized && mode !== "set"}
              aria-label={mode === "set" ? "Exact counted quantity" : "Adjustment quantity"}
              onChange={(event) => setQuantity(event.target.value === "" ? 0 : Math.floor(Number(event.target.value)))}
              className="h-14 min-w-0 flex-1 rounded-2xl border border-line bg-surface text-center text-3xl font-semibold tabular-nums focus:border-accent focus:bg-white focus:outline-none"
            />
            <button
              type="button"
              aria-label="Increase"
              disabled={serialized && mode !== "set"}
              onClick={() => setQuantity((value) => value + 1)}
              className="flex h-14 w-14 items-center justify-center rounded-2xl border border-line text-charcoal hover:border-accent hover:text-accent disabled:opacity-30"
            >
              <Plus size={20} aria-hidden="true" />
            </button>
          </div>
          <p className="mt-2 text-sm tabular-nums text-charcoal/70">
            {onHand} → <span className="font-semibold text-charcoal">{after}</span>{" "}
            <span className={change < 0 ? "text-accent" : ""}>
              ({change > 0 ? `+${change}` : change}
              {target !== null ? " to match the count" : ""})
            </span>
            {serialized && mode !== "set" ? (
              <span className="ml-2 text-xs text-charcoal/50">Quantity follows the IMEIs below.</span>
            ) : null}
          </p>
          {mode === "set" ? (
            <p className="mt-1 text-sm text-charcoal/70">
              System {onHand} · counted {quantity} · {change === 0 ? "no difference" : change > 0 ? "surplus" : "shortage"}
            </p>
          ) : null}
        </div>

        {adding ? (
          <div className="mt-5 grid gap-4 rounded-2xl border border-line p-4">
            <p className="text-sm font-medium">New stock cost</p>
            <label className="block text-sm font-medium">
              Unit acquisition cost <span className="text-accent">*</span>
              <span className="mt-0.5 block text-xs font-normal text-charcoal/50">
                {row.sold_by_weight ? "Per kilogram" : "Per unit"}. This opens a new cost layer and leaves older layers as they are.
              </span>
              <input
                inputMode="decimal"
                value={unitCost}
                aria-label="Unit acquisition cost"
                onChange={(event) => {
                  costTouched.current = true;
                  setUnitCost(event.target.value);
                }}
                placeholder="0.00"
                className="mt-1.5 h-11 w-full rounded-xl border border-transparent bg-surface px-4 text-sm font-normal tabular-nums focus:border-accent focus:bg-white focus:outline-none"
              />
            </label>
            <label className="block text-sm font-medium">
              Additional landed cost
              <input
                inputMode="decimal"
                value={landedCost}
                aria-label="Additional landed cost"
                onChange={(event) => setLandedCost(event.target.value)}
                placeholder="0.00"
                className="mt-1.5 h-11 w-full rounded-xl border border-transparent bg-surface px-4 text-sm font-normal tabular-nums focus:border-accent focus:bg-white focus:outline-none"
              />
            </label>
            <label className="block text-sm font-medium">
              Supplier / reference
              <input
                value={supplierRef}
                aria-label="Supplier or reference"
                onChange={(event) => setSupplierRef(event.target.value)}
                maxLength={120}
                className="mt-1.5 h-11 w-full rounded-xl border border-transparent bg-surface px-4 text-sm font-normal focus:border-accent focus:bg-white focus:outline-none"
              />
            </label>
            <label className="block text-sm font-medium">
              Stock receipt date
              <input
                type="date"
                value={receiptDate}
                aria-label="Stock receipt date"
                onChange={(event) => setReceiptDate(event.target.value)}
                className="mt-1.5 h-11 w-full rounded-xl border border-transparent bg-surface px-4 text-sm font-normal focus:border-accent focus:bg-white focus:outline-none"
              />
            </label>
            {trackLots ? (
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block text-sm font-medium">
                  Batch / lot number
                  <input
                    value={lotNumber}
                    aria-label="Batch or lot number"
                    onChange={(event) => setLotNumber(event.target.value)}
                    maxLength={32}
                    className="mt-1.5 h-11 w-full rounded-xl border border-transparent bg-surface px-4 text-sm font-normal focus:border-accent focus:bg-white focus:outline-none"
                  />
                </label>
                <label className="block text-sm font-medium">
                  Expiry date
                  <input
                    type="date"
                    value={expiry}
                    aria-label="Expiry date"
                    onChange={(event) => setExpiry(event.target.value)}
                    className="mt-1.5 h-11 w-full rounded-xl border border-transparent bg-surface px-4 text-sm font-normal focus:border-accent focus:bg-white focus:outline-none"
                  />
                </label>
              </div>
            ) : null}
            <p className="text-sm tabular-nums text-charcoal/80">
              {acquisition === null
                ? "Quantity × unit cost + landed cost = total acquisition value"
                : `${change} × ${formatMoney(unitCents ?? 0, currency)}${row.sold_by_weight ? " / kg" : ""} + ${formatMoney(landedCents ?? 0, currency)} = ${formatMoney(acquisition, currency)}`}
            </p>
          </div>
        ) : null}

        {removal !== null ? (
          <div className="mt-5 rounded-2xl border border-line p-4 text-sm">
            <p className="font-medium">{mode === "set" ? "Shortage" : "Stock being removed"}</p>
            <p className="mt-2 tabular-nums text-charcoal/80">
              Estimated inventory cost{" "}
              <span className="font-semibold text-charcoal">{formatMoney(removal.cost, currency)}</span>
              {costing?.method === "WEIGHTED_AVERAGE" ? " at the current weighted average." : " from the oldest cost layers."}
            </p>
            {removal.uncosted > 0 ? (
              <p className="mt-1 text-charcoal/60">{removal.uncosted} units have no recorded acquisition cost.</p>
            ) : (
              <p className="mt-1 text-charcoal/60">Inventory value falls by this amount. Posted sales keep their original cost.</p>
            )}
          </div>
        ) : null}

        {serialized && (mode === "add" || needScans > 0) ? (
          <div className="mt-5 rounded-2xl border border-line p-4">
            <p className="text-sm font-medium">
              New IMEI / serial numbers {needScans ? `(${scanned.length}/${needScans})` : `(${scanned.length})`}
            </p>
            <div className="mt-2 flex gap-2">
              <label className="relative flex-1">
                <span className="sr-only">Scan IMEI</span>
                <ScanLine size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-charcoal/40" />
                <input
                  value={scan}
                  onChange={(event) => setScan(event.target.value)}
                  onKeyDown={onScanKey}
                  placeholder="Scan or type, then Enter"
                  className="h-11 w-full rounded-xl bg-surface pl-9 pr-3 font-mono text-sm focus:outline-accent"
                />
              </label>
              <GhostButton onClick={addScan}>Add</GhostButton>
            </div>
            {scanned.length > 0 ? (
              <ul className="mt-3 flex flex-wrap gap-2">
                {scanned.map((item) => (
                  <li key={item.value} className="flex items-center gap-1 rounded-full bg-surface py-1 pl-3 pr-1 font-mono text-xs">
                    {item.value}
                    <button
                      type="button"
                      aria-label={`Remove ${item.value}`}
                      onClick={() => setScanned((current) => current.filter((entry) => entry.value !== item.value))}
                      className="flex h-6 w-6 items-center justify-center rounded-full hover:bg-white"
                    >
                      <X size={12} aria-hidden="true" />
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}

        {serialized && (mode === "remove" || needPicks > 0) ? (
          <div className="mt-5 rounded-2xl border border-line p-4">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-medium">
                Units to write off {needPicks ? `(${selected.size}/${needPicks})` : `(${selected.size})`}
              </p>
              <label className="relative w-48">
                <span className="sr-only">Search IMEIs</span>
                <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-charcoal/40" />
                <input
                  value={filter}
                  onChange={(event) => setFilter(event.target.value)}
                  placeholder="Search IMEI"
                  className="h-9 w-full rounded-full bg-surface pl-8 pr-3 font-mono text-xs"
                />
              </label>
            </div>
            {units === null ? <p className="mt-3 text-sm text-charcoal/60">Loading units…</p> : null}
            {units !== null && units.length === 0 ? (
              <p className="mt-3 text-sm text-charcoal/60">No units are in stock at {row.store_code}.</p>
            ) : null}
            <ul className="mt-3 max-h-48 space-y-1 overflow-y-auto">
              {visibleUnits.map((unit) => (
                <li key={unit.id}>
                  <label className="flex cursor-pointer items-center gap-3 rounded-xl px-2 py-1.5 hover:bg-surface">
                    <input
                      type="checkbox"
                      checked={selected.has(unit.id)}
                      onChange={() => toggleUnit(unit.id)}
                      className="h-4 w-4 accent-accent"
                    />
                    <span className="font-mono text-sm tabular-nums">{unit.value}</span>
                    <span className="ml-auto text-[11px] uppercase text-charcoal/40">{unit.kind}</span>
                  </label>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="mt-5 grid gap-4">
          <SelectField
            label="Adjustment reason *"
            value={reason}
            placeholder="Choose a reason"
            options={reasons.map((value) => ({ value, label: adjustmentReasonLabels[value] }))}
            onChange={setReason}
          />
          <label className="block text-sm font-medium">
            Explanation <span className="text-accent">*</span>
            <textarea
              value={note}
              onChange={(event) => setNote(event.target.value)}
              rows={3}
              maxLength={1000}
              placeholder="e.g. Found 2 unopened units during annual floor audit"
              className="mt-1.5 w-full rounded-xl border border-transparent bg-surface px-4 py-3 text-sm font-normal focus:border-accent focus:bg-white focus:outline-none"
            />
            <span
              className={`mt-1 block text-xs font-normal tabular-nums ${
                trimmedNote.length >= ADJUSTMENT_NOTE_MIN_LENGTH ? "text-charcoal/50" : "text-accent"
              }`}
            >
              {trimmedNote.length < ADJUSTMENT_NOTE_MIN_LENGTH
                ? `Min ${ADJUSTMENT_NOTE_MIN_LENGTH} characters required (${trimmedNote.length}/${ADJUSTMENT_NOTE_MIN_LENGTH})`
                : `${trimmedNote.length}/1000`}
            </span>
          </label>
        </div>

        {problem !== null && !busy ? <p className="mt-4 text-xs text-charcoal/60">{problem}</p> : null}
        <ErrorNote message={error} />
        </div>

        <footer className={modalFooter}>
          <GhostButton onClick={onClose} disabled={busy}>
            Cancel
          </GhostButton>
          <PrimaryButton disabled={busy || problem !== null} onClick={() => void confirm()}>
            {busy ? "Recording…" : "Confirm Adjustment"}
          </PrimaryButton>
        </footer>
      </div>
    </div>
  );
}

function CostSummary({
  costing,
  currency,
  onHand,
  valueCents,
  averageCents,
  lastCents,
  previousCents,
  lastDate,
  historyOpen,
  layers,
  weighed,
  onToggleHistory,
}: {
  costing: ProductCosting | null;
  currency: string;
  onHand: number;
  valueCents: number | null;
  averageCents: number | null;
  lastCents: number | null;
  previousCents: number | null;
  lastDate: string | null;
  historyOpen: boolean;
  layers: CostLayerRow[];
  weighed: boolean;
  onToggleHistory: () => void;
}) {
  const money = (cents: number | null) => (cents === null ? "—" : formatMoney(cents, currency));
  const method = costing?.method === "WEIGHTED_AVERAGE" ? "Weighted average" : costing ? "FIFO" : "—";
  return (
    <div className="mt-5 rounded-2xl border border-line p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium">Cost information</p>
        <button type="button" onClick={onToggleHistory} className="text-xs font-semibold text-accent">
          {historyOpen ? "Hide cost history" : "View cost history"}
        </button>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <div>
          <dt className="text-charcoal/50">On hand</dt>
          <dd className="font-medium tabular-nums">{onHand}{weighed ? " g" : ""}</dd>
        </div>
        <div>
          <dt className="text-charcoal/50">Inventory value</dt>
          <dd className="font-medium tabular-nums">{money(valueCents)}</dd>
        </div>
        <div>
          <dt className="text-charcoal/50">Valuation method</dt>
          <dd className="font-medium">{method}</dd>
        </div>
        <div>
          <dt className="text-charcoal/50">Weighted average</dt>
          <dd className="font-medium tabular-nums">{money(averageCents)}</dd>
        </div>
        <div>
          <dt className="text-charcoal/50">Last acquisition</dt>
          <dd className="font-medium tabular-nums">{money(lastCents)}</dd>
        </div>
        <div>
          <dt className="text-charcoal/50">Previous acquisition</dt>
          <dd className="font-medium tabular-nums">{money(previousCents)}</dd>
        </div>
        <div className="col-span-2">
          <dt className="text-charcoal/50">Most recent acquisition</dt>
          <dd className="font-medium">{lastDate ? new Date(lastDate).toLocaleDateString() : "Not recorded"}</dd>
        </div>
      </dl>
      {historyOpen ? (
        layers.length === 0 ? (
          <p className="mt-3 text-sm text-charcoal/60">No cost layers at this branch yet.</p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-charcoal/50">
                <tr>
                  <th className="py-1 pr-2 font-medium">Date</th>
                  <th className="py-1 pr-2 font-medium">Source</th>
                  <th className="py-1 pr-2 font-medium">Reference</th>
                  <th className="py-1 pr-2 text-right font-medium">Qty</th>
                  <th className="py-1 pr-2 text-right font-medium">Unit</th>
                  <th className="py-1 text-right font-medium">Remaining</th>
                </tr>
              </thead>
              <tbody>
                {layers.map((layer) => (
                  <tr key={layer.batch_item_id} className="border-t border-line">
                    <td className="py-1.5 pr-2 tabular-nums">{new Date(layer.receipt_date).toLocaleDateString()}</td>
                    <td className="py-1.5 pr-2 capitalize">{layer.source ?? "import"}</td>
                    <td className="py-1.5 pr-2 font-mono">{layer.batch_number}</td>
                    <td className="py-1.5 pr-2 text-right tabular-nums">{layer.original_quantity}</td>
                    <td className="py-1.5 pr-2 text-right tabular-nums">{formatMoney(layer.unit_cost_cents, currency)}</td>
                    <td className="py-1.5 text-right tabular-nums">{layer.remaining_quantity}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : null}
    </div>
  );
}
