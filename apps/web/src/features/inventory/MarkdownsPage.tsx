import { Permission, formatMoney } from "@ai-pos/shared-types";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, PrimaryButton, TextField } from "../../components/ui/Field";
import { apiBlob, apiGet, apiPost } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCurrency } from "../../lib/currency";
import { message } from "../customers/api";

interface MarkdownEvent {
  id: string;
  name: string;
  percent_bps: number | null;
  price_cents: number | null;
  starts_at: string;
  ends_at: string;
  final_sale: boolean;
  status: string;
  applied_count: number;
  skipped_count: number;
}

interface Preview {
  products: number;
  units: number;
  retail_cents: number;
  marked_cents: number;
  skipped: { sku: string; reason: string }[];
}

function iso(day: string, end: boolean): string {
  return new Date(`${day}T${end ? "23:59" : "00:00"}:00`).toISOString();
}

/** Schedule a percent-off markdown for a season and reprint the tags it changed. */
export function MarkdownsPage() {
  const { user } = useAuth();
  const { currency } = useCurrency();
  const canManage = Boolean(user?.permissions.includes(Permission.PortalInventoryManage));
  const [events, setEvents] = useState<MarkdownEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [season, setSeason] = useState("");
  const [percent, setPercent] = useState("30");
  const [from, setFrom] = useState(() => new Date().toISOString().slice(0, 10));
  const [to, setTo] = useState(() => new Date(Date.now() + 14 * 86_400_000).toISOString().slice(0, 10));
  const [finalSale, setFinalSale] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    apiGet<MarkdownEvent[]>("/api/v1/markdowns")
      .then(setEvents)
      .catch((err: unknown) => setError(message(err, "Could not load markdowns.")));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function payload() {
    return {
      name: name.trim(),
      scope: { season: season.trim().toUpperCase() },
      percent_bps: Math.round(Number(percent) * 100),
      starts_at: iso(from, false),
      ends_at: iso(to, true),
      final_sale: finalSale,
    };
  }

  async function runPreview() {
    setBusy(true);
    setError(null);
    try {
      setPreview(await apiPost<Preview>("/api/v1/markdowns/preview", payload()));
    } catch (err) {
      setError(message(err, "Could not preview the markdown."));
    } finally {
      setBusy(false);
    }
  }

  async function create() {
    setBusy(true);
    setError(null);
    try {
      await apiPost("/api/v1/markdowns", payload());
      setPreview(null);
      setName("");
      load();
    } catch (err) {
      setError(message(err, "Could not schedule the markdown."));
    } finally {
      setBusy(false);
    }
  }

  async function end(id: string) {
    setError(null);
    try {
      await apiPost(`/api/v1/markdowns/${id}/end`, {});
      load();
    } catch (err) {
      setError(message(err, "Could not end the markdown."));
    }
  }

  async function reprint(id: string) {
    const blob = await apiBlob(`/api/v1/markdowns/${id}/labels.pdf`);
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank");
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold text-charcoal">Markdowns</h1>
        <p className="mt-1 text-sm text-charcoal/60">
          Mark a season down. Prices never go below the margin floor, and they return when the event ends.
        </p>
      </div>
      <ErrorNote message={error} />
      {canManage ? (
        <form
          className="grid gap-3 rounded-2xl border border-line bg-white p-4 sm:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            void create();
          }}
        >
          <TextField label="Name" value={name} onChange={(event) => setName(event.target.value)} required />
          <TextField label="Season" value={season} onChange={(event) => setSeason(event.target.value)} placeholder="SS26" required />
          <TextField label="Percent off" value={percent} onChange={(event) => setPercent(event.target.value)} inputMode="decimal" required />
          <TextField label="From" type="date" value={from} onChange={(event) => setFrom(event.target.value)} required />
          <TextField label="Until" type="date" value={to} onChange={(event) => setTo(event.target.value)} required />
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={finalSale} onChange={(event) => setFinalSale(event.target.checked)} />
            Final sale
          </label>
          <div className="flex flex-wrap gap-2 sm:col-span-2">
            <PrimaryButton type="button" disabled={busy} onClick={() => void runPreview()}>
              Preview
            </PrimaryButton>
            <PrimaryButton type="submit" disabled={busy || !name.trim()}>
              Schedule
            </PrimaryButton>
          </div>
          {preview ? (
            <p className="text-sm text-charcoal/70 sm:col-span-2">
              {preview.products} products, {preview.units} units, {formatMoney(preview.retail_cents, currency)} to{" "}
              {formatMoney(preview.marked_cents, currency)}
              {preview.skipped.length ? ` · ${preview.skipped.length} skipped` : ""}
            </p>
          ) : null}
        </form>
      ) : null}
      <ul className="divide-y divide-line rounded-2xl border border-line bg-white">
        {events.map((event) => (
          <li key={event.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
            <div>
              <p className="font-medium">{event.name}</p>
              <p className="text-sm text-charcoal/60">
                {event.status} · {event.percent_bps != null ? `${event.percent_bps / 100}% off` : formatMoney(event.price_cents ?? 0, currency)}
                {" · "}
                {event.applied_count} priced, {event.skipped_count} skipped
                {event.final_sale ? " · final sale" : ""}
              </p>
            </div>
            {canManage && (event.status === "ACTIVE" || event.status === "SCHEDULED") ? (
              <div className="flex gap-2">
                {event.status === "ACTIVE" ? (
                  <button type="button" className="text-sm font-semibold text-accent" onClick={() => void reprint(event.id)}>
                    Reprint tags
                  </button>
                ) : null}
                <button type="button" className="text-sm font-semibold" onClick={() => void end(event.id)}>
                  End
                </button>
              </div>
            ) : null}
          </li>
        ))}
        {events.length === 0 ? <li className="px-4 py-6 text-sm text-charcoal/50">No markdowns yet.</li> : null}
      </ul>
    </div>
  );
}
