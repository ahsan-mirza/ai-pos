import { Permission, isValidImei, type ProductUpsert } from "@ai-pos/shared-types";
import { ScanLine, ShieldCheck, X } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { ManagerApprovalModal } from "../../components/ManagerApprovalModal";
import type { RegisterSerial } from "../../lib/tauri";
import type { CashierSession } from "../auth/session";
import { availableSerials, checkSerials, verifyManager } from "./wholesaleClient";

type Kind = "imei" | "serial";

const LOAD_LIMIT = 500;

function parseIdentifier(raw: string): { value: string; kind: Kind } | string {
  const cleaned = raw.trim();
  if (/^\d{15}$/.test(cleaned)) return isValidImei(cleaned) ? { value: cleaned, kind: "imei" } : "That IMEI failed the Luhn check.";
  if (/^[A-Za-z0-9-]{4,64}$/.test(cleaned)) return { value: cleaned.toUpperCase(), kind: "serial" };
  return "Enter a 15-digit IMEI or a serial of 4 to 64 letters, numbers, or hyphens.";
}

interface SerialPickerModalProps {
  session: CashierSession;
  product: ProductUpsert;
  /** Identifiers already on this sale, hidden from the list. */
  inCart: string[];
  onClose: () => void;
  onConfirm: (value: string, kind: Kind) => void;
}

