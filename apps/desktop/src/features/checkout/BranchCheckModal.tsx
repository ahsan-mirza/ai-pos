import type { Availability, ProductUpsert } from "@ai-pos/shared-types";
import { MapPin, Phone, Search, Warehouse, X } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Select } from "../../components/Select";
import { branchAvailability } from "../../lib/api";
import { checkBranchesViaShell, inTauri } from "../../lib/tauri";
import { store } from "./catalog";

function lookup(params: { productId?: string; serial?: string }): Promise<Availability> {
  return inTauri() ? checkBranchesViaShell(params) : branchAvailability(params);
}

/** Read-only cross-branch lookup so a cashier can send a customer to the branch or warehouse that has stock. */
export function BranchCheckModal({
  product,
  products,
  onClose,
}: {
  product: ProductUpsert | null;
  products: ProductUpsert[];
  onClose: () => void;
}) {
  const [productId, setProductId] = useState(product?.id ?? "");
  const [serial, setSerial] = useState("");
  const [result, setResult] = useState<Availability | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = useCallback(async (params: { productId?: string; serial?: string }) => {
    setBusy(true);
    setError(null);
    try {
      setResult(await lookup(params));
    } catch (caught) {
      setResult(null);
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    if (product) void run({ productId: product.id });
  }, [product, run]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const submitSerial = (event: FormEvent) => {
    event.preventDefault();
    if (serial.trim().length >= 4) void run({ serial: serial.trim() });
  };

  const elsewhere = result?.branches.filter((branch) => branch.store_id !== store.id) ?? [];
  const here = result?.branches.find((branch) => branch.store_id === store.id);

  return (
    <div className="modal-backdrop" role="presentation">
      <div role="dialog" aria-modal="true" aria-label="Check other branches" className="modal-card max-w-2xl">
        <div className="mb-5 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Check other branches</h2>
            <p className="mt-0.5 text-sm text-charcoal/60 dark:text-zinc-400">Live stock at every branch and the central warehouse.</p>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} className="modal-close">
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div className="block text-sm font-medium">
            <label id="branch-check-product-label" htmlFor="branch-check-product">
              Product
            </label>
            <Select
              id="branch-check-product"
              labelledBy="branch-check-product-label"
              className="mt-1.5"
              value={productId}
              placeholder="Choose a product"
              options={products.map((item) => ({ value: item.id, label: item.name, hint: item.sku }))}
              onChange={(next) => {
                setProductId(next);
                void run({ productId: next });
              }}
            />
          </div>
          <form onSubmit={submitSerial} className="block text-sm font-medium">
            Or a specific IMEI / serial
            <span className="mt-1.5 flex gap-2">
              <input
                value={serial}
                onChange={(event) => setSerial(event.target.value)}
                placeholder="Scan IMEI"
                className="modal-input min-w-0 flex-1 font-mono text-sm font-normal"
              />
              <button
                type="submit"
                aria-label="Look up IMEI"
                className="flex w-11 shrink-0 items-center justify-center rounded-xl bg-primary text-white transition-colors hover:bg-primary-600"
              >
                <Search size={16} aria-hidden="true" />
              </button>
            </span>
          </form>
        </div>

        {busy ? <p className="mt-4 text-sm text-charcoal/60 dark:text-zinc-400">Checking branches…</p> : null}
        {error ? (
          <p role="alert" className="mt-4 rounded-2xl bg-red-500/10 px-4 py-3 text-sm text-red-700 dark:text-red-300">
            {error}
          </p>
        ) : null}

        {result ? (
          <div className="mt-5 space-y-3">
            <p className="text-sm">
              <span className="font-semibold">{result.product.name}</span>
              <span className="text-charcoal/60 dark:text-zinc-400"> · {result.product.sku}</span>
            </p>
            {result.serial ? (
              <div className="rounded-2xl bg-charcoal p-4 text-white">
                <p className="text-xs uppercase tracking-[0.16em] text-white/50">
                  {result.serial.kind} •••• {result.serial.last4}
                </p>
                <p className="mt-1 text-lg font-semibold">
                  {result.serial.status === "in_stock" ? "In stock at " : `${result.serial.status.replace(/_/g, " ")} · `}
                  {result.serial.store_code} · {result.serial.store_name}
                </p>
                <p className="text-sm text-white/70">Shelf {result.serial.aisle_shelf_location ?? "not set"}</p>
              </div>
            ) : null}
            <p className="text-sm text-charcoal/60 dark:text-zinc-400">
              This branch ({store.code}): <span className="font-semibold tabular-nums">{here?.quantity_available ?? 0}</span>{" "}
              available
            </p>
            <ul className="grid gap-2 sm:grid-cols-2">
              {elsewhere.map((branch) => (
                <li
                  key={branch.store_id}
                  className={`rounded-2xl border p-4 ${branch.quantity_available > 0 ? "border-primary" : "border-line dark:border-zinc-800 opacity-70"}`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span>
                      <span className="flex items-center gap-1 font-semibold">
                        {branch.is_warehouse ? <Warehouse size={14} aria-hidden="true" /> : null}
                        {branch.store_code}
                      </span>
                      <span className="block text-xs text-charcoal/60 dark:text-zinc-400">{branch.store_name}</span>
                    </span>
                    <span className="text-right">
                      <span className="block text-2xl font-semibold tabular-nums">{branch.quantity_available}</span>
                      <span className="block text-[11px] text-charcoal/50 dark:text-zinc-400">available</span>
                    </span>
                  </div>
                  <p className="mt-2 flex items-center gap-1 text-xs text-charcoal/60 dark:text-zinc-400">
                    <MapPin size={12} aria-hidden="true" /> {branch.address ?? "No address"}
                  </p>
                  <p className="flex items-center gap-1 text-xs text-charcoal/60 dark:text-zinc-400">
                    <Phone size={12} aria-hidden="true" /> {branch.phone ?? "No phone"}
                  </p>
                </li>
              ))}
            </ul>
            {elsewhere.length === 0 ? <p className="text-sm text-charcoal/60 dark:text-zinc-400">No other branch stocks this product.</p> : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
