import type { ConsoleChangeRequest } from "@ai-pos/shared-types";
import { Inbox } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorNote, StatusBadge } from "../components/ui";
import { api, errorText } from "../lib/api";
import { when } from "../lib/format";

const FILTERS = ["PENDING", "RESOLVED", "REJECTED", ""] as const;

/** Every store's change requests; open one to migrate, resolve or reject it from the tenant's page. */
export function RequestsPage() {
  const [status, setStatus] = useState<(typeof FILTERS)[number]>("PENDING");
  const [rows, setRows] = useState<ConsoleChangeRequest[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setRows(await api.get<ConsoleChangeRequest[]>(`/change-requests${status ? `?status=${status}` : ""}`));
      setError(null);
    } catch (caught) {
      setError(errorText(caught, "Could not load the requests."));
    }
  }, [status]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-charcoal text-white">
            <Inbox size={20} aria-hidden="true" />
          </span>
          <div>
            <h1 className="text-2xl font-semibold">Change requests</h1>
            <p className="text-sm text-charcoal/60">Business-type migrations and modules stores asked for.</p>
          </div>
        </div>
        <div className="inline-flex rounded-full bg-white p-1 shadow-sm" role="group" aria-label="Filter">
          {FILTERS.map((value) => (
            <button
              key={value || "all"}
              type="button"
              aria-pressed={status === value}
              onClick={() => setStatus(value)}
              className={`h-9 rounded-full px-4 text-sm font-semibold capitalize ${status === value ? "bg-charcoal text-white" : "text-charcoal/60"}`}
            >
              {value ? value.toLowerCase() : "all"}
            </button>
          ))}
        </div>
      </div>
      <ErrorNote message={error} />
      <ul className="space-y-2">
        {rows.map((request) => (
          <li key={request.id}>
            <Link to={`/tenants/${request.tenant_id}`} className="block rounded-3xl border border-line bg-white p-5 transition hover:border-accent">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge value={request.status} />
                <span className="font-semibold">{request.tenant_name}</span>
                <span className="font-mono text-xs text-charcoal/50">{request.tenant_slug}</span>
                <span className="ml-auto text-xs text-charcoal/50">{when(request.created_at)}</span>
              </div>
              <p className="mt-2 text-sm">
                <span className="font-medium">{request.kind === "BUSINESS_TYPE" ? "Business type" : "Module"}:</span> {request.current_value} → {request.requested_value}
              </p>
              <p className="mt-1 text-sm text-charcoal/70">{request.reason}</p>
            </Link>
          </li>
        ))}
        {rows.length === 0 ? <li className="rounded-3xl bg-white p-8 text-center text-sm text-charcoal/60">Nothing here.</li> : null}
      </ul>
    </section>
  );
}
