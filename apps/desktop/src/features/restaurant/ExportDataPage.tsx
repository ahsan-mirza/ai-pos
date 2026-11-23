import { useState } from "react";
import { RetailRequestError, retailCall } from "../../lib/retailClient";

function saveJson(name: string, value: unknown) {
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

/** Branch scope is the signed-in user's store. A user with no store receives the tenant list the API already allows. */
export function ExportDataPage({ storeId, canCustomers }: { storeId: string | null; canCustomers: boolean }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const scope = storeId ? `branch ${storeId}` : "every branch this sign-in may see";

  async function run(kind: "sales" | "customers") {
    setBusy(kind);
    setNotice(null);
    try {
      const path = kind === "sales" ? "/api/v1/sales?limit=200" : "/api/v1/customers?limit=200";
      const rows = await retailCall<unknown[]>("GET", path);
      const stamp = new Date().toISOString().slice(0, 19);
      saveJson(`${kind}-${stamp}.json`, {
        export_version: 1,
        generated_at: new Date().toISOString(),
        scope,
        module: kind,
        format: "json",
        record_count: rows.length,
        records: rows,
      });
      setNotice(`${rows.length} ${kind} records downloaded. The file is the latest authorized list, not a database backup.`);
    } catch (caught) {
      const offline = caught instanceof RetailRequestError && caught.offline;
      setNotice(offline ? "Export needs a connection." : caught instanceof Error ? caught.message : "The export was refused.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4 p-4">
      <header>
        <h1 className="text-xl font-semibold">Export Data</h1>
        <p className="text-sm text-zinc-500">Scope for this sign-in: {scope}. Cashiers without report access do not see this page. The file contains no passwords, tokens, or database credentials.</p>
      </header>
      <section className="rounded-2xl border border-zinc-200 p-4">
        <h2 className="font-semibold">Sales and bills</h2>
        <p className="mt-1 text-sm text-zinc-600">Latest completed bills returned by the sales API, with saved totals.</p>
        <button type="button" disabled={busy !== null} className="mt-3 h-10 rounded-full bg-zinc-900 px-4 text-sm font-semibold text-white disabled:opacity-50" onClick={() => void run("sales")}>
          {busy === "sales" ? "Preparing…" : "Download JSON"}
        </button>
      </section>
      {canCustomers ? <section className="rounded-2xl border border-zinc-200 p-4">
        <h2 className="font-semibold">Customers</h2>
        <p className="mt-1 text-sm text-zinc-600">Customer names and balances for accounts this sign-in may manage. Requires customer management on the server.</p>
        <button type="button" disabled={busy !== null} className="mt-3 h-10 rounded-full border border-zinc-300 px-4 text-sm font-semibold disabled:opacity-50" onClick={() => void run("customers")}>
          {busy === "customers" ? "Preparing…" : "Download JSON"}
        </button>
      </section> : <p className="text-sm text-zinc-600">Customer export stays hidden until this sign-in can manage customers.</p>}
      {notice ? <p className="text-sm">{notice}</p> : null}
      <p className="text-xs text-zinc-500">A full tenant backup, spreadsheet package, and raw database copy are not available from the register.</p>
    </div>
  );
}
