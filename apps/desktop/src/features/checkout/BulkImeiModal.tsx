import type { ProductUpsert } from "@ai-pos/shared-types";
import { ClipboardList, ScanLine, Sparkles, X } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { availableSerials, checkSerials, countSerials, parseIdentifiers } from "./wholesaleClient";

type SlotStatus = "available" | "unknown" | "invalid" | "duplicate" | "taken" | "other_product";

interface Slot {
  value: string;
  kind: "imei" | "serial";
  status: SlotStatus;
}

const blocking: SlotStatus[] = ["invalid", "duplicate", "taken", "other_product"];

const statusText: Record<SlotStatus, string> = {
  available: "In stock here",
  unknown: "Not in this branch's list",
  invalid: "Failed the IMEI check",
  duplicate: "Already scanned",
  taken: "Already sold on this register",
  other_product: "Belongs to another product",
};

type Tab = "scan" | "paste" | "auto";

const tabs: { value: Tab; label: string; icon: typeof ScanLine }[] = [
  { value: "scan", label: "Multi-scan", icon: ScanLine },
  { value: "paste", label: "Paste list", icon: ClipboardList },
  { value: "auto", label: "Auto-assign", icon: Sparkles },
];

interface BulkImeiModalProps {
  product: ProductUpsert;
  /** Identifiers already in the cart. */
  inCart: string[];
  initialQuantity?: number;
  onClose: () => void;
  onConfirm: (serials: { value: string; kind: "imei" | "serial" }[]) => void;
}

