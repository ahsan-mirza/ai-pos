import {
  formatMoney,
  type ChannelSettlementReport,
  type DeliveryChannel,
  type DeliveryChannelInput,
  type DeliveryChannelSecret,
} from "@ai-pos/shared-types";
import { actionHoverClass } from "@ai-pos/ui";
import { Copy, KeyRound, Plus, Truck } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useConfirm } from "../../components/ui/ConfirmDialog";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { Toggle } from "../../components/ui/Toggle";
import { env } from "../../config/env";
import { apiGet, apiPost, apiPut } from "../../lib/api";
import { useCurrency } from "../../lib/currency";
import { message } from "../customers/api";
import { storeOptions, useStores } from "../inventory/shared";

const iso = (value: Date) =>
  `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;

const SAMPLE = {
  external_id: "TLB-102938",
  customer: { name: "Sara", phone: "+971500000000", address: "Marina Walk, Tower 3" },
  items: [{ sku: "BURGER-CLASSIC", quantity: 2, unit_price_cents: 3200, note: "No onion" }],
  notes: "Leave at reception",
  total_cents: 6400,
  paid: true,
};

function webhookUrl(channel: DeliveryChannel): string {
  return `${env.apiBaseUrl}${channel.webhook_path}`;
}

function copy(text: string) {
  void navigator.clipboard?.writeText(text);
}

function ChannelModal({
  channel,
  onClose,
  onSaved,
}: {
  channel: DeliveryChannel | null;
  onClose: () => void;
  onSaved: (secret: DeliveryChannelSecret | null) => void;
}) {
  const { stores } = useStores();
  const [draft, setDraft] = useState<DeliveryChannelInput>(
    channel ?? {
      name: "",
      code: "",
      store_id: "",
      commission_bps: 2000,
      price_markup_bps: 0,
      auto_accept: false,
      default_prep_minutes: 20,
      is_active: true,
    },
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (draft.store_id === "" && stores.length > 0) {
      setDraft((current) => ({ ...current, store_id: stores.find((store) => !store.is_warehouse)?.id ?? stores[0]!.id }));
    }
  }, [stores, draft.store_id]);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      if (channel) {
        await apiPut<DeliveryChannel>(`/api/v1/channels/${channel.id}`, draft);
        onSaved(null);
      } else {
        onSaved(await apiPost<DeliveryChannelSecret>("/api/v1/channels", draft));
      }
    } catch (caught) {
      setError(message(caught, "Could not save the channel."));
      setBusy(false);
    }
  }

  const percent = (bps: number) => String(bps / 100);
  const toBps = (value: string) => Math.round((Number(value) || 0) * 100);

  return (
    <Modal
      title={channel ? `Edit ${channel.name}` : "New delivery channel"}
      onClose={onClose}
      footer={
        <div className="flex w-full justify-end gap-2">
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy || draft.name.trim() === "" || draft.code === ""} onClick={() => void save()}>
            Save
          </PrimaryButton>
        </div>
      }
    >
      <div className="grid gap-3 md:grid-cols-2">
        <TextField
          label="Name"
          value={draft.name}
          maxLength={60}
          placeholder="Talabat"
          onChange={(event) => {
            const name = event.target.value;
            setDraft((current) => ({
              ...current,
              name,
              code: channel ? current.code : name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 32),
            }));
          }}
        />
        <TextField
          label="Code (in the webhook URL)"
          value={draft.code}
          maxLength={32}
          onChange={(event) => setDraft({ ...draft, code: event.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "") })}
        />
        <SelectField label="Orders arrive at" value={draft.store_id} options={storeOptions(stores)} onChange={(store_id) => setDraft({ ...draft, store_id })} />
        <TextField
          label="Default prep time (min)"
          type="number"
          min={1}
          value={String(draft.default_prep_minutes)}
          onChange={(event) => setDraft({ ...draft, default_prep_minutes: Number(event.target.value) || 20 })}
        />
        <TextField
          label="Commission (%)"
          inputMode="decimal"
          value={percent(draft.commission_bps)}
          onChange={(event) => setDraft({ ...draft, commission_bps: toBps(event.target.value) })}
        />
        <TextField
          label="Menu markup on the app (%)"
          inputMode="decimal"
          value={percent(draft.price_markup_bps)}
          hint="Used when the app sends items without prices."
          onChange={(event) => setDraft({ ...draft, price_markup_bps: toBps(event.target.value) })}
        />
      </div>
      <div className="mt-3 space-y-2">
        <Toggle
          label="Accept automatically"
          description="Orders go straight to the kitchen with the default prep time, without waiting at the register."
          checked={draft.auto_accept}
          onChange={(auto_accept) => setDraft({ ...draft, auto_accept })}
        />
        <Toggle label="Active" checked={draft.is_active} onChange={(is_active) => setDraft({ ...draft, is_active })} />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}

function SecretModal({ secret, onClose }: { secret: DeliveryChannelSecret; onClose: () => void }) {
  const url = webhookUrl(secret.channel);
  return (
    <Modal title={`${secret.channel.name} webhook`} subtitle="Copy the secret now; it is not shown again." onClose={onClose} width="lg">
      <div className="space-y-3 text-sm">
        {[
          ["Webhook URL (POST)", url],
          ["Signing secret", secret.webhook_secret],
        ].map(([label, value]) => (
          <div key={label}>
            <p className="text-xs text-charcoal/60">{label}</p>
            <div className="mt-1 flex items-center gap-2 rounded-xl bg-surface px-3 py-2 font-mono text-xs">
              <span className="min-w-0 flex-1 break-all">{value}</span>
              <button type="button" aria-label={`Copy ${label}`} onClick={() => copy(value!)} className={`shrink-0 rounded-full px-2 py-1 text-charcoal/60 ${actionHoverClass("neutral")}`}>
                <Copy size={14} aria-hidden="true" />
              </button>
            </div>
          </div>
        ))}
        <p className="text-xs text-charcoal/60">
          Sign the raw body with HMAC-SHA256 using the secret and send it as <span className="font-mono">X-Channel-Signature: sha256=&lt;hex&gt;</span>.
          Each order is accepted once per <span className="font-mono">external_id</span>; items match by product id, SKU, barcode or PLU.
        </p>
        <pre className="overflow-x-auto rounded-xl bg-charcoal p-3 text-[11px] text-white">{JSON.stringify(SAMPLE, null, 2)}</pre>
      </div>
    </Modal>
  );
}

function PayoutModal({
  row,
  onClose,
  onSaved,
}: {
  row: ChannelSettlementReport["rows"][number];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { currency } = useCurrency();
  const [amount, setAmount] = useState((Math.max(0, row.outstanding_cents) / 100).toFixed(2));
  const [commission, setCommission] = useState((row.commission_cents / 100).toFixed(2));
  const [reference, setReference] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function save() {
    const cents = Math.round(Number(amount) * 100);
    const kept = Math.round(Number(commission) * 100);
    if (!Number.isFinite(cents) || cents < 0 || !Number.isFinite(kept) || kept < 0) return setError("Enter the amounts like 1250.00.");
    try {
      await apiPost(`/api/v1/channels/${row.channel_id}/payouts`, { amount_cents: cents, commission_cents: kept, reference: reference || null });
      onSaved();
    } catch (caught) {
      setError(message(caught, "Could not record the payout."));
    }
  }

  return (
    <Modal
      title={`Payout from ${row.name}`}
      subtitle={`Outstanding ${formatMoney(row.outstanding_cents, currency)}`}
      onClose={onClose}
      footer={
        <div className="flex w-full justify-end gap-2">
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton onClick={() => void save()}>Mark received</PrimaryButton>
        </div>
      }
    >
      <div className="grid gap-3 md:grid-cols-2">
        <TextField label="Received in the bank" inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} />
        <TextField label="Commission the app kept" inputMode="decimal" value={commission} onChange={(event) => setCommission(event.target.value)} />
        <TextField label="Payout reference" value={reference} maxLength={80} onChange={(event) => setReference(event.target.value)} />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}

/** Delivery apps: their webhooks, commission, and what each owes until it pays out. */
export function ChannelsPage() {
  const { currency } = useCurrency();
  const [channels, setChannels] = useState<DeliveryChannel[]>([]);
  const [editing, setEditing] = useState<DeliveryChannel | "new" | null>(null);
  const [secret, setSecret] = useState<DeliveryChannelSecret | null>(null);
  const [range, setRange] = useState(() => {
    const today = new Date();
    return { from: iso(new Date(today.getFullYear(), today.getMonth(), 1)), to: iso(today) };
  });
  const [report, setReport] = useState<ChannelSettlementReport | null>(null);
  const [payout, setPayout] = useState<ChannelSettlementReport["rows"][number] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const confirm = useConfirm();

  const query = useMemo(() => new URLSearchParams({ from: range.from, to: range.to }).toString(), [range]);

  const load = useCallback(async () => {
    try {
      const [nextChannels, nextReport] = await Promise.all([
        apiGet<DeliveryChannel[]>("/api/v1/channels"),
        apiGet<ChannelSettlementReport>(`/api/v1/channels/settlement?${query}`),
      ]);
      setChannels(nextChannels);
      setReport(nextReport);
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not load the delivery channels."));
    }
  }, [query]);

  useEffect(() => {
    void load();
  }, [load]);

  async function rotate(channel: DeliveryChannel) {
    const accepted = await confirm({
      title: "Issue a new secret",
      message: `Issue a new secret for ${channel.name}? The old one stops working at once.`,
      confirmLabel: "Issue secret",
      tone: "danger",
    });
    if (!accepted) return;
    try {
      setSecret(await apiPost<DeliveryChannelSecret>(`/api/v1/channels/${channel.id}/rotate-secret`, {}));
    } catch (caught) {
      setError(message(caught, "Could not rotate the secret."));
    }
  }

  return (
    <section className="space-y-4">
      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-charcoal text-white">
              <Truck size={20} aria-hidden="true" />
            </span>
            <div>
              <h2 className="text-xl font-semibold">Delivery channels</h2>
              <p className="text-sm text-charcoal/60">
                Apps post orders to a signed webhook, or cashiers key them in. Registers accept them into the kitchen.
              </p>
            </div>
          </div>
          <PrimaryButton onClick={() => setEditing("new")}>
            <Plus size={15} aria-hidden="true" /> Channel
          </PrimaryButton>
        </div>
        <ErrorNote message={error} />
        <div className="space-y-2">
          {channels.map((channel) => (
            <div key={channel.id} className={`flex flex-wrap items-center gap-3 rounded-2xl border border-line p-4 ${channel.is_active ? "" : "opacity-50"}`}>
              <div className="min-w-0 flex-1">
                <p className="font-semibold">
                  {channel.name}
                  <span className="ml-2 text-xs font-normal text-charcoal/50">
                    {(channel.commission_bps / 100).toFixed(1)}% commission{channel.auto_accept ? " · accepts automatically" : ""}
                  </span>
                </p>
                <p className="mt-1 flex items-center gap-1.5 truncate font-mono text-xs text-charcoal/60">
                  {webhookUrl(channel)}
                  <button type="button" aria-label="Copy webhook URL" onClick={() => copy(webhookUrl(channel))} className={`rounded-full px-2 py-1 ${actionHoverClass("neutral")}`}>
                    <Copy size={12} aria-hidden="true" />
                  </button>
                </p>
              </div>
              <GhostButton onClick={() => void rotate(channel)}>
                <KeyRound size={14} aria-hidden="true" /> New secret
              </GhostButton>
              <GhostButton onClick={() => setEditing(channel)}>Edit</GhostButton>
            </div>
          ))}
          {channels.length === 0 ? <p className="text-sm text-charcoal/60">No channels yet. Add each delivery app you sell on.</p> : null}
        </div>
      </div>

      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h3 className="text-lg font-semibold">Commission &amp; settlement</h3>
            <p className="text-sm text-charcoal/60">Orders paid on each app, the commission it keeps, and what it still owes you.</p>
          </div>
          <div className="flex items-end gap-3">
            <TextField label="From" type="date" value={range.from} onChange={(event) => setRange((current) => ({ ...current, from: event.target.value }))} />
            <TextField label="To" type="date" value={range.to} onChange={(event) => setRange((current) => ({ ...current, to: event.target.value }))} />
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-charcoal/50">
                <th className="py-2">Channel</th>
                <th className="py-2 text-right">Orders</th>
                <th className="py-2 text-right">Paid on app</th>
                <th className="py-2 text-right">Commission</th>
                <th className="py-2 text-right">Net</th>
                <th className="py-2 text-right">Paid out</th>
                <th className="py-2 text-right">Outstanding</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {(report?.rows ?? []).map((row) => (
                <tr key={row.channel_id} className="border-b border-line/60">
                  <td className="py-2.5 font-medium">{row.name}</td>
                  <td className="py-2.5 text-right tabular-nums">{row.orders}</td>
                  <td className="py-2.5 text-right tabular-nums">{formatMoney(row.gross_cents, currency)}</td>
                  <td className="py-2.5 text-right tabular-nums text-charcoal/60">{formatMoney(row.commission_cents, currency)}</td>
                  <td className="py-2.5 text-right tabular-nums">{formatMoney(row.net_cents, currency)}</td>
                  <td className="py-2.5 text-right tabular-nums">{formatMoney(row.paid_out_cents, currency)}</td>
                  <td className={`py-2.5 text-right font-semibold tabular-nums ${row.outstanding_cents > 0 ? "text-accent" : ""}`}>
                    {formatMoney(row.outstanding_cents, currency)}
                  </td>
                  <td className="py-2.5 text-right">
                    <GhostButton onClick={() => setPayout(row)}>Payout received</GhostButton>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {report && report.payouts.length > 0 ? (
          <div className="mt-4">
            <h4 className="mb-2 text-sm font-semibold">Payouts in this period</h4>
            <ul className="space-y-1 text-sm">
              {report.payouts.map((item) => (
                <li key={item.id} className="flex justify-between rounded-xl bg-surface px-3 py-2">
                  <span>
                    {item.channel_name} · {item.received_at.slice(0, 10)}
                    {item.reference ? ` · ${item.reference}` : ""}
                  </span>
                  <span className="tabular-nums">
                    {formatMoney(item.amount_cents, currency)}
                    {item.commission_cents ? <span className="text-charcoal/50"> + {formatMoney(item.commission_cents, currency)} commission</span> : null}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>

      {editing ? (
        <ChannelModal
          channel={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={(created) => {
            setEditing(null);
            if (created) setSecret(created);
            void load();
          }}
        />
      ) : null}
      {secret ? <SecretModal secret={secret} onClose={() => setSecret(null)} /> : null}
      {payout ? (
        <PayoutModal
          row={payout}
          onClose={() => setPayout(null)}
          onSaved={() => {
            setPayout(null);
            void load();
          }}
        />
      ) : null}
    </section>
  );
}
