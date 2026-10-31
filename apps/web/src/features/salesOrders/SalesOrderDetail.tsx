import {
  formatMoney,
  OPEN_SALES_ORDER_STATUSES,
  Permission,
  SALES_ORDER_SOURCE_LABELS,
  type DeliveryNote,
  type PaymentMethod,
  type SalesOrder,
} from "@ai-pos/shared-types";
import { ArrowLeft, Ban, ClipboardList, FileDown, PackageCheck, PenLine, Smartphone, Truck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { Toast } from "../../components/ui/Toast";
import { actionHoverClass, actionIntentFromLabel, type ActionIntent } from "@ai-pos/ui";
import { ApiRequestError } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { formatDate } from "../inventory/shared";
import { errorMessage } from "../users/api";
import { salesOrdersApi } from "./api";
import { OrderStatusChip } from "./SalesOrdersPage";
import { SignaturePad } from "./SignaturePad";

function iconAction(intent: ActionIntent) {
  return `flex h-9 w-9 items-center justify-center rounded-full border border-line disabled:opacity-40 ${actionHoverClass(intent)}`;
}

export function SalesOrderDetail({ orderId, onBack }: { orderId: string; onBack: () => void }) {
  const { user, can } = useAuth();
  const [order, setOrder] = useState<SalesOrder | null>(null);
  const [dispatching, setDispatching] = useState(false);
  const [trimming, setTrimming] = useState(false);
  const [ending, setEnding] = useState<"cancel" | "close" | null>(null);
  const [signing, setSigning] = useState<DeliveryNote | null>(null);
  const [creditBlocked, setCreditBlocked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);

  const load = useCallback(async () => {
    try {
      setOrder(await salesOrdersApi.get(orderId));
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load the order."));
    }
  }, [orderId]);

  useEffect(() => {
    void load();
  }, [load]);

  const run = async (work: () => Promise<SalesOrder>, done: (next: SalesOrder) => string) => {
    setBusy(true);
    try {
      const next = await work();
      setOrder(next);
      setError(null);
      setCreditBlocked(false);
      setToast(done(next));
      return true;
    } catch (caught) {
      setCreditBlocked(caught instanceof ApiRequestError && caught.code === "credit_limit");
      setError(errorMessage(caught, "Could not update the order."));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const pdf = async (open: () => Promise<void>) => {
    try {
      await open();
    } catch (caught) {
      setError(errorMessage(caught, "Could not open the PDF."));
    }
  };

  const open = order !== null && OPEN_SALES_ORDER_STATUSES.includes(order.status);
  const reserved = order?.lines.reduce((sum, line) => sum + Math.min(line.quantity_reserved, line.outstanding), 0) ?? 0;
  const backordered = order?.lines.reduce((sum, line) => sum + line.backordered, 0) ?? 0;
  const outstanding = order?.lines.reduce((sum, line) => sum + line.outstanding, 0) ?? 0;
  const currentPick = order?.pick_lists.find((pick) => pick.status === "OPEN") ?? null;

  return (
    <section className="space-y-4">
      <button type="button" onClick={onBack} className={`inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-sm font-medium text-charcoal/60 ${actionHoverClass("neutral")}`}>
        <ArrowLeft size={15} aria-hidden="true" /> All sales orders
      </button>
      {order ? (
        <div className="grid gap-4 md:grid-cols-3">
          <article className="rounded-card bg-charcoal p-6 text-white">
            <p className="text-sm text-white/60">Order value</p>
            <p className="mt-4 text-4xl font-semibold tabular-nums">{formatMoney(order.total_cents, order.currency)}</p>
            <p className="mt-2 text-xs text-white/50 tabular-nums">
              {formatMoney(order.delivered_cents, order.currency)} delivered and invoiced
            </p>
          </article>
          <article className="rounded-card bg-accent p-6 text-white">
            <p className="text-sm text-white/80">Ready to deliver</p>
            <p className="mt-4 text-4xl font-semibold tabular-nums">{open ? reserved : 0}</p>
            <p className="mt-2 text-xs text-white/80">Units reserved for this order at the branch</p>
          </article>
          <article className="rounded-card border border-line bg-white p-6">
            <p className="text-sm text-charcoal/60">Backordered</p>
            <p className={`mt-4 text-4xl font-semibold tabular-nums ${backordered ? "text-accent" : ""}`}>{backordered}</p>
            <p className="mt-2 text-xs text-charcoal/50">{outstanding} units still to deliver in all</p>
          </article>
        </div>
      ) : null}

      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="flex flex-wrap items-center gap-3 text-xl font-semibold">
              <span className="font-mono">{order?.number ?? "…"}</span>
              {order ? <OrderStatusChip status={order.status} /> : null}
            </h2>
            {order ? (
              <p className="mt-1 text-sm text-charcoal/60">
                <Link to={`/customers/${order.customer_id}`} className="font-medium text-charcoal hover:text-accent">
                  {order.customer_name}
                </Link>
                {` · ${SALES_ORDER_SOURCE_LABELS[order.source]}`}
                {order.customer_reference ? ` · Their ref ${order.customer_reference}` : ""}
                {order.requested_date ? ` · Wanted by ${formatDate(order.requested_date)}` : ""}
              </p>
            ) : null}
            {order?.delivery_address ? <p className="text-xs text-charcoal/50">Deliver to {order.delivery_address}</p> : null}
          </div>
          {order ? (
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" title="Order confirmation PDF" aria-label="Order PDF" onClick={() => void pdf(() => salesOrdersApi.orderPdf(order.id))} className={iconAction("info")}>
                <FileDown size={15} aria-hidden="true" />
              </button>
              {order.status === "DRAFT" ? (
                <>
                  {creditBlocked && can(Permission.CustomersManage) ? (
                    <GhostButton
                      disabled={busy}
                      onClick={() =>
                        void run(() => salesOrdersApi.confirm(order.id, user?.id ?? null), (next) => `${next.number} confirmed over the credit limit.`)
                      }
                    >
                      Approve credit and confirm
                    </GhostButton>
                  ) : null}
                  <PrimaryButton
                    disabled={busy}
                    onClick={() => void run(() => salesOrdersApi.confirm(order.id, null), (next) => `${next.number} confirmed; stock reserved.`)}
                  >
                    <PackageCheck size={16} aria-hidden="true" className="-ml-1 mr-1.5" /> Confirm order
                  </PrimaryButton>
                </>
              ) : null}
              {open ? (
                <>
                  {backordered ? (
                    <GhostButton
                      disabled={busy}
                      onClick={() =>
                        void run(
                          () => salesOrdersApi.allocate(order.id),
                          (next) => `${next.lines.reduce((sum, line) => sum + line.backordered, 0)} units still backordered.`,
                        )
                      }
                    >
                      Allocate stock
                    </GhostButton>
                  ) : null}
                  <GhostButton
                    disabled={busy || reserved === 0}
                    onClick={() => void run(() => salesOrdersApi.pick(order.id), (next) => `Pick list ${next.pick_lists.at(-1)?.number ?? ""} ready.`)}
                  >
                    <ClipboardList size={15} aria-hidden="true" className="-ml-1 mr-1.5" /> Pick list
                  </GhostButton>
                  <PrimaryButton disabled={busy || reserved === 0} onClick={() => setDispatching(true)}>
                    <Truck size={16} aria-hidden="true" className="-ml-1 mr-1.5" /> Dispatch
                  </PrimaryButton>
                </>
              ) : null}
              {order.status !== "DELIVERED" && order.status !== "CLOSED" && order.status !== "CANCELLED" ? (
                <>
                  {outstanding > 0 ? (
                    <GhostButton disabled={busy} onClick={() => setTrimming(true)}>
                      Cancel lines
                    </GhostButton>
                  ) : null}
                  <button
                    type="button"
                    title={order.delivered_cents ? "Close (short-ship the rest)" : "Cancel the order"}
                    aria-label="End order"
                    onClick={() => setEnding(order.delivered_cents ? "close" : "cancel")}
                    className={iconAction(actionIntentFromLabel(order.delivered_cents ? "Close" : "Cancel the order"))}
                  >
                    <Ban size={15} aria-hidden="true" />
                  </button>
                </>
              ) : null}
            </div>
          ) : null}
        </div>
        <ErrorNote message={error} />
        {order ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[880px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-charcoal/50">
                <tr>
                  <th className="pb-3 font-medium">Product</th>
                  <th className="pb-3 text-right font-medium">Ordered</th>
                  <th className="pb-3 text-right font-medium">Delivered</th>
                  <th className="pb-3 text-right font-medium">Reserved</th>
                  <th className="pb-3 text-right font-medium">Backordered</th>
                  <th className="pb-3 text-right font-medium">Unit price</th>
                  <th className="pb-3 text-right font-medium">Amount</th>
                </tr>
              </thead>
              <tbody>
                {order.lines.map((line) => (
                  <tr key={line.id} className="border-t border-line align-top">
                    <td className="py-3">
                      <span className="block font-medium">{line.product_name}</span>
                      <span className="block font-mono text-xs text-charcoal/50">
                        {line.sku}
                        {line.bin_location ? ` · Bin ${line.bin_location}` : ""}
                      </span>
                      {line.quantity_cancelled ? <span className="block text-xs text-charcoal/50">{line.quantity_cancelled} cancelled</span> : null}
                    </td>
                    <td className="py-3 text-right tabular-nums">{line.quantity_ordered}</td>
                    <td className="py-3 text-right tabular-nums">{line.quantity_delivered}</td>
                    <td className="py-3 text-right tabular-nums">{open ? Math.min(line.quantity_reserved, line.outstanding) : "—"}</td>
                    <td className={`py-3 text-right font-semibold tabular-nums ${line.backordered ? "text-accent" : "text-charcoal/40"}`}>
                      {line.backordered}
                      {line.backordered && line.available_now ? (
                        <span className="block text-xs font-normal text-charcoal/60">{line.available_now} free now</span>
                      ) : null}
                    </td>
                    <td className="py-3 text-right tabular-nums">
                      {formatMoney(line.unit_price_cents, order.currency)}
                      {line.unit_price_cents !== line.list_price_cents ? (
                        <span className="block text-xs text-charcoal/50 line-through">{formatMoney(line.list_price_cents, order.currency)}</span>
                      ) : null}
                    </td>
                    <td className="py-3 text-right font-semibold tabular-nums">{formatMoney(line.line_total_cents, order.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {order.notes ? <p className="mt-4 rounded-2xl bg-surface px-4 py-3 text-sm text-charcoal/70">{order.notes}</p> : null}
          </div>
        ) : null}
      </div>

      {order && (order.deliveries.length || currentPick) ? (
        <div className="rounded-card border border-line bg-white p-6">
          <h3 className="mb-4 text-lg font-semibold">Deliveries</h3>
          {currentPick ? (
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-surface px-4 py-3 text-sm">
              <span>
                <span className="font-mono text-xs font-semibold">{currentPick.number}</span> · pick{" "}
                {currentPick.lines.reduce((sum, line) => sum + line.quantity, 0)} units across {currentPick.lines.length} bins
              </span>
              <GhostButton onClick={() => void pdf(() => salesOrdersApi.pickListPdf(currentPick.id))}>Print pick list</GhostButton>
            </div>
          ) : null}
          <ul className="divide-y divide-line">
            {order.deliveries.map((note) => (
              <li key={note.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm">
                <div>
                  <span className="font-mono text-xs font-semibold">{note.number}</span>
                  <span className={`ml-2 rounded-full px-2 py-0.5 text-[11px] font-semibold ${note.status === "DELIVERED" ? "bg-surface ring-1 ring-line" : "bg-charcoal text-white"}`}>
                    {note.status === "DELIVERED" ? "Signed for" : "On the way"}
                  </span>
                  <span className="block text-xs text-charcoal/60">
                    {note.lines.reduce((sum, line) => sum + line.quantity, 0)} units · invoice {note.invoice_number ?? "—"}
                    {note.invoice_total_cents !== null ? ` · ${formatMoney(note.invoice_total_cents, order.currency)}` : ""}
                    {note.vehicle ? ` · ${note.vehicle}` : ""}
                  </span>
                  {note.status === "DELIVERED" ? (
                    <span className="block text-xs text-charcoal/60">
                      Received by {note.receiver_name} {note.delivered_at ? `on ${formatDate(note.delivered_at)}` : ""}
                    </span>
                  ) : null}
                </div>
                <div className="flex items-center gap-2">
                  {note.sale_id ? (
                    <GhostButton onClick={() => void pdf(() => salesOrdersApi.invoicePdf(note.sale_id ?? ""))}>Invoice</GhostButton>
                  ) : null}
                  <button type="button" title="Delivery note PDF" aria-label={`${note.number} PDF`} onClick={() => void pdf(() => salesOrdersApi.deliveryPdf(note.id))} className={iconAction("info")}>
                    <FileDown size={15} aria-hidden="true" />
                  </button>
                  {note.status === "DISPATCHED" ? (
                    <>
                      <Link to={`/deliveries/${note.id}`} title="Open on the driver's phone" aria-label="Driver page" className={iconAction("info")}>
                        <Smartphone size={15} aria-hidden="true" />
                      </Link>
                      <PrimaryButton onClick={() => setSigning(note)}>
                        <PenLine size={15} aria-hidden="true" className="-ml-1 mr-1.5" /> Proof of delivery
                      </PrimaryButton>
                    </>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {dispatching && order ? (
        <DispatchModal
          order={order}
          busy={busy}
          error={error}
          onClose={() => setDispatching(false)}
          onDispatch={async (body) => {
            if (
              await run(
                () => salesOrdersApi.dispatch(order.id, body),
                (next) => `${next.deliveries.at(-1)?.number ?? "Delivery"} dispatched and invoiced ${next.deliveries.at(-1)?.invoice_number ?? ""}.`,
              )
            ) {
              setDispatching(false);
            }
          }}
        />
      ) : null}
      {trimming && order ? (
        <CancelLinesModal
          order={order}
          busy={busy}
          onClose={() => setTrimming(false)}
          onSave={async (lines, reason) => {
            if (await run(() => salesOrdersApi.cancelLines(order.id, lines, reason), () => "Lines cancelled; their stock is released.")) {
              setTrimming(false);
            }
          }}
        />
      ) : null}
      {ending && order ? (
        <ReasonModal
          title={ending === "close" ? `Close ${order.number}?` : `Cancel ${order.number}?`}
          subtitle={
            ending === "close"
              ? "What was delivered stays invoiced; the rest is cancelled and its reserved stock released."
              : "Nothing was delivered. Every reservation is released."
          }
          action={ending === "close" ? "Close order" : "Cancel order"}
          busy={busy}
          onClose={() => setEnding(null)}
          onSave={async (reason) => {
            const work = ending === "close" ? salesOrdersApi.close : salesOrdersApi.cancel;
            if (await run(() => work(order.id, reason), (next) => `${next.number} ${next.status === "CLOSED" ? "closed" : "cancelled"}.`)) {
              setEnding(null);
            }
          }}
        />
      ) : null}
      {signing ? (
        <DeliverModal
          note={signing}
          onClose={() => setSigning(null)}
          onDone={(note) => {
            setSigning(null);
            setToast(`${note.number} signed for by ${note.receiver_name}.`);
            void load();
          }}
        />
      ) : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}

function DispatchModal({
  order,
  busy,
  error,
  onClose,
  onDispatch,
}: {
  order: SalesOrder;
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onDispatch: (body: Parameters<typeof salesOrdersApi.dispatch>[1]) => Promise<void>;
}) {
  const ready = order.lines.filter((line) => Math.min(line.quantity_reserved, line.outstanding) > 0);
  const [quantities, setQuantities] = useState<Record<string, string>>(
    Object.fromEntries(ready.map((line) => [line.id, String(Math.min(line.quantity_reserved, line.outstanding))])),
  );
  const [serials, setSerials] = useState<Record<string, string>>({});
  const [vehicle, setVehicle] = useState("");
  const wholesale = order.customer_type === "WHOLESALE";
  const [method, setMethod] = useState<PaymentMethod>(wholesale ? "on_account" : "transfer");
  const [local, setLocal] = useState<string | null>(null);

  const submit = () => {
    const lines = [];
    for (const line of ready) {
      const quantity = Number(quantities[line.id] ?? "0");
      if (!quantity) continue;
      if (!Number.isInteger(quantity) || quantity > line.outstanding) {
        return setLocal(`${line.product_name}: at most ${line.outstanding} left to deliver.`);
      }
      const scanned = (serials[line.id] ?? "").split(/[\s,;]+/).map((value) => value.trim()).filter(Boolean);
      if (line.is_serialized && scanned.length && scanned.length !== quantity) {
        return setLocal(`Scan ${quantity} IMEIs for ${line.product_name}, or leave it empty to assign free units.`);
      }
      lines.push({ order_line_id: line.id, quantity, serials: scanned });
    }
    if (!lines.length) return setLocal("Enter what goes on this delivery.");
    setLocal(null);
    void onDispatch({ lines, vehicle: vehicle.trim() || null, payment_method: method });
  };

  const methods: { value: PaymentMethod; label: string }[] = [
    ...(wholesale ? [{ value: "on_account" as PaymentMethod, label: "Invoice on account" }] : []),
    { value: "transfer", label: "Bank transfer" },
    { value: "cash", label: "Cash on delivery" },
    { value: "card", label: "Card" },
  ];

  return (
    <Modal
      width="lg"
      title={`Dispatch from ${order.number}`}
      subtitle="Only what leaves now is invoiced. Whatever stays behind remains on the order."
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={submit}>
            {busy ? "Dispatching…" : "Dispatch and invoice"}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        {ready.map((line) => (
          <div key={line.id} className="rounded-2xl border border-line p-4">
            <div className="flex items-center justify-between gap-3">
              <span>
                <span className="block font-medium">{line.product_name}</span>
                <span className="block text-xs text-charcoal/50">
                  {Math.min(line.quantity_reserved, line.outstanding)} reserved · {line.outstanding} outstanding
                  {line.bin_location ? ` · Bin ${line.bin_location}` : ""}
                </span>
              </span>
              <input
                aria-label={`Deliver ${line.product_name}`}
                inputMode="numeric"
                value={quantities[line.id] ?? ""}
                onChange={(event) => setQuantities((current) => ({ ...current, [line.id]: event.target.value.replace(/[^\d]/g, "") }))}
                className="w-24 rounded-xl border border-line bg-surface px-3 py-2 text-right font-semibold tabular-nums focus:border-accent focus:outline-none"
              />
            </div>
            {line.is_serialized ? (
              <textarea
                aria-label={`IMEIs for ${line.product_name}`}
                rows={2}
                value={serials[line.id] ?? ""}
                onChange={(event) => setSerials((current) => ({ ...current, [line.id]: event.target.value }))}
                placeholder="Scan IMEIs, or leave empty to assign free units"
                className="mt-3 w-full rounded-xl border border-transparent bg-surface px-3 py-2 font-mono text-xs focus:border-accent focus:bg-white focus:outline-none"
              />
            ) : null}
          </div>
        ))}
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="Vehicle (optional)" value={vehicle} maxLength={40} onChange={(event) => setVehicle(event.target.value)} />
          <SelectField label="Payment" value={method} options={methods} onChange={setMethod} />
        </div>
      </div>
      <ErrorNote message={local ?? error} />
    </Modal>
  );
}

function CancelLinesModal({
  order,
  busy,
  onClose,
  onSave,
}: {
  order: SalesOrder;
  busy: boolean;
  onClose: () => void;
  onSave: (lines: { order_line_id: string; quantity: number }[], reason: string) => Promise<void>;
}) {
  const [quantities, setQuantities] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");
  const [local, setLocal] = useState<string | null>(null);
  const lines = order.lines.filter((line) => line.outstanding > 0);

  const submit = () => {
    const picked = lines
      .map((line) => ({ order_line_id: line.id, quantity: Number(quantities[line.id] ?? "0"), max: line.outstanding }))
      .filter((line) => line.quantity > 0);
    if (!picked.length) return setLocal("Enter how many to cancel on at least one line.");
    if (picked.some((line) => line.quantity > line.max)) return setLocal("You can only cancel what is still outstanding.");
    if (reason.trim().length < 3) return setLocal("Give a reason.");
    void onSave(
      picked.map(({ order_line_id, quantity }) => ({ order_line_id, quantity })),
      reason.trim(),
    );
  };

  return (
    <Modal
      title={`Cancel lines on ${order.number}`}
      subtitle="Cancelled units come off the order and release any stock reserved for them."
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Back</GhostButton>
          <PrimaryButton disabled={busy} onClick={submit}>
            Cancel units
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-3">
        {lines.map((line) => (
          <div key={line.id} className="flex items-center justify-between gap-3 text-sm">
            <span>
              <span className="block font-medium">{line.product_name}</span>
              <span className="block text-xs text-charcoal/50">{line.outstanding} outstanding</span>
            </span>
            <input
              aria-label={`Cancel ${line.product_name}`}
              inputMode="numeric"
              value={quantities[line.id] ?? ""}
              placeholder="0"
              onChange={(event) => setQuantities((current) => ({ ...current, [line.id]: event.target.value.replace(/[^\d]/g, "") }))}
              className="w-20 rounded-xl border border-line bg-surface px-3 py-1.5 text-right tabular-nums focus:border-accent focus:outline-none"
            />
          </div>
        ))}
        <TextField label="Reason" value={reason} maxLength={255} onChange={(event) => setReason(event.target.value)} />
      </div>
      <ErrorNote message={local} />
    </Modal>
  );
}

function ReasonModal({
  title,
  subtitle,
  action,
  busy,
  onClose,
  onSave,
}: {
  title: string;
  subtitle: string;
  action: string;
  busy: boolean;
  onClose: () => void;
  onSave: (reason: string) => Promise<void>;
}) {
  const [code, setCode] = useState("changed_mind");
  const [reason, setReason] = useState("");
  return (
    <Modal
      title={title}
      subtitle={subtitle}
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Back</GhostButton>
          <PrimaryButton
            disabled={busy || reason.trim().length < 3}
            onClick={() => void onSave(`[${code}] ${reason.trim()}`)}
          >
            {action}
          </PrimaryButton>
        </>
      }
    >
      <label className="mb-3 block text-sm font-medium">
        Why
        <select
          value={code}
          onChange={(event) => setCode(event.target.value)}
          className="mt-1.5 h-11 w-full rounded-xl border border-line bg-white px-3 text-sm"
        >
          <option value="changed_mind">Customer changed mind</option>
          <option value="duplicate">Duplicate order</option>
          <option value="wrong_item">Incorrect product</option>
          <option value="wrong_quantity">Incorrect quantity</option>
          <option value="price">Price or promotion</option>
          <option value="stock">Stock unavailable</option>
          <option value="payment">Payment failure</option>
          <option value="delivery">Delivery issue</option>
          <option value="entry_mistake">Employee mistake</option>
          <option value="operational">Operational issue</option>
          <option value="other">Other</option>
        </select>
      </label>
      <TextField label="Explanation" value={reason} maxLength={220} onChange={(event) => setReason(event.target.value)} />
    </Modal>
  );
}

export function DeliverForm({ note, onDone }: { note: DeliveryNote; onDone: (note: DeliveryNote) => void }) {
  const [receiver, setReceiver] = useState("");
  const [signature, setSignature] = useState<string | null>(null);
  const [remark, setRemark] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!receiver.trim()) return setError("Enter who received the goods.");
    setBusy(true);
    setError(null);
    try {
      onDone(await salesOrdersApi.deliver(note.id, { receiver_name: receiver.trim(), signature, note: remark.trim() || null }));
    } catch (caught) {
      setError(errorMessage(caught, "Could not record the delivery."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <ul className="rounded-2xl bg-surface px-4 py-3 text-sm">
        {note.lines.map((line) => (
          <li key={line.order_line_id} className="flex justify-between gap-3 py-0.5">
            <span>{line.product_name}</span>
            <span className="font-semibold tabular-nums">× {line.quantity}</span>
          </li>
        ))}
      </ul>
      <TextField label="Received by" value={receiver} maxLength={120} onChange={(event) => setReceiver(event.target.value)} />
      <SignaturePad onChange={setSignature} />
      <TextField label="Note (optional)" value={remark} maxLength={255} placeholder="e.g. 2 cartons dented" onChange={(event) => setRemark(event.target.value)} />
      <ErrorNote message={error} />
      <div className="grid">
        <PrimaryButton disabled={busy} onClick={() => void submit()}>
          {busy ? "Saving…" : "Confirm delivery"}
        </PrimaryButton>
      </div>
    </div>
  );
}

function DeliverModal({ note, onClose, onDone }: { note: DeliveryNote; onClose: () => void; onDone: (note: DeliveryNote) => void }) {
  return (
    <Modal title={`Proof of delivery · ${note.number}`} subtitle={note.delivery_address ?? note.customer_name} onClose={onClose}>
      <DeliverForm note={note} onDone={onDone} />
    </Modal>
  );
}
