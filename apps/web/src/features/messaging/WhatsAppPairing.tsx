import { useCallback, useEffect, useState } from "react";
import { TextField } from "../../components/ui/Field";
import { apiGet, apiPost } from "../../lib/api";
import { errorMessage } from "../users/api";

interface Connection {
  id: string;
  name: string;
  phone_number: string | null;
  status: string;
  last_error: string | null;
  qr_base64: string | null;
}

function sessionLabel(status: string): { label: string; className: string } {
  if (status === "open") return { label: "Connected", className: "bg-emerald-50 text-emerald-700" };
  if (status === "qr" || status === "qrcode") return { label: "Scan the QR", className: "bg-sky-50 text-sky-700" };
  if (status === "close" || status === "closed" || status === "disconnected") {
    return { label: "Disconnected", className: "bg-rose-50 text-rose-700" };
  }
  if (status === "error") return { label: "Connection error", className: "bg-rose-50 text-rose-700" };
  return { label: "Not connected", className: "bg-surface text-charcoal/60" };
}

export function WhatsAppPairing() {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setConnections(await apiGet<Connection[]>("/api/v1/reach/connections"));
  }, []);

  useEffect(() => {
    void load().catch((caught) => setError(errorMessage(caught, "WhatsApp sessions could not be loaded.")));
  }, [load]);

  const run = async (work: () => Promise<void>, fallback: string) => {
    setBusy(true);
    setError(null);
    try {
      await work();
      await load();
    } catch (caught) {
      setError(errorMessage(caught, fallback));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="grid gap-3 rounded-card border border-line bg-white p-4 shadow-sm">
      <div>
        <h2 className="text-lg font-semibold">WhatsApp number</h2>
        <p className="mt-1 max-w-2xl text-sm leading-6 text-charcoal/60">
          Create a connection, then scan the QR with the phone that should send messages. The number appears after the session connects.
        </p>
      </div>
      {error ? <p className="text-sm text-rose-700">{error}</p> : null}
      <form
        className="flex flex-col gap-3 sm:flex-row sm:items-end"
        onSubmit={(event) => {
          event.preventDefault();
          if (busy || name.trim().length < 1) return;
          const next = name.trim();
          void run(async () => {
            await apiPost("/api/v1/reach/connections", { name: next });
            setName("");
          }, "The WhatsApp connection was not created.");
        }}
      >
        <div className="min-w-0 flex-1">
          <TextField label="Connection name" value={name} onChange={(event) => setName(event.target.value)} />
        </div>
        <button
          type="submit"
          disabled={busy || name.trim().length < 1}
          className="inline-flex h-11 items-center justify-center rounded-full bg-accent px-4 text-sm font-medium text-white disabled:opacity-40"
        >
          Create connection
        </button>
      </form>
      {connections.length === 0 ? (
        <p className="text-sm text-charcoal/60">No WhatsApp session yet.</p>
      ) : (
        <ul className="grid gap-3">
          {connections.map((row) => {
            const badge = sessionLabel(row.status);
            return (
              <li key={row.id} className="grid gap-4 rounded-2xl border border-line p-4 lg:grid-cols-[minmax(0,1fr)_auto]">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-semibold">{row.name}</h3>
                    <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${badge.className}`}>{badge.label}</span>
                  </div>
                  <p className="mt-2 text-sm">
                    <span className="text-charcoal/50">WhatsApp number </span>
                    {row.phone_number || "Not available yet"}
                  </p>
                  {row.last_error ? <p className="mt-2 text-sm text-rose-700">{row.last_error}</p> : null}
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => {
                        setBusy(true);
                        setError(null);
                        void apiPost<Connection>(`/api/v1/reach/connections/${row.id}/connect`, {})
                          .then((next) => {
                            setConnections((current) => current.map((item) => (item.id === row.id ? next : item)));
                          })
                          .catch((caught) => setError(errorMessage(caught, "The QR could not be loaded.")))
                          .finally(() => setBusy(false));
                      }}
                      className="rounded-full bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
                    >
                      {row.qr_base64 ? "Refresh QR" : "Connect"}
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        void run(async () => {
                          await apiPost(`/api/v1/reach/connections/${row.id}/status`, {});
                        }, "The session status could not be refreshed.")
                      }
                      className="rounded-full border border-line px-4 py-2 text-sm font-medium disabled:opacity-40"
                    >
                      Refresh status
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        void run(async () => {
                          await apiPost(`/api/v1/reach/connections/${row.id}/disconnect`, {});
                        }, "The session could not be disconnected.")
                      }
                      className="rounded-full border border-line px-4 py-2 text-sm font-medium disabled:opacity-40"
                    >
                      Disconnect
                    </button>
                  </div>
                </div>
                {row.qr_base64 ? (
                  <img
                    alt={`WhatsApp QR for ${row.name}`}
                    className="h-44 w-44 justify-self-center rounded-xl bg-white p-2"
                    src={row.qr_base64.startsWith("data:") ? row.qr_base64 : `data:image/png;base64,${row.qr_base64}`}
                  />
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
