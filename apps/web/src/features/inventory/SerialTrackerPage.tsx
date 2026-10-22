import { movementLabel, type SerialSearchRow, type SerialTrace } from "@ai-pos/shared-types";
import { MapPin, ScanLine, Warehouse } from "lucide-react";
import { useState, type FormEvent } from "react";
import { ErrorNote, PrimaryButton } from "../../components/ui/Field";
import { inventoryApi, message } from "./api";
import { DocStatus, formatDate } from "./shared";

const SUFFIX_MAX = 6;

export function SerialTrackerPage() {
  const [value, setValue] = useState("");
  const [trace, setTrace] = useState<SerialTrace | null>(null);
  const [matches, setMatches] = useState<SerialSearchRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const traceValue = async (identifier: string) => {
    setBusy(true);
    setError(null);
    try {
      setTrace(await inventoryApi.trace(identifier));
      setMatches(null);
    } catch (caught) {
      setTrace(null);
      setError(message(caught, "Could not trace that identifier."));
    } finally {
      setBusy(false);
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = value.trim();
    if (trimmed.length < 3) return;
    if (trimmed.length > SUFFIX_MAX) return traceValue(trimmed);
    setBusy(true);
    setError(null);
    setTrace(null);
    try {
      const result = await inventoryApi.searchSerials({ query: trimmed });
      if (result.rows.length === 1 && !result.rows[0]!.value.startsWith("•")) return traceValue(result.rows[0]!.value);
      setMatches(result.rows);
      if (result.hint) setError(result.hint);
    } catch (caught) {
      setMatches(null);
      setError(message(caught, "Could not search serial numbers."));
    } finally {
      setBusy(false);
    }
  };

  const location = trace?.location;
  return (
    <section className="space-y-4">
      <form onSubmit={(event) => void submit(event)} className="rounded-card border border-line bg-white p-6">
        <h2 className="text-2xl font-semibold">IMEI / serial tracker</h2>
        <p className="text-sm text-charcoal/60">
          Scan the full IMEI or serial, or type its last 3 to 6 characters. Identifiers are encrypted at rest, so the
          middle digits cannot be searched.
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          <label className="relative min-w-[280px] flex-1">
            <span className="sr-only">IMEI or serial number</span>
            <ScanLine size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-charcoal/40" />
            <input
              autoFocus
              value={value}
              onChange={(event) => setValue(event.target.value)}
              placeholder="e.g. 490154203237518"
              className="h-12 w-full rounded-full border border-line bg-surface pl-11 pr-4 font-mono text-base tabular-nums"
            />
          </label>
          <PrimaryButton type="submit" disabled={busy || value.trim().length < 3}>
            {busy ? "Searching…" : value.trim().length > SUFFIX_MAX ? "Trace" : "Search"}
          </PrimaryButton>
        </div>
        <ErrorNote message={error} />
      </form>

      {matches !== null ? (
        <div className="rounded-card border border-line bg-white p-6">
          <h3 className="text-lg font-semibold">
            {matches.length} unit{matches.length === 1 ? "" : "s"} ending in {value.trim().toUpperCase()}
          </h3>
          {matches.length === 0 ? <p className="mt-2 text-sm text-charcoal/60">No unit ends with those characters.</p> : null}
          <ul className="mt-3 divide-y divide-line">
            {matches.map((row) => {
              const traceable = !row.value.startsWith("•");
              return (
                <li key={row.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <span className="min-w-0">
                    <span className="block font-mono text-sm tabular-nums">{row.value}</span>
                    <span className="block text-xs text-charcoal/60">
                      {row.product_name} · {row.store_code}
                      {row.batch_number ? ` · ${row.batch_number}` : ""}
                    </span>
                  </span>
                  <span className="flex items-center gap-2">
                    <span className="rounded-full bg-surface px-2.5 py-0.5 text-xs font-semibold capitalize">{row.status.replace(/_/g, " ")}</span>
                    {traceable ? (
                      <button
                        type="button"
                        onClick={() => void traceValue(row.value)}
                        className="rounded-full border border-line px-3 py-1 text-xs font-semibold hover:border-accent hover:text-accent"
                      >
                        Trace
                      </button>
                    ) : null}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}

      {trace && location ? (
        <div className="grid gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
          <article className="rounded-card bg-charcoal p-6 text-white">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-white/50">{trace.product.sku}</p>
            <h3 className="mt-1 text-2xl font-semibold">{trace.product.name}</h3>
            <p className="mt-1 font-mono text-sm text-white/60">
              {location.kind.toUpperCase()} •••• {location.last4}
            </p>
            <div className="mt-6 rounded-2xl bg-white/10 p-4">
              <p className="flex items-center gap-2 text-sm text-white/70">
                {location.is_warehouse ? <Warehouse size={16} /> : <MapPin size={16} />} Current location
              </p>
              <p className="mt-1 text-xl font-semibold">
                {location.store_code} · {location.store_name}
              </p>
              <p className="mt-1 text-sm text-white/70">Shelf {location.aisle_shelf_location ?? "not set"}</p>
            </div>
            <span className="mt-4 inline-flex rounded-full bg-accent px-3 py-1 text-xs font-semibold capitalize">
              {location.status.replace(/_/g, " ")}
            </span>
          </article>

          <div className="rounded-card border border-line bg-white p-6">
            <h3 className="text-lg font-semibold">Movement history</h3>
            {trace.history.length === 0 ? (
              <p className="mt-2 text-sm text-charcoal/60">No branch movements recorded for this unit.</p>
            ) : null}
            <ol className="mt-3 space-y-3">
              {trace.history.map((movement) => (
                <li key={movement.id} className="flex items-start gap-3">
                  <span
                    className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${movement.quantity > 0 ? "bg-charcoal" : "bg-accent"}`}
                  />
                  <span className="text-sm">
                    <span className="font-medium">{movementLabel(movement.movement_type)}</span>
                    <span className="text-charcoal/60">
                      {" "}
                      · {movement.store_code} · {movement.quantity > 0 ? "in" : "out"} · {formatDate(movement.created_at)}
                      {movement.user_name ? ` · ${movement.user_name}` : ""}
                    </span>
                  </span>
                </li>
              ))}
            </ol>
            {trace.transfers.length > 0 ? (
              <>
                <h3 className="mt-6 text-lg font-semibold">Branch transfers</h3>
                <ul className="mt-2 space-y-2 text-sm">
                  {trace.transfers.map((transfer) => (
                    <li key={transfer.id} className="flex flex-wrap items-center justify-between gap-2 rounded-2xl bg-surface px-4 py-3">
                      <span>
                        <span className="font-mono text-xs">{transfer.number}</span>
                        <span className="ml-2 font-medium">
                          {transfer.source_store_code} → {transfer.destination_store_code}
                        </span>
                      </span>
                      <span className="flex items-center gap-2">
                        <span className="text-xs text-charcoal/60">{formatDate(transfer.received_at ?? transfer.shipped_at)}</span>
                        <DocStatus status={transfer.status} />
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
