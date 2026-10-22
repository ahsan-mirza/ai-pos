import {
  ADD_ONLY_REASONS,
  ADJUSTMENT_NOTE_MIN_LENGTH,
  AdjustmentReason,
  REMOVE_ONLY_REASONS,
  adjustmentReasonLabels,
  isValidImei,
  type AdjustmentMode,
  type ManualAdjustmentResult,
  type SerialInput,
  type StockRow,
  type StoreSerial,
} from "@ai-pos/shared-types";
import { Minus, Plus, ScanLine, Search, X } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { ErrorNote, GhostButton, PrimaryButton, SelectField } from "../../components/ui/Field";
import { modalBody, modalFooter, modalHeader } from "../../components/ui/Modal";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { inventoryApi, message } from "./api";

const modes = [
  { value: "add", label: "+ Add Stock" },
  { value: "remove", label: "− Remove / Deduct Stock" },
  { value: "set", label: "= Set Exact Count" },
] as const;

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
  const [mode, setMode] = useState<AdjustmentMode>("add");
  const [quantity, setQuantity] = useState(row.is_serialized ? 0 : 1);
  const [reason, setReason] = useState<AdjustmentReason | "">("");
  const [note, setNote] = useState("");
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
  const problem = (() => {
    if (storeId === null) return "Select a specific store branch to adjust stock levels.";
    if (!Number.isInteger(quantity) || quantity < 0) return "Enter a whole number.";
    if (change === 0) return mode === "set" ? `The branch already holds ${onHand} units.` : "Adjust by at least one unit.";
    if (change < 0 && -change > removable) {
      return `Only ${removable} units can be removed; ${row.quantity_reserved} are reserved for transfers.`;
    }
    if (needScans && scanned.length !== needScans) return `Scan ${needScans} IMEI/serial number${needScans === 1 ? "" : "s"}.`;
    if (needPicks && selected.size !== needPicks) return `Select ${needPicks} unit${needPicks === 1 ? "" : "s"} to write off.`;
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
              <span className="font-mono text-xs">{row.sku}</span> · {row.store_code} · {row.store_name}
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
        </div>

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
