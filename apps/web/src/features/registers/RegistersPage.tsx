import type { Device, DeviceActivationKey, DeviceKey } from "@ai-pos/shared-types";
import { Copy, Download, KeyRound, MonitorSmartphone, Plus, RotateCw, ShieldOff } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { Toast } from "../../components/ui/Toast";
import { apiGet, apiPost } from "../../lib/api";
import { useAuth, useIsSuperAdmin } from "../../lib/auth";
import { formatDate, storeOptions, useStores } from "../inventory/shared";
import { errorMessage } from "../users/api";

function seen(device: Device): { label: string; live: boolean } {
  if (device.revoked_at) return { label: "Revoked", live: false };
  if (!device.last_seen_at) return { label: "Never connected", live: false };
  const minutes = (Date.now() - new Date(device.last_seen_at).getTime()) / 60_000;
  if (minutes < 10) return { label: "Online", live: true };
  return { label: `Seen ${formatDate(device.last_seen_at)}`, live: false };
}

export function RegistersPage() {
  const { user } = useAuth();
  const superAdmin = useIsSuperAdmin();
  const { stores } = useStores();
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [issued, setIssued] = useState<DeviceKey | null>(null);
  const [activation, setActivation] = useState<{ device: Device; key: DeviceActivationKey } | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);

  const load = useCallback(async () => {
    try {
      setDevices(await apiGet<Device[]>("/api/v1/devices"));
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load registers."));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const act = async (device: Device, action: "rotate" | "revoke") => {
    const question =
      action === "revoke"
        ? `Revoke ${device.code}? It stops syncing until it gets a new key.`
        : `Issue a new key for ${device.code}? The old key stops working immediately.`;
    if (!window.confirm(question)) return;
    try {
      if (action === "rotate") setIssued(await apiPost<DeviceKey>(`/api/v1/devices/${device.id}/rotate`, {}));
      else {
        await apiPost<Device>(`/api/v1/devices/${device.id}/revoke`, {});
        setToast(`${device.code} revoked.`);
      }
      await load();
    } catch (caught) {
      setError(errorMessage(caught, "Could not update the register."));
    }
  };

  const issueActivation = async (device: Device) => {
    try {
      const key = await apiPost<DeviceActivationKey>(`/api/v1/devices/${device.id}/activation-key`, {});
      setActivation({ device, key });
    } catch (caught) {
      setError(errorMessage(caught, "Could not create an activation key."));
    }
  };

  const rows = devices ?? [];
  const online = rows.filter((device) => seen(device).live).length;

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">Registered tills</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{rows.filter((device) => !device.revoked_at).length}</p>
          <p className="mt-2 text-xs text-white/50">Each has its own key and invoice series</p>
        </article>
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">Online now</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{online}</p>
          <p className="mt-2 text-xs text-white/80">Synced in the last 10 minutes</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Invoices numbered offline</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">
            {rows.reduce((sum, device) => sum + device.last_invoice_value, 0)}
          </p>
          <p className="mt-2 text-xs text-charcoal/50">Across every register series</p>
        </article>
      </div>

      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Registers</h2>
            <p className="text-sm text-charcoal/60">Keys replace the shared API key and bind each till to its branch.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {superAdmin ? (
              <Link
                to="/downloads"
                className="inline-flex items-center justify-center rounded-full border border-gray-200 bg-white px-6 py-2.5 text-sm font-medium text-black transition-colors hover:bg-gray-50"
              >
                <Download size={16} aria-hidden="true" className="-ml-2 mr-1.5" />
                Download POS app
              </Link>
            ) : null}
            <PrimaryButton onClick={() => setCreating(true)}>
              <Plus size={16} aria-hidden="true" className="-ml-2 mr-1.5" />
              Register a till
            </PrimaryButton>
          </div>
        </div>
        <ErrorNote message={error} />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[880px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="pb-3 font-medium">Register</th>
                <th className="pb-3 font-medium">Branch</th>
                <th className="pb-3 font-medium">Invoice series</th>
                <th className="pb-3 text-right font-medium">Last number</th>
                <th className="pb-3 pl-6 font-medium">Status</th>
                <th className="pb-3 font-medium">Key</th>
                <th className="pb-3 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((device) => {
                const state = seen(device);
                return (
                  <tr key={device.id} className={`border-t border-line ${device.revoked_at ? "opacity-50" : ""}`}>
                    <td className="py-3">
                      <span className="flex items-center gap-2 font-medium">
                        <MonitorSmartphone size={16} aria-hidden="true" className="text-charcoal/50" />
                        {device.code}
                      </span>
                      <span className="block text-xs text-charcoal/50">{device.name}</span>
                    </td>
                    <td className="py-3">{device.store_code}</td>
                    <td className="py-3 font-mono text-xs">{device.invoice_prefix}-NNNNNN</td>
                    <td className="py-3 text-right tabular-nums">{device.last_invoice_value}</td>
                    <td className="py-3 pl-6">
                      <span
                        className={`inline-flex rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                          state.live ? "bg-accent text-white" : "bg-surface text-charcoal/60 ring-1 ring-line"
                        }`}
                      >
                        {state.label}
                      </span>
                    </td>
                    <td className="py-3 font-mono text-xs text-charcoal/60">…{device.key_hint}</td>
                    <td className="py-3">
                      <div className="flex justify-end gap-1">
                        <button
                          type="button"
                          title="Generate activation key"
                          aria-label={`Generate activation key for ${device.code}`}
                          onClick={() => void issueActivation(device)}
                          className="inline-flex h-9 items-center gap-1.5 rounded-full border border-line px-3 text-xs font-semibold hover:border-accent hover:text-accent"
                        >
                          <KeyRound size={14} aria-hidden="true" /> Activate
                        </button>
                        <button
                          type="button"
                          title="Issue a new key"
                          aria-label={`Issue a new key for ${device.code}`}
                          onClick={() => void act(device, "rotate")}
                          className="flex h-9 w-9 items-center justify-center rounded-full border border-line hover:border-accent hover:text-accent"
                        >
                          <RotateCw size={15} aria-hidden="true" />
                        </button>
                        {!device.revoked_at ? (
                          <button
                            type="button"
                            title="Revoke"
                            aria-label={`Revoke ${device.code}`}
                            onClick={() => void act(device, "revoke")}
                            className="flex h-9 w-9 items-center justify-center rounded-full border border-line hover:border-accent hover:text-accent"
                          >
                            <ShieldOff size={15} aria-hidden="true" />
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {devices !== null && rows.length === 0 ? (
            <p className="py-8 text-sm text-charcoal/60">No registers yet. Registers on the shared key keep working in dev.</p>
          ) : null}
        </div>
      </div>

      {creating ? (
        <CreateRegisterModal
          stores={stores}
          defaultStore={user?.store_id ?? stores[0]?.id ?? ""}
          onClose={() => setCreating(false)}
          onCreated={(result) => {
            setCreating(false);
            void issueActivation(result.device);
            void load();
          }}
        />
      ) : null}
      {issued ? <KeyModal issued={issued} onClose={() => setIssued(null)} /> : null}
      {activation ? (
        <ActivationModal device={activation.device} activation={activation.key} onClose={() => setActivation(null)} />
      ) : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}

function CreateRegisterModal({
  stores,
  defaultStore,
  onClose,
  onCreated,
}: {
  stores: ReturnType<typeof useStores>["stores"];
  defaultStore: string;
  onClose: () => void;
  onCreated: (result: DeviceKey) => void;
}) {
  const [storeId, setStoreId] = useState(defaultStore);
  const [code, setCode] = useState("R01");
  const [name, setName] = useState("Front counter");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      onCreated(await apiPost<DeviceKey>("/api/v1/devices", { store_id: storeId, code: code.trim(), name: name.trim() }));
    } catch (caught) {
      setError(errorMessage(caught, "Could not register the till."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Register a till"
      subtitle="Next you get a one-time activation key to enter on the new register."
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy || !storeId || !code.trim()} onClick={() => void save()}>
            {busy ? "Registering…" : "Register and get activation key"}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        <SelectField label="Branch" value={storeId} options={storeOptions(stores)} placeholder="Choose a branch" onChange={setStoreId} />
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            label="Code"
            value={code}
            maxLength={12}
            hint="Letters and digits, e.g. R01"
            onChange={(event) => setCode(event.target.value.replace(/[^A-Za-z0-9]/g, "").toUpperCase())}
          />
          <TextField label="Name" value={name} onChange={(event) => setName(event.target.value)} />
        </div>
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}

function ActivationModal({
  device,
  activation,
  onClose,
}: {
  device: Device;
  activation: DeviceActivationKey;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <Modal
      title={`Activate ${device.code}`}
      subtitle="On the new register, open AI POS and enter these two values. The key works once."
      onClose={onClose}
      footer={<PrimaryButton onClick={onClose}>Done</PrimaryButton>}
    >
      <dl className="space-y-3">
        <div className="rounded-2xl bg-surface p-4">
          <dt className="text-[11px] font-semibold uppercase tracking-[0.18em] text-charcoal/50">Store subdomain</dt>
          <dd className="mt-1 font-mono text-lg font-semibold">{activation.tenant_domain}</dd>
        </div>
        <div className="rounded-2xl bg-charcoal p-4 text-white">
          <dt className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-white/50">
            <KeyRound size={14} aria-hidden="true" /> Activation key
          </dt>
          <dd className="mt-1 font-mono text-2xl font-semibold tracking-[0.2em]">{activation.activation_key}</dd>
        </div>
      </dl>
      <button
        type="button"
        onClick={() => {
          void navigator.clipboard
            .writeText(`Subdomain: ${activation.tenant_domain}\nActivation key: ${activation.activation_key}`)
            .then(() => setCopied(true));
        }}
        className="mt-3 inline-flex items-center gap-2 rounded-full border border-line px-4 py-2 text-sm font-semibold hover:border-accent hover:text-accent"
      >
        <Copy size={14} aria-hidden="true" /> {copied ? "Copied" : "Copy both"}
      </button>
      <p className="mt-4 text-sm text-charcoal/60">
        Valid until {formatDate(activation.expires_at)}. Generating a new key cancels this one; activating replaces the
        register's previous key.
      </p>
    </Modal>
  );
}

function KeyModal({ issued, onClose }: { issued: DeviceKey; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  return (
    <Modal
      title={`Key for ${issued.device.code}`}
      subtitle="Copy it now. It cannot be shown again."
      onClose={onClose}
      footer={<PrimaryButton onClick={onClose}>Done</PrimaryButton>}
    >
      <div className="rounded-2xl bg-charcoal p-4 text-white">
        <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-white/50">
          <KeyRound size={14} aria-hidden="true" /> DEVICE_KEY
        </p>
        <p className="mt-2 break-all font-mono text-sm">{issued.key}</p>
      </div>
      <button
        type="button"
        onClick={() => {
          void navigator.clipboard.writeText(`DEVICE_KEY=${issued.key}`).then(() => setCopied(true));
        }}
        className="mt-3 inline-flex items-center gap-2 rounded-full border border-line px-4 py-2 text-sm font-semibold hover:border-accent hover:text-accent"
      >
        <Copy size={14} aria-hidden="true" /> {copied ? "Copied" : "Copy as .env line"}
      </button>
      <p className="mt-4 text-sm text-charcoal/60">
        Invoices from this till are numbered <span className="font-mono">{issued.device.invoice_prefix}-000001</span> onward.
      </p>
    </Modal>
  );
}
