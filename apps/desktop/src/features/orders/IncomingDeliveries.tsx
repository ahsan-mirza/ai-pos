import { formatMoney, type DeliveryChannel, type Order } from "@ai-pos/shared-types";
import { Bell, Check, Truck, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

function chime() {
  try {
    const context = new AudioContext();
    const tone = context.createOscillator();
    const gain = context.createGain();
    tone.frequency.value = 660;
    gain.gain.value = 0.1;
    tone.connect(gain).connect(context.destination);
    tone.start();
    tone.stop(context.currentTime + 0.35);
  } catch {
    // Audio is optional.
  }
}

/** Delivery-app orders waiting for the restaurant: accept with a prep time (they go to the kitchen) or reject. */
export function IncomingDeliveries({
  orders,
  currency,
  busy,
  onAccept,
  onReject,
}: {
  orders: Order[];
  currency: string;
  busy: boolean;
  onAccept: (order: Order, prepMinutes: number) => void;
  onReject: (order: Order, reason: string) => void;
}) {
  const [prep, setPrep] = useState<Record<string, string>>({});
  const seen = useRef(new Set<string>());

  useEffect(() => {
    const fresh = orders.filter((order) => !seen.current.has(order.id));
    for (const order of orders) seen.current.add(order.id);
    if (fresh.length > 0) chime();
  }, [orders]);

  if (orders.length === 0) return null;
  return (
    <section aria-label="Incoming delivery orders" className="rounded-2xl border-2 border-amber-400/70 bg-amber-500/10 p-3">
      <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold">
        <Bell size={15} aria-hidden="true" className="text-amber-600" /> Incoming delivery orders ({orders.length})
      </h2>
      <ul className="space-y-2">
        {orders.map((order) => (
          <li key={order.id} className="flex flex-wrap items-center gap-3 rounded-xl bg-white px-3 py-2 text-sm dark:bg-charcoal">
            <Truck size={16} aria-hidden="true" className="shrink-0 text-primary" />
            <div className="min-w-0 flex-1">
              <p className="font-semibold">
                {order.channel_name} {order.external_ref} · #{order.number}
              </p>
              <p className="truncate text-xs text-zinc-500 dark:text-white/50">
                {order.items.map((item) => `${item.quantity} × ${item.product_name}`).join(", ")}
                {order.note ? ` · ${order.note}` : ""}
              </p>
            </div>
            <span className="font-bold tabular-nums">{formatMoney(order.open_cents, currency)}</span>
            <label className="flex items-center gap-1 text-xs">
              Ready in
              <input
                inputMode="numeric"
                value={prep[order.id] ?? String(order.prep_minutes ?? 20)}
                onChange={(event) => setPrep({ ...prep, [order.id]: event.target.value.replace(/\D/g, "") })}
                className="h-8 w-12 rounded-lg border border-zinc-200 bg-white px-2 text-right tabular-nums dark:border-white/10 dark:bg-zinc-900"
              />
              min
            </label>
            <button
              type="button"
              disabled={busy}
              onClick={() => onAccept(order, Math.max(1, Number(prep[order.id] ?? order.prep_minutes ?? 20) || 20))}
              className="flex h-9 items-center gap-1 rounded-full bg-emerald-500 px-3 text-xs font-semibold text-white disabled:opacity-50"
            >
              <Check size={14} aria-hidden="true" /> Accept
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                const reason = window.prompt("Why reject this order?", "Kitchen too busy");
                if (reason !== null) onReject(order, reason.trim() || "Rejected by the restaurant");
              }}
              className="flex h-9 items-center gap-1 rounded-full bg-zinc-200 px-3 text-xs font-semibold disabled:opacity-50 dark:bg-white/10"
            >
              <X size={14} aria-hidden="true" /> Reject
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Key in an order taken on a delivery app's tablet: pick the app and its order number, then add the items. */
export function KeyInDeliveryModal({
  channels,
  onClose,
  onSubmit,
}: {
  channels: DeliveryChannel[];
  onClose: () => void;
  onSubmit: (channelId: string, externalRef: string, customerName: string | null) => void;
}) {
  const titleId = useId();
  const active = channels.filter((channel) => channel.is_active);
  const [channelId, setChannelId] = useState(active[0]?.id ?? "");
  const [reference, setReference] = useState("");
  const [customer, setCustomer] = useState("");
  return (
    <div className="modal-backdrop" role="presentation">
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="modal-card max-w-sm space-y-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (channelId && reference.trim()) onSubmit(channelId, reference.trim(), customer.trim() || null);
        }}
      >
        <h2 id={titleId} className="text-lg font-semibold">
          Delivery-app order
        </h2>
        {active.length === 0 ? (
          <p className="text-sm text-zinc-500">No delivery channels yet. Add them in the portal under Settings, Delivery channels.</p>
        ) : (
          <>
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Delivery app">
              {active.map((channel) => (
                <button
                  key={channel.id}
                  type="button"
                  aria-pressed={channelId === channel.id}
                  onClick={() => setChannelId(channel.id)}
                  className={`h-9 rounded-full px-3 text-sm font-semibold ${channelId === channel.id ? "bg-primary text-white" : "bg-zinc-100 dark:bg-white/10"}`}
                >
                  {channel.name}
                </button>
              ))}
            </div>
            <input autoFocus value={reference} onChange={(event) => setReference(event.target.value)} maxLength={64} placeholder="App order number" className="modal-input" />
            <input value={customer} onChange={(event) => setCustomer(event.target.value)} maxLength={120} placeholder="Customer name (optional)" className="modal-input" />
          </>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" className="modal-cancel" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="modal-save" disabled={!channelId || !reference.trim()}>
            Open order
          </button>
        </div>
      </form>
    </div>
  );
}
