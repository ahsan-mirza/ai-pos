import type { EInvoice, EInvoiceList, EInvoiceStatus, EInvoiceSummary } from "@ai-pos/shared-types";
import { Download, FileCheck2 } from "lucide-react";
import { useEffect, useState } from "react";
import { ErrorNote } from "../../components/ui/Field";
import { apiBlob, apiGet } from "../../lib/api";
import { errorMessage } from "../users/api";

const STATUS_STYLES: Record<EInvoiceStatus, string> = {
  PENDING: "bg-surface text-charcoal/70",
  REPORTED: "bg-emerald-50 text-emerald-700",
  CLEARED: "bg-emerald-50 text-emerald-700",
  REJECTED: "bg-red-50 text-red-700",
};

async function downloadXml(row: EInvoice): Promise<void> {
  const blob = await apiBlob(`/api/v1/einvoices/${row.id}/xml`);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${row.number}.xml`;
  link.click();
  URL.revokeObjectURL(url);
}

/** The signed e-invoice chain for authorities that clear or report every invoice (ZATCA). */
export function EInvoicingPanel({ refreshKey }: { refreshKey: string }) {
  const [summary, setSummary] = useState<EInvoiceSummary | null>(null);
  const [rows, setRows] = useState<EInvoice[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([apiGet<EInvoiceSummary>("/api/v1/einvoices/summary"), apiGet<EInvoiceList>("/api/v1/einvoices?limit=8")])
      .then(([nextSummary, list]) => {
        if (cancelled) return;
        setSummary(nextSummary);
        setRows(list.items);
      })
      .catch((caught: unknown) => !cancelled && setError(errorMessage(caught, "Could not load e-invoices.")));
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  if (summary === null) return error ? <ErrorNote message={error} /> : null;
  if (!summary.issues_einvoices) return null;

  return (
    <section className="mt-6 rounded-2xl border border-line p-5" aria-labelledby="einvoicing-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <FileCheck2 size={18} className="text-accent" aria-hidden="true" />
          <div>
            <h3 id="einvoicing-title" className="text-base font-semibold">
              E-invoicing · {summary.authority_name}
            </h3>
            <p className="text-xs text-charcoal/60">
              Every invoice and credit note is signed, hash-chained and given a QR code when it syncs.
            </p>
          </div>
        </div>
        {summary.environment === "simulation" || summary.environment === null ? (
          <span className="rounded-full bg-amber-100 px-3 py-1 text-[11px] font-semibold text-amber-800">
            Simulation: not sent to ZATCA until onboarding is complete
          </span>
        ) : null}
      </div>

      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-4">
        {(["REPORTED", "CLEARED", "REJECTED", "PENDING"] as const).map((status) => (
          <div key={status} className="rounded-xl bg-surface px-3 py-2">
            <dt className="text-[11px] font-semibold uppercase tracking-wider text-charcoal/50">{status.toLowerCase()}</dt>
            <dd className="text-xl font-semibold tabular-nums">{summary.counts[status]}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 text-xs text-charcoal/60">
        Chain at invoice #{summary.last_counter}
        {summary.last_hash ? (
          <>
            {" · last hash "}
            <code className="rounded bg-surface px-1">{summary.last_hash.slice(0, 16)}…</code>
          </>
        ) : null}
        {summary.certificate_subject ? ` · signing certificate ${summary.certificate_subject}` : ""}
      </p>

      {rows.length > 0 ? (
        <table className="mt-4 w-full text-left text-sm">
          <thead className="text-[11px] uppercase tracking-wider text-charcoal/50">
            <tr>
              <th className="py-2 font-semibold">#</th>
              <th className="py-2 font-semibold">Document</th>
              <th className="py-2 font-semibold">Type</th>
              <th className="py-2 font-semibold">Status</th>
              <th className="py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((row) => (
              <tr key={row.id}>
                <td className="py-2 tabular-nums text-charcoal/60">{row.counter}</td>
                <td className="py-2">
                  <span className="font-medium">{row.number}</span>
                  {row.errors.length > 0 ? <span className="block text-xs text-red-700">{row.errors.join(" ")}</span> : null}
                </td>
                <td className="py-2 text-charcoal/70">
                  {row.source_type === "return" ? "Credit note" : row.kind === "STANDARD" ? "Tax invoice" : "Simplified"}
                </td>
                <td className="py-2">
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${STATUS_STYLES[row.status]}`}>
                    {row.status.toLowerCase()}
                  </span>
                </td>
                <td className="py-2 text-right">
                  <button
                    type="button"
                    onClick={() => void downloadXml(row).catch((caught: unknown) => setError(errorMessage(caught, "Download failed.")))}
                    className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-charcoal/70 hover:bg-surface"
                  >
                    <Download size={14} aria-hidden="true" /> XML
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="mt-4 text-sm text-charcoal/60">No e-invoices yet. They appear here as registers sync sales.</p>
      )}
      <ErrorNote message={error} />
    </section>
  );
}
