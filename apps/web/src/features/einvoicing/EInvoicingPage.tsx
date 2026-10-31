import { useCallback, useEffect, useState } from "react";
import { ErrorNote, GhostButton } from "../../components/ui/Field";
import { apiGet, apiPost } from "../../lib/api";
import { errorMessage } from "../users/api";

interface Dashboard {
  eligible: number;
  queued: number;
  accepted: number;
  rejected: number;
  validation_failed: number;
  credit_notes: number;
  provider_connected: boolean;
  provider_code: string;
  mock_only: boolean;
}

interface InvoiceRow {
  id: string;
  document_number: string;
  document_kind: string;
  issue_date: string;
  status: string;
  provider_status: string;
  provider_reference: string;
  error_detail: string;
}

const cards: { key: keyof Dashboard; label: string }[] = [
  { key: "eligible", label: "Eligible" },
  { key: "queued", label: "Pending" },
  { key: "accepted", label: "Accepted" },
  { key: "rejected", label: "Rejected" },
  { key: "validation_failed", label: "Needs data" },
  { key: "credit_notes", label: "Credit notes" },
];

export function EInvoicingPage() {
  const [board, setBoard] = useState<Dashboard | null>(null);
  const [rows, setRows] = useState<InvoiceRow[]>([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [summary, invoices] = await Promise.all([
        apiGet<Dashboard>("/api/v1/einvoicing/dashboard"),
        apiGet<InvoiceRow[]>(`/api/v1/einvoicing/invoices${status ? `?status=${encodeURIComponent(status)}` : ""}`),
      ]);
      setBoard(summary);
      setRows(invoices);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load e-Invoicing."));
    }
  }, [status]);

  useEffect(() => {
    void load();
  }, [load]);

  async function testConnection() {
    setNotice(null);
    setError(null);
    try {
      const result = await apiPost<{ ok: boolean; provider_status: string; detail: string }>("/api/v1/einvoicing/providers/test", {
        provider_code: "mock",
      });
      setNotice(`${result.provider_status}: ${result.detail}`);
      await load();
    } catch (caught) {
      setError(errorMessage(caught, "Connection test failed."));
    }
  }

  async function retry(id: string) {
    setError(null);
    try {
      await apiPost(`/api/v1/einvoicing/invoices/${id}/retry`, {});
      await load();
    } catch (caught) {
      setError(errorMessage(caught, "Retry was not accepted."));
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-4">
      <div>
        <h1 className="text-xl font-semibold">UAE e-Invoicing</h1>
        <p className="mt-1 text-sm text-charcoal/60">
          In-scope business and government sales are queued here. Consumer receipts stay on the register. The mock provider is for tests and is not an accredited ASP.
        </p>
      </div>
      <ErrorNote message={error} />
      {notice ? <p className="text-sm text-charcoal/80">{notice}</p> : null}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {cards.map((card) => (
          <article key={card.key} className="rounded-card border border-line bg-white p-3 dark:bg-white/5">
            <p className="text-xs text-charcoal/60">{card.label}</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">{board ? String(board[card.key]) : "—"}</p>
          </article>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-sm">
          Status
          <select className="ml-2 rounded-lg border border-line bg-white px-2 py-1" value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">All</option>
            <option value="QUEUED">Queued</option>
            <option value="ACCEPTED">Accepted</option>
            <option value="REJECTED">Rejected</option>
            <option value="VALIDATION_FAILED">Needs data</option>
          </select>
        </label>
        <GhostButton onClick={() => void testConnection()}>Test mock connection</GhostButton>
      </div>
      <div className="overflow-x-auto rounded-card border border-line">
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase text-charcoal/50">
            <tr>
              <th className="px-3 py-2">Number</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Provider</th>
              <th className="px-3 py-2">Detail</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td className="px-3 py-4 text-charcoal/60" colSpan={6}>
                  No e-invoices in this register yet.
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.id} className="border-t border-line">
                  <td className="px-3 py-2 font-medium">{row.document_number || row.id.slice(0, 8)}</td>
                  <td className="px-3 py-2">{row.document_kind}</td>
                  <td className="px-3 py-2">{row.status}</td>
                  <td className="px-3 py-2">{row.provider_status || "—"}</td>
                  <td className="px-3 py-2 text-charcoal/70">{row.error_detail || row.provider_reference}</td>
                  <td className="px-3 py-2 text-right">
                    {row.status === "REJECTED" || row.status === "RETRY_PENDING" || row.status === "PROCESSING_ERROR" ? (
                      <button type="button" className="text-sm font-semibold text-accent" onClick={() => void retry(row.id)}>
                        Retry
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