export function BulkImeiModal({ product, inCart, initialQuantity = 10, onClose, onConfirm }: BulkImeiModalProps) {
  const titleId = useId();
  const [target, setTarget] = useState(String(initialQuantity));
  const [tab, setTab] = useState<Tab>("scan");
  const [slots, setSlots] = useState<Slot[]>([]);
  const [scan, setScan] = useState("");
  const [paste, setPaste] = useState("");
  const [free, setFree] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const scanRef = useRef<HTMLInputElement>(null);

  const wanted = Math.max(1, Math.min(500, Number(target) || 0));
  const errors = slots.filter((slot) => blocking.includes(slot.status)).length;
  const warnings = slots.filter((slot) => slot.status === "unknown").length;
  const usable = slots.filter((slot) => !blocking.includes(slot.status));
  const remaining = Math.max(0, wanted - slots.length);

  useEffect(() => {
    void countSerials(product.id).then(setFree);
  }, [product.id]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  useEffect(() => {
    if (tab === "scan") scanRef.current?.focus();
  }, [tab]);

  const taken = useMemo(() => new Set([...inCart, ...slots.map((slot) => slot.value)]), [inCart, slots]);

  const addValues = async (raw: string) => {
    const parsed = parseIdentifiers(raw);
    if (parsed.length === 0) return;
    setBusy(true);
    setMessage(null);
    try {
      const seen = new Set(taken);
      const fresh: Slot[] = [];
      const lookup: string[] = [];
      for (const item of parsed) {
        if (!item.valid) {
          fresh.push({ value: item.value, kind: item.kind, status: "invalid" });
        } else if (seen.has(item.value)) {
          fresh.push({ value: item.value, kind: item.kind, status: "duplicate" });
        } else {
          seen.add(item.value);
          fresh.push({ value: item.value, kind: item.kind, status: "unknown" });
          lookup.push(item.value);
        }
      }
      const checks = lookup.length > 0 ? await checkSerials(product.id, lookup) : [];
      const byValue = new Map(checks.map((check) => [check.value.toUpperCase(), check]));
      const resolved = fresh.map((slot) => {
        if (slot.status !== "unknown") return slot;
        const check = byValue.get(slot.value.toUpperCase());
        return check ? { ...slot, value: check.value, status: check.status as SlotStatus } : slot;
      });
      setSlots((current) => {
        const next = [...current, ...resolved];
        if (next.length > wanted) setTarget(String(next.length));
        return next;
      });
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not check those identifiers.");
    } finally {
      setBusy(false);
    }
  };

  const autoAssign = async () => {
    if (remaining === 0) return;
    setBusy(true);
    setMessage(null);
    try {
      const rows = await availableSerials(product.id, remaining, [...taken]);
      setSlots((current) => [
        ...current,
        ...rows.map((row) => ({ value: row.value, kind: row.kind, status: "available" as const })),
      ]);
      if (rows.length < remaining) {
        setMessage(
          rows.length === 0
            ? `No free ${product.name} IMEIs are cached for this branch.`
            : `Only ${rows.length} more free IMEIs are cached for this branch.`,
        );
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not load free IMEIs.");
    } finally {
      setBusy(false);
    }
  };

  const cells = Math.max(wanted, slots.length);

  return (
    <div className="modal-backdrop" role="presentation">
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="modal-card max-w-3xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.16em] text-charcoal/50 dark:text-zinc-400">Bulk IMEI matrix</p>
            <h2 id={titleId} className="text-xl font-semibold">
              {product.name}
            </h2>
            <p className="mt-0.5 text-sm text-charcoal/60 dark:text-zinc-400 tabular-nums">
              {free === null ? "Checking free units…" : `${free} free at this branch`}
            </p>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} disabled={busy} className="modal-close">
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        <div className="mt-5 flex flex-wrap items-end gap-3">
          <label className="text-sm font-medium" htmlFor="bulk-target">
            Units
            <input
              id="bulk-target"
              inputMode="numeric"
              value={target}
              onChange={(event) => setTarget(event.target.value.replace(/\D/g, "").slice(0, 3))}
              className="modal-input mt-1.5 w-24 text-center font-semibold tabular-nums"
            />
          </label>
          <div className="inline-flex rounded-full border border-line dark:border-zinc-800 bg-surface dark:bg-zinc-800/60 p-1" role="tablist" aria-label="Add method">
            {tabs.map((item) => (
              <button
                key={item.value}
                type="button"
                role="tab"
                aria-selected={tab === item.value}
                onClick={() => setTab(item.value)}
                className={`inline-flex h-10 items-center gap-2 rounded-full px-4 text-sm font-semibold ${
                  tab === item.value ? "bg-primary text-white" : "text-charcoal/70 dark:text-zinc-300 hover:text-charcoal"
                }`}
              >
                <item.icon size={15} aria-hidden="true" />
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-4">
          {tab === "scan" ? (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                const value = scan;
                setScan("");
                void addValues(value);
              }}
            >
              <input
                ref={scanRef}
                data-scan="true"
                value={scan}
                onChange={(event) => setScan(event.target.value)}
                placeholder="Scan each IMEI. The scanner's Enter adds it to the next slot."
                className="modal-input tabular-nums"
              />
            </form>
          ) : null}
          {tab === "paste" ? (
            <div className="space-y-2">
              <textarea
                value={paste}
                rows={4}
                onChange={(event) => setPaste(event.target.value)}
                placeholder="Paste IMEIs separated by new lines, spaces, or commas"
                className="modal-input resize-none font-mono text-sm"
              />
              <div className="flex justify-end">
                <button
                  type="button"
                  disabled={busy || paste.trim() === ""}
                  onClick={() => {
                    const value = paste;
                    setPaste("");
                    void addValues(value);
                  }}
                  className="modal-save px-6"
                >
                  Add {parseIdentifiers(paste).length || ""} from list
                </button>
              </div>
            </div>
          ) : null}
          {tab === "auto" ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-surface dark:bg-zinc-800/60 px-4 py-3">
              <p className="text-sm text-charcoal/70 dark:text-zinc-300">
                Fills the empty slots with this branch's free IMEIs, oldest stock first.
              </p>
              <button type="button" disabled={busy || remaining === 0} onClick={() => void autoAssign()} className="modal-save px-6">
                {busy ? "Assigning…" : `Assign ${remaining} IMEIs`}
              </button>
            </div>
          ) : null}
        </div>

        {message ? <p className="mt-3 text-sm font-medium text-red-600 dark:text-red-400">{message}</p> : null}

        <ol className="mt-4 grid max-h-[38vh] grid-cols-2 gap-2 overflow-y-auto pr-1 sm:grid-cols-3 lg:grid-cols-4">
          {Array.from({ length: cells }, (_, index) => {
            const slot = slots[index];
            if (!slot) {
              return (
                <li
                  key={`empty-${index}`}
                  className="flex h-14 items-center gap-2 rounded-2xl border border-dashed border-line dark:border-zinc-800 px-3 text-xs text-charcoal/40 dark:text-zinc-500"
                >
                  <span className="tabular-nums">{index + 1}</span>
                  <span>Empty</span>
                </li>
              );
            }
            const bad = blocking.includes(slot.status);
            const warn = slot.status === "unknown";
            return (
              <li
                key={`${slot.value}-${index}`}
                title={statusText[slot.status]}
                className={`group relative flex h-14 flex-col justify-center rounded-2xl px-3 pr-8 ${
                  bad ? "bg-danger text-white" : warn ? "border border-warning bg-warning/10 dark:bg-zinc-900" : "bg-surface dark:bg-zinc-800/60"
                }`}
              >
                <span className={`text-[10px] font-semibold uppercase tracking-wide ${bad ? "text-white/80" : "text-charcoal/50 dark:text-zinc-400"}`}>
                  {index + 1} · {statusText[slot.status]}
                </span>
                <span className="truncate font-mono text-xs">{slot.value}</span>
                <button
                  type="button"
                  aria-label={`Remove ${slot.value}`}
                  onClick={() => setSlots((current) => current.filter((_, position) => position !== index))}
                  className={`absolute right-2 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-full ${
                    bad ? "hover:bg-white/20" : "text-charcoal/50 dark:text-zinc-400 hover:bg-charcoal/10 dark:hover:bg-white/10"
                  }`}
                >
                  <X size={12} aria-hidden="true" />
                </button>
              </li>
            );
          })}
        </ol>

        <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-charcoal/60 dark:text-zinc-400 tabular-nums">
            {usable.length} of {wanted} assigned
            {warnings ? ` · ${warnings} not in the branch list` : ""}
            {errors ? ` · ${errors} to fix` : ""}
          </p>
          <div className="flex gap-3">
            {errors ? (
              <button
                type="button"
                onClick={() => setSlots((current) => current.filter((slot) => !blocking.includes(slot.status)))}
                className="modal-cancel"
              >
                Clear errors
              </button>
            ) : null}
            <button type="button" onClick={onClose} disabled={busy} className="modal-cancel">
              Cancel
            </button>
            <button
              type="button"
              disabled={busy || usable.length === 0 || errors > 0}
              onClick={() => onConfirm(usable.map((slot) => ({ value: slot.value, kind: slot.kind })))}
              className="modal-save"
            >
              Add {usable.length || ""} to sale
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