/** Pick the unit being sold from this branch's free stock, filter by typing, or scan it. */
export function SerialPickerModal({ session, product, inCart, onClose, onConfirm }: SerialPickerModalProps) {
  const titleId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [units, setUnits] = useState<RegisterSerial[] | null>(null);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<RegisterSerial | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [override, setOverride] = useState<{ value: string; kind: Kind } | null>(null);
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);

  const cartKey = inCart.join("|");
  useEffect(() => {
    let cancelled = false;
    availableSerials(product.id, LOAD_LIMIT, cartKey ? cartKey.split("|") : [])
      .then((rows) => {
        if (!cancelled) setUnits(rows);
      })
      .catch(() => {
        if (!cancelled) setUnits([]);
      });
    return () => {
      cancelled = true;
    };
  }, [product.id, cartKey]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !asking) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, asking]);

  const needle = query.trim().toUpperCase();
  const filtered = useMemo(
    () => (units ?? []).filter((unit) => needle === "" || unit.value.toUpperCase().includes(needle)),
    [units, needle],
  );
  const type = (next: string) => {
    setQuery(next);
    setSelected(null);
    setError(null);
    setOverride(null);
    // A scan (or a fully typed identifier) that is exactly one free unit goes straight onto the sale.
    const exact = (units ?? []).find((unit) => unit.value.toUpperCase() === next.trim().toUpperCase());
    if (exact) onConfirm(exact.value, exact.kind as Kind);
  };

  const pick = (unit: RegisterSerial) => {
    setSelected(unit);
    setQuery(unit.value);
    setError(null);
    inputRef.current?.focus();
  };

  const submit = async () => {
    if (override !== null) return setAsking(true);
    if (selected !== null && selected.value.toUpperCase() === needle) return onConfirm(selected.value, selected.kind as Kind);
    if (filtered.length === 1 && needle.length >= 3) return onConfirm(filtered[0]!.value, filtered[0]!.kind as Kind);
    const parsed = parseIdentifier(query);
    if (typeof parsed === "string") return setError(filtered.length > 1 ? "Several units match; pick one below." : parsed);
    setBusy(true);
    try {
      const [check] = await checkSerials(product.id, [parsed.value]);
      if (check?.status === "available") return onConfirm(check.value, (check.kind ?? parsed.kind) as Kind);
      if (check?.status === "taken") return setError(`${parsed.value} is already on a sale waiting to sync.`);
      if (check?.status === "other_product") return setError(`${parsed.value} belongs to a different product.`);
      setError(`${parsed.value} is not in this branch's stock list.`);
      setOverride(parsed);
    } catch {
      setError("Could not check the identifier against stock.");
    } finally {
      setBusy(false);
    }
  };

  const loading = units === null;
  return (
    <>
      <div className="modal-backdrop" role="presentation">
        <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="modal-card max-w-xl">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h2 id={titleId} className="text-xl font-semibold">
                Select IMEI / serial
              </h2>
              <p className="mt-0.5 truncate text-sm text-charcoal/60 dark:text-zinc-400">{product.name}</p>
            </div>
            <button type="button" aria-label="Close" onClick={onClose} className="modal-close">
              <X size={18} aria-hidden="true" />
            </button>
          </div>

          <form
            className="mt-5"
            onSubmit={(event) => {
              event.preventDefault();
              void submit();
            }}
          >
            <div className="relative">
              <ScanLine size={16} aria-hidden="true" className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-charcoal/40 dark:text-zinc-500" />
              <input
                ref={inputRef}
                autoFocus
                data-scan="true"
                aria-label="IMEI or serial"
                value={query}
                onChange={(event) => type(event.target.value)}
                placeholder="Scan, or type any part of the IMEI"
                className="modal-input pl-11 pr-11 font-mono tabular-nums"
              />
              {query ? (
                <button
                  type="button"
                  aria-label="Clear"
                  onClick={() => {
                    type("");
                    inputRef.current?.focus();
                  }}
                  className="absolute right-3 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full text-charcoal/50 hover:bg-charcoal/5 dark:text-zinc-400 dark:hover:bg-white/10"
                >
                  <X size={14} aria-hidden="true" />
                </button>
              ) : null}
            </div>

            <div className="mt-4 flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-charcoal/50 dark:text-zinc-500">
                In stock here {units ? `(${needle ? `${filtered.length} of ` : ""}${units.length})` : ""}
              </span>
              {loading ? <span className="animate-pulse text-xs text-primary">Loading…</span> : null}
            </div>
            <div className="mt-2 max-h-52 overflow-y-auto pr-1">
              {!loading && filtered.length === 0 ? (
                <p className="rounded-2xl bg-surface px-4 py-3 text-sm text-charcoal/60 dark:bg-zinc-800/60 dark:text-zinc-400">
                  {units?.length
                    ? `No in-stock unit matches "${query.trim()}". Scan the full IMEI to check it.`
                    : "No free units of this product are cached on this register. Scan the box to check it."}
                </p>
              ) : (
                <div className="flex flex-wrap gap-2" role="listbox" aria-label="Available units">
                  {filtered.map((unit) => {
                    const active = selected?.id === unit.id;
                    return (
                      <button
                        key={unit.id}
                        type="button"
                        role="option"
                        aria-selected={active}
                        onClick={() => pick(unit)}
                        onDoubleClick={() => onConfirm(unit.value, unit.kind as Kind)}
                        className={`rounded-xl border px-3.5 py-2 font-mono text-xs font-medium tabular-nums transition-colors ${
                          active
                            ? "border-primary bg-primary font-bold text-white shadow-lg shadow-primary/20"
                            : "border-zinc-200 bg-white text-charcoal hover:border-primary/60 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100 dark:hover:border-primary/60"
                        }`}
                      >
                        {unit.value}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            {error ? (
              <p role="alert" className="mt-3 text-sm font-medium text-red-600 dark:text-red-400">
                {error}
              </p>
            ) : null}
            <div className="mt-5 flex flex-wrap items-center justify-end gap-3">
              {override !== null ? (
                <span className="mr-auto inline-flex items-center gap-1.5 text-sm font-semibold text-primary">
                  <ShieldCheck size={15} aria-hidden="true" /> Needs a manager
                </span>
              ) : (
                <span className="mr-auto text-xs text-charcoal/50 dark:text-zinc-500">Double-click a unit to add it at once</span>
              )}
              <button type="button" onClick={onClose} className="modal-cancel">
                Cancel
              </button>
              <button type="submit" disabled={busy || (override === null && !query.trim())} className="modal-save">
                {busy ? "Checking…" : override !== null ? "Manager override" : "Add to sale"}
              </button>
            </div>
          </form>
        </div>
      </div>
      {asking && override !== null ? (
        <ManagerApprovalModal
          reasons={[`Sell ${product.name} with ${override.value}, which is not in this branch's stock list`]}
          subtitle="A manager who can adjust stock must enter their PIN; the unit is checked again when the sale syncs."
          verify={(username, pin) => verifyManager(session, username, pin, Permission.InventoryAdjustStock)}
          approveLabel="Approve and add"
          onClose={() => setAsking(false)}
          onApproved={() => onConfirm(override.value, override.kind)}
        />
      ) : null}
    </>
  );
}
