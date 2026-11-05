import { Permission, hasPermission } from "@ai-pos/shared-types";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { ApiRequestError, apiGet, apiPost } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { storeOptions, useStores } from "../inventory/shared";

interface Provider {
  code: string;
  name: string;
  kind: string;
  status: string;
  countries: string[];
  capabilities: string[];
  detail: string;
}

interface Connection {
  id: string;
  provider: string;
  market: string;
  store_id: string;
  status: string;
  channel_id: string | null;
  webhook_path: string | null;
  webhook_secret: string | null;
  last_error: string | null;
}

interface Health {
  connections: number;
  active_connections: number;
  open_orders: number;
  available_providers: number;
  awaiting_partner: number;
}

interface DeliveryOrder {
  id: string;
  number: number;
  status: string;
  external_ref: string | null;
  channel_status: string | null;
}

function problem(caught: unknown, fallback: string): string {
  return caught instanceof ApiRequestError ? caught.message : fallback;
}

export function DeliveryPage() {
  const { user } = useAuth();
  const canManage = hasPermission(user, Permission.DeliveryManage);
  const { stores } = useStores();
  const [health, setHealth] = useState<Health | null>(null);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [orders, setOrders] = useState<DeliveryOrder[]>([]);
  const [provider, setProvider] = useState("generic");
  const [market, setMarket] = useState("");
  const [storeId, setStoreId] = useState("");
  const [secret, setSecret] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [nextHealth, nextProviders, nextConnections, nextOrders] = await Promise.all([
      apiGet<Health>("/api/v1/delivery/health"),
      apiGet<Provider[]>("/api/v1/delivery/providers"),
      apiGet<Connection[]>("/api/v1/delivery/connections"),
      apiGet<DeliveryOrder[]>("/api/v1/delivery/orders"),
    ]);
    setHealth(nextHealth);
    setProviders(nextProviders);
    setConnections(nextConnections);
    setOrders(nextOrders);
  }, []);

  useEffect(() => {
    void load().catch((caught) => setError(problem(caught, "Delivery Integrations could not be loaded.")));
  }, [load]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await load();
    } catch (caught) {
      setError(problem(caught, "That delivery action failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-charcoal">Delivery Integrations</h1>
        <p className="mt-2 max-w-3xl text-sm text-charcoal/70">
          Connect a branch to a delivery source. Named marketplaces stay unavailable until partner API access is
          approved. Live orders still arrive through{" "}
          <Link className="text-accent underline" to="/settings/channels">
            Delivery channels
          </Link>
          , then follow the existing register and kitchen flow.
        </p>
      </div>

      {health && (
        <div className="grid gap-3 sm:grid-cols-4">
          {[
            ["Connections", health.connections],
            ["Active", health.active_connections],
            ["Open delivery orders", health.open_orders],
            ["Awaiting partner", health.awaiting_partner],
          ].map(([label, value]) => (
            <div key={label} className="rounded-2xl border border-charcoal/10 bg-surface px-4 py-3">
              <p className="text-xs uppercase tracking-wide text-charcoal/50">{label}</p>
              <p className="mt-1 text-2xl font-semibold">{value}</p>
            </div>
          ))}
        </div>
      )}

      <section>
        <h2 className="text-lg font-semibold">Providers</h2>
        <div className="mt-3 overflow-x-auto rounded-2xl border border-charcoal/10">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-canvas text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="px-4 py-3">Provider</th>
                <th className="px-4 py-3">Route</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">What it can do</th>
              </tr>
            </thead>
            <tbody>
              {providers.map((item) => (
                <tr key={item.code} className="border-t border-charcoal/10">
                  <td className="px-4 py-3 font-medium">{item.name}</td>
                  <td className="px-4 py-3">{item.kind}</td>
                  <td className="px-4 py-3">{item.status === "available" ? "Available" : "Awaiting partner approval"}</td>
                  <td className="px-4 py-3 text-charcoal/70">
                    {item.capabilities.length > 0 ? item.capabilities.join(", ") : "No production operations"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {canManage && (
        <section className="rounded-2xl border border-charcoal/10 p-4">
          <h2 className="text-lg font-semibold">New connection</h2>
          <div className="mt-4 grid gap-4 sm:grid-cols-3">
            <SelectField
              label="Provider"
              value={provider}
              onChange={setProvider}
              options={providers.map((item) => ({
                value: item.code,
                label: item.status === "available" ? item.name : `${item.name} — awaiting partner approval`,
                disabled: item.status !== "available",
              }))}
            />
            <TextField label="Market" value={market} onChange={(event) => setMarket(event.target.value)} maxLength={8} />
            <SelectField
              label="Branch"
              value={storeId}
              placeholder="Choose a branch"
              onChange={setStoreId}
              options={storeOptions(stores)}
            />
          </div>
          <div className="mt-4">
            <PrimaryButton
              disabled={busy || storeId === "" || provider !== "generic"}
              onClick={() =>
                void run(async () => {
                  await apiPost("/api/v1/delivery/connections", {
                    provider,
                    market,
                    store_id: storeId,
                  });
                })
              }
            >
              Save connection
            </PrimaryButton>
          </div>
        </section>
      )}

      <section>
        <h2 className="text-lg font-semibold">Connections</h2>
        <div className="mt-3 space-y-3">
          {connections.length === 0 && <p className="text-sm text-charcoal/60">No connections yet.</p>}
          {connections.map((item) => (
            <div key={item.id} className="rounded-2xl border border-charcoal/10 px-4 py-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="font-medium">
                    {item.provider} · {item.status}
                    {item.market ? ` · ${item.market}` : ""}
                  </p>
                  <p className="text-sm text-charcoal/60">
                    {item.webhook_path ?? "No live order channel yet."}
                    {item.last_error ? ` ${item.last_error}` : ""}
                  </p>
                </div>
                {canManage && (
                  <div className="flex gap-2">
                    <GhostButton disabled={busy} onClick={() => void run(async () => { await apiPost(`/api/v1/delivery/connections/${item.id}/test`, {}); })}>
                      Test
                    </GhostButton>
                    <GhostButton
                      disabled={busy}
                      onClick={() =>
                        void run(async () => {
                          const updated = await apiPost<Connection>(`/api/v1/delivery/connections/${item.id}/activate`, {});
                          setSecret(updated.webhook_secret);
                        })
                      }
                    >
                      Activate
                    </GhostButton>
                    <GhostButton disabled={busy} onClick={() => void run(async () => { await apiPost(`/api/v1/delivery/connections/${item.id}/pause`, {}); })}>
                      Pause
                    </GhostButton>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
        {secret && (
          <p className="mt-3 rounded-2xl bg-canvas px-4 py-3 text-sm">
            Webhook secret, shown once: <span className="font-mono">{secret}</span>
          </p>
        )}
      </section>

      <section>
        <h2 className="text-lg font-semibold">Recent delivery orders</h2>
        <p className="mt-1 text-sm text-charcoal/60">These are existing open orders linked to an activated connection.</p>
        <div className="mt-3 overflow-x-auto rounded-2xl border border-charcoal/10">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-canvas text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="px-4 py-3">Number</th>
                <th className="px-4 py-3">External id</th>
                <th className="px-4 py-3">Order status</th>
                <th className="px-4 py-3">Channel status</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => (
                <tr key={order.id} className="border-t border-charcoal/10">
                  <td className="px-4 py-3">{order.number}</td>
                  <td className="px-4 py-3">{order.external_ref ?? "—"}</td>
                  <td className="px-4 py-3">{order.status}</td>
                  <td className="px-4 py-3">{order.channel_status ?? "—"}</td>
                </tr>
              ))}
              {orders.length === 0 && (
                <tr>
                  <td className="px-4 py-3 text-charcoal/60" colSpan={4}>
                    No delivery orders yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
      <ErrorNote message={error} />
    </div>
  );
}
