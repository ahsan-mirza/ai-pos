import {
  Capability,
  Permission,
  comboDelta,
  comboSummary,
  formatMoney,
  modifierDelta,
  modifierSummary,
  type ComboChoice,
  unpaidItems,
  type DeliveryChannel,
  type DiningTable,
  type Floor,
  type ModifierChoice,
  ORDER_PROGRESS_LABEL,
  type KitchenStatus,
  type Order,
  type OrderItem,
  type OrderProgress,
  type ProductUpsert,
  type ServiceType,
} from "@ai-pos/shared-types";
import { FloorTableCard, floorTableGridClass } from "../../components/FloorTableCard";
import { ChefHat, CreditCard, Merge, MoveRight, Plus, Receipt, Search, Send, Split, Truck, Users, UtensilsCrossed, X } from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { ManagerApprovalModal } from "../../components/ManagerApprovalModal";
import { DrawerHeader } from "../../components/shell/Drawer";
import { PageFrame } from "../../components/shell/RegisterShell";
import { useShell } from "../../components/shell/ShellContext";
import { ui } from "../../components/shell/tokens";
import { useCapabilities } from "../../lib/capabilities";
import type { CashierSession } from "../auth/session";
import { loadCatalog, seedProducts, useCatalogUpdates } from "../checkout/catalog";
import { activeStore, useBusinessCurrency } from "../checkout/currency";
import { combosFor, groupsFor, refreshMenu, useMenu } from "../checkout/menu";
import { ComboBuilderModal } from "../checkout/ComboBuilderModal";
import { ModifierPickerModal } from "../checkout/ModifierPickerModal";
import { QuantityModal } from "../checkout/QuantityModal";
import { verifyManager } from "../checkout/wholesaleClient";
import { printKitchenTickets } from "./kitchenPrint";
import { SplitChecksModal } from "./SplitChecksModal";
import { IncomingDeliveries, KeyInDeliveryModal } from "./IncomingDeliveries";
import { GuestSuggestions, suggestsForGuests } from "./GuestSuggestions";
import { OrderRequestError, channelsApi, ordersApi, queueOfflineOrder } from "./ordersClient";
import { listenForTableEvents } from "./tableSync";
import { startSettlement } from "./settlement";

const POLL_MS = 3000;

const KITCHEN_LABEL: Record<string, string> = {
  new: ORDER_PROGRESS_LABEL.preparing,
  preparing: ORDER_PROGRESS_LABEL.preparing,
  ready: ORDER_PROGRESS_LABEL.ready,
  bumped: ORDER_PROGRESS_LABEL.completed,
};

/** The most urgent kitchen phase on a ticket: a ready plate beats a line that is still cooking. */
function orderPhase(order: Order | undefined): OrderProgress | null {
  if (!order) return null;
  const live = order.items.filter((item) => !item.voided_at && (item.sent_at || item.kitchen_status));
  if (live.length === 0) return null;
  if (live.every((item) => item.kitchen_status === "bumped")) return "completed";
  if (live.some((item) => item.kitchen_status === "ready")) return "ready";
  return "preparing";
}

function minutesSince(iso: string | null): number {
  return iso ? Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60_000)) : 0;
}

function GuestCountModal({
  table,
  onClose,
  onConfirm,
}: {
  table: DiningTable;
  onClose: () => void;
  onConfirm: (covers: number) => void;
}) {
  const titleId = useId();
  const [covers, setCovers] = useState(Math.min(2, Math.max(1, table.seats)));
  const seats = Math.max(1, table.seats);
  const choices = Array.from({ length: Math.min(seats, 12) }, (_, index) => index + 1);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" role="presentation">
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="modal-card max-w-md">
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-charcoal text-white dark:bg-zinc-100 dark:text-zinc-900">
            <Users size={20} aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-xl font-semibold">
              Seat {table.label}
            </h2>
            <p className="text-sm text-charcoal/60 dark:text-zinc-400">
              How many guests? This table seats {table.seats}.
            </p>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} className="modal-close">
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <form
          className="mt-5 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (covers >= 1 && covers <= seats) onConfirm(covers);
          }}
        >
          <div className="flex flex-wrap gap-2" role="group" aria-label="Guest count">
            {choices.map((count) => (
              <button
                key={count}
                type="button"
                aria-pressed={covers === count}
                onClick={() => setCovers(count)}
                className={`h-12 min-w-12 rounded-2xl px-3 text-base font-semibold tabular-nums ${
                  covers === count ? "bg-primary text-white" : "bg-zinc-100 text-zinc-800 dark:bg-white/10 dark:text-zinc-100"
                }`}
              >
                {count}
              </button>
            ))}
          </div>
          {seats > 12 ? (
            <label className="block text-sm font-medium" htmlFor="guest-count">
              Guests
              <input
                id="guest-count"
                inputMode="numeric"
                autoComplete="off"
                value={covers}
                onChange={(event) => {
                  const next = Number(event.target.value.replace(/\D/g, ""));
                  if (Number.isFinite(next)) setCovers(Math.min(seats, next));
                }}
                className="modal-input mt-1.5 text-lg font-semibold tabular-nums"
              />
            </label>
          ) : null}
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="modal-cancel">
              Cancel
            </button>
            <button type="submit" className="modal-save" disabled={covers < 1}>
              Seat {covers} {covers === 1 ? "guest" : "guests"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function lineLabel(item: OrderItem): string {
  const extras = [comboSummary(item.components), modifierSummary(item.modifiers)].filter(Boolean).join(" · ");
  return extras ? `${item.product_name} · ${extras}` : item.product_name;
}

interface DraftLine {
  id: string;
  product: ProductUpsert;
  quantity: number;
  modifiers: ModifierChoice[];
  components: ComboChoice[];
  seat: number | null;
}

/** Restaurant floor: tables and open tabs shared by every register, with kitchen sending, voids, merges and pay. */
export function OrdersPage({ session }: { session: CashierSession }) {
  const { navigate } = useShell();
  const currency = useBusinessCurrency();
  const capabilities = useCapabilities();
  const tablesOn = capabilities.enabled.has(Capability.Tables);
  const menu = useMenu();
  const storeId = activeStore().id;
  const userId = session.user.id;

  const [orders, setOrders] = useState<Order[]>([]);
  const [floor, setFloor] = useState<Floor | null>(null);
  const [areaId, setAreaId] = useState<string>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [products, setProducts] = useState<ProductUpsert[]>(seedProducts);
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState<DraftLine[]>([]);
  const [seat, setSeat] = useState<number | null>(null);
  const [modifierFor, setModifierFor] = useState<ProductUpsert | null>(null);
  const [comboFor, setComboFor] = useState<ProductUpsert | null>(null);
  const [quantityFor, setQuantityFor] = useState<ProductUpsert | null>(null);
  const [voiding, setVoiding] = useState<{ item: OrderItem | null; reason: string } | null>(null);
  const [mergeFrom, setMergeFrom] = useState<Order | null>(null);
  const [moving, setMoving] = useState<Order | null>(null);
  const [splitting, setSplitting] = useState(false);
  const splitOn = capabilities.enabled.has(Capability.SplitBills);
  const channelsOn = capabilities.enabled.has(Capability.DeliveryChannels);
  const [channels, setChannels] = useState<DeliveryChannel[]>([]);
  const [keyingIn, setKeyingIn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [seating, setSeating] = useState<DiningTable | null>(null);

  const selected = orders.find((order) => order.id === selectedId) ?? null;

  const refresh = useCallback(async () => {
    try {
      const [next, nextFloor] = await Promise.all([ordersApi.list(storeId), tablesOn ? ordersApi.floor(storeId) : Promise.resolve(null)]);
      setOrders(next);
      setFloor(nextFloor);
      setOffline(false);
    } catch (caught) {
      if (caught instanceof OrderRequestError && caught.offline) setOffline(true);
      else setNotice(caught instanceof Error ? caught.message : String(caught));
    }
  }, [storeId, tablesOn]);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), POLL_MS);
    const stopLive = listenForTableEvents(storeId, (event) => {
      if (
        event.message &&
        (event.type === "KDS_ITEM_READY" || event.type === "ORDER_STATUS_CHANGED")
      ) {
        setNotice(event.message);
      }
      if (event.type === "ORDER_STATUS_CHANGED" && event.order_id && event.kitchen_status) {
        const ids = new Set(event.item_ids ?? []);
        setOrders((current) =>
          current.map((order) =>
            order.id !== event.order_id
              ? order
              : {
                  ...order,
                  items: order.items.map((item) =>
                    ids.has(item.id)
                      ? { ...item, kitchen_status: event.kitchen_status as KitchenStatus, sent_at: item.sent_at ?? event.updated_at ?? null }
                      : item,
                  ),
                },
          ),
        );
      }
      if (
        event.type === "TABLE_ITEMS_ADDED" ||
        event.type === "TABLE_SESSION_CLOSED" ||
        event.type === "KDS_ITEM_READY" ||
        event.type === "ORDER_STATUS_CHANGED" ||
        event.type === "BILL_REQUESTED"
      ) {
        void refresh();
      }
    });
    return () => {
      stopLive();
      window.clearInterval(timer);
    };
  }, [refresh, storeId]);

  const refreshCatalog = useCallback(() => {
    void loadCatalog().then((catalog) => setProducts(catalog.products));
  }, []);
  useCatalogUpdates(refreshCatalog);

  useEffect(() => {
    refreshCatalog();
    if (capabilities.enabled.has(Capability.MenuModifiers)) void refreshMenu();
  }, [capabilities.enabled, refreshCatalog]);

  useEffect(() => {
    if (channelsOn) void channelsApi.list().then(setChannels).catch(() => setChannels([]));
  }, [channelsOn]);

  useEffect(() => {
    if (floor && areaId !== "all" && !floor.areas.some((area) => area.id === areaId)) setAreaId("all");
  }, [floor, areaId]);

  /** Runs a write; a stale order refreshes and asks the cashier to try again. */
  const write = useCallback(
    async (action: () => Promise<Order>, success?: string) => {
      setBusy(true);
      try {
        const order = await action();
        setOrders((current) => [...current.filter((item) => item.id !== order.id), order].filter((item) => item.status === "OPEN"));
        setSelectedId(order.status === "OPEN" ? order.id : null);
        if (success) setNotice(success);
        void refresh();
        return order;
      } catch (caught) {
        if (caught instanceof OrderRequestError && caught.stale) {
          await refresh();
          setNotice("Another register changed this order. It is refreshed: check it and try again.");
        } else {
          setNotice(caught instanceof Error ? caught.message : String(caught));
        }
        return null;
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );

  async function openTab(serviceType: ServiceType, table: DiningTable | null, covers = 0) {
    const id = crypto.randomUUID();
    const input = { storeId, userId, serviceType, tableId: table?.id ?? null, covers };
    setBusy(true);
    try {
      const order = await ordersApi.create(input, id);
      setOrders((current) => [...current.filter((item) => item.id !== order.id), order]);
      setSelectedId(order.id);
      setNotice(table ? `Table ${table.label} seated.` : "New tab opened.");
    } catch (caught) {
      if (caught instanceof OrderRequestError && caught.offline) {
        await queueOfflineOrder({ ...input, id }, false);
        setNotice("Offline: the tab is saved on this register and syncs when the connection is back.");
      } else {
        setNotice(caught instanceof Error ? caught.message : String(caught));
      }
    } finally {
      setBusy(false);
      void refresh();
    }
  }

  function addDraft(product: ProductUpsert, modifiers: ModifierChoice[], components: ComboChoice[] = [], quantity = 1) {
    setDraft((current) => {
      const plain = modifiers.length === 0 && components.length === 0;
      const same = plain
        ? current.find(
            (line) =>
              line.product.id === product.id && line.seat === seat && line.modifiers.length === 0 && line.components.length === 0,
          )
        : undefined;
      if (same) return current.map((line) => (line === same ? { ...line, quantity: line.quantity + quantity } : line));
      return [...current, { id: crypto.randomUUID(), product, quantity, modifiers, components, seat }];
    });
  }

  function pick(product: ProductUpsert) {
    if (product.is_serialized || product.sold_by_weight) {
      setNotice(`${product.name} is sold at checkout, not on a tab.`);
      return;
    }
    if (combosFor(menu, product.id).length > 0) setComboFor(product);
    else if (groupsFor(menu, product.id).length > 0) setModifierFor(product);
    else setQuantityFor(product);
  }

  async function addAndMaybeSend(send: boolean) {
    if (selected === null || draft.length === 0) return;
    const items = draft.map((line) => ({
      id: line.id,
      product_id: line.product.id,
      quantity: line.quantity,
      unit_price_cents: line.product.price_cents + modifierDelta(line.modifiers) + comboDelta(line.components),
      modifiers: line.modifiers,
      ...(line.components.length ? { components: line.components } : {}),
      seat: line.seat,
    }));
    let added: Order | null = null;
    try {
      added = await ordersApi.addItems(selected, userId, items);
    } catch (caught) {
      if (caught instanceof OrderRequestError && caught.offline) {
        await queueOfflineOrder(
          { id: selected.id, storeId, userId, serviceType: selected.service_type, tableId: selected.table_id, covers: selected.covers, items, openedAt: selected.opened_at },
          send,
        );
        setDraft([]);
        setNotice("Offline: the lines are saved on this register and reach the kitchen when the connection is back.");
        return;
      }
      if (caught instanceof OrderRequestError && caught.stale) {
        await refresh();
        setNotice("Another register changed this order. It is refreshed: add the lines again.");
        return;
      }
      setNotice(caught instanceof Error ? caught.message : String(caught));
      return;
    }
    setDraft([]);
    const fresh = added;
    if (send) await sendToKitchen(fresh);
    else await write(async () => fresh, `${items.length} line${items.length === 1 ? "" : "s"} added.`);
  }

  async function sendToKitchen(order: Order) {
    const sent = await write(() => ordersApi.send(order, userId), "Sent to the kitchen.");
    if (sent && capabilities.enabled.has(Capability.Kds)) void printKitchenTickets(sent.id);
  }

  function pay(itemIds: string[], label: string, guests?: number) {
    if (selected === null || itemIds.length === 0) return;
    startSettlement({ order: selected, itemIds, label, guests });
    navigate("checkout");
  }

  async function keyIn(channelId: string, externalRef: string, customerName: string | null) {
    setKeyingIn(false);
    await write(() => channelsApi.keyIn(channelId, externalRef, userId, customerName), "Delivery order opened. Add its items, then send.");
  }

  const visibleTables =
    floor === null
      ? []
      : (areaId === "all" ? floor.areas : floor.areas.filter((item) => item.id === areaId)).flatMap((item) =>
          item.tables.filter((table) => table.is_active),
        );
  const occupiedTables = visibleTables.filter((table) => table.status !== "free").length;
  const incoming = orders.filter((order) => order.channel_status === "PENDING");
  const tabs = orders.filter((order) => order.table_id === null && order.channel_status !== "PENDING");
  const unpaid = selected ? unpaidItems(selected) : [];
  const seats = [...new Set(unpaid.map((item) => item.seat).filter((value): value is number => value !== null))].sort((a, b) => a - b);
  const hits = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const sellable = products.filter((product) => !product.is_serialized && !product.sold_by_weight);
    return (needle ? sellable.filter((product) => `${product.name} ${product.sku} ${product.category}`.toLowerCase().includes(needle)) : sellable).slice(0, 24);
  }, [products, query]);

  return (
    <PageFrame
      title="Orders & Tables"
      sync={{ tone: offline ? "offline" : "live", label: offline ? "Offline" : "Live", title: offline ? "Orders sync when the connection returns." : "Shared with every register." }}
      actions={
        <div className="flex gap-2">
          <button type="button" className={`${ui.secondaryAction} h-10 px-3`} disabled={busy} onClick={() => void openTab("TAKEAWAY", null)}>
            <Plus size={16} aria-hidden="true" /> Takeaway tab
          </button>
          {!tablesOn ? (
            <button type="button" className={`${ui.secondaryAction} h-10 px-3`} disabled={busy} onClick={() => void openTab("DINE_IN", null)}>
              <UtensilsCrossed size={16} aria-hidden="true" /> Dine-in tab
            </button>
          ) : null}
          {channelsOn ? (
            <button type="button" className={`${ui.secondaryAction} h-10 px-3`} disabled={busy} onClick={() => setKeyingIn(true)}>
              <Truck size={16} aria-hidden="true" /> Delivery order
            </button>
          ) : null}
        </div>
      }
      drawer={
        <aside aria-label="Order" className="hidden min-h-0 flex-col border-l border-zinc-200 bg-white lg:flex lg:w-[420px] dark:border-white/10 dark:bg-charcoal">
          {selected === null ? (
            <div className="flex flex-1 flex-col items-center justify-center p-8 text-center text-sm text-zinc-500 dark:text-white/50">
              <UtensilsCrossed size={28} aria-hidden="true" />
              <p className="mt-3 font-semibold text-zinc-700 dark:text-white/80">Pick a table or a tab</p>
              <p className="mt-1">Seat a free table, or open a takeaway tab, then add items and send them to the kitchen.</p>
            </div>
          ) : (
            <>
              <DrawerHeader title={selected.table_label ? `Table ${selected.table_label}` : selected.name || `Tab #${selected.number}`} count={`#${selected.number}`}>
                <button type="button" aria-label="Close order" onClick={() => setSelectedId(null)} className="flex h-9 w-9 items-center justify-center rounded-full hover:bg-zinc-100 dark:hover:bg-white/10">
                  <X size={18} aria-hidden="true" />
                </button>
              </DrawerHeader>
              <div className="custom-scrollbar min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
                <p className="flex flex-wrap items-center gap-2 text-xs text-zinc-500 dark:text-white/50">
                  <span className="inline-flex items-center gap-1"><Users size={13} aria-hidden="true" /> {selected.covers} covers</span>
                  <span>· open {minutesSince(selected.opened_at)} min</span>
                  {selected.channel_name ? <span className="inline-flex items-center gap-1 text-primary"><Truck size={13} aria-hidden="true" /> {selected.channel_name} {selected.external_ref}</span> : null}
                  {selected.bill_requested_at ? <span className="font-semibold text-amber-600">Bill requested</span> : null}
                </p>
                <ul className="space-y-1.5">
                  {selected.items.map((item) => (
                    <li key={item.id} className={`rounded-2xl border px-3 py-2 text-sm ${item.voided_at ? "border-dashed border-zinc-200 opacity-50 dark:border-white/10" : "border-zinc-200 bg-zinc-50 dark:border-white/[0.06] dark:bg-[#1A191D]"}`}>
                      <div className="flex items-baseline justify-between gap-2">
                        <span className={`min-w-0 truncate font-semibold ${item.voided_at ? "line-through" : ""}`}>
                          {item.quantity} × {lineLabel(item)}
                        </span>
                        <span className="shrink-0 font-bold tabular-nums">{formatMoney(item.unit_price_cents * item.quantity, currency)}</span>
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-zinc-500 dark:text-white/50">
                        {item.seat ? <span className="rounded-full bg-zinc-200/70 px-1.5 dark:bg-white/10">Seat {item.seat}</span> : null}
                        {item.paid_sale_id ? <span className="rounded-full bg-emerald-500/15 px-1.5 text-emerald-700 dark:text-emerald-300">Paid</span> : null}
                        {item.voided_at ? <span>Voided: {item.void_reason}</span> : item.sent_at ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-1.5 text-primary">
                            <ChefHat size={11} aria-hidden="true" /> {KITCHEN_LABEL[item.kitchen_status ?? "new"] ?? "In kitchen"}
                          </span>
                        ) : <span className="rounded-full bg-zinc-200/70 px-1.5 dark:bg-white/10">Not sent</span>}
                        {!item.voided_at && !item.paid_sale_id ? (
                          <button type="button" disabled={busy} onClick={() => setVoiding({ item, reason: "" })} className="ml-auto font-semibold text-zinc-500 hover:text-red-600">
                            Void
                          </button>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>

                {draft.length > 0 ? (
                  <div className="rounded-2xl border border-primary/40 p-2">
                    <p className="px-1 text-[11px] font-semibold uppercase tracking-wide text-primary">Adding</p>
                    <ul className="mt-1 space-y-1 text-sm">
                      {draft.map((line) => (
                        <li key={line.id} className="flex items-center justify-between gap-2 px-1">
                          <span className="min-w-0 truncate">
                            {line.quantity} × {line.product.name}
                            {line.components.length ? ` · ${comboSummary(line.components)}` : ""}
                            {line.modifiers.length ? ` · ${modifierSummary(line.modifiers)}` : ""}
                            {line.seat ? ` · seat ${line.seat}` : ""}
                          </span>
                          <button type="button" aria-label={`Remove ${line.product.name}`} onClick={() => setDraft(draft.filter((item) => item.id !== line.id))} className="text-zinc-400 hover:text-red-600">
                            <X size={14} aria-hidden="true" />
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                <div className="flex items-center gap-1.5 text-[11px] font-semibold">
                  <span className="text-zinc-500 dark:text-white/50">Seat</span>
                  {[null, 1, 2, 3, 4, 5, 6].map((value) => (
                    <button key={value ?? "all"} type="button" aria-pressed={seat === value} onClick={() => setSeat(value)}
                      className={`h-7 min-w-7 rounded-full px-2 ${seat === value ? "bg-primary text-white" : "bg-zinc-200/70 dark:bg-white/10"}`}>
                      {value ?? "—"}
                    </button>
                  ))}
                </div>
                <label className="relative block">
                  <span className="sr-only">Find a menu item</span>
                  <Search size={15} aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
                  <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find a menu item"
                    className="h-10 w-full rounded-2xl border border-zinc-200 bg-white pl-9 pr-3 text-sm focus:border-primary focus:outline-none dark:border-white/10 dark:bg-zinc-900/60" />
                </label>
                <div className="grid grid-cols-2 gap-1.5">
                  {hits.map((product) => (
                    <button key={product.id} type="button" disabled={busy} onClick={() => pick(product)}
                      className="rounded-2xl border border-zinc-200 px-2.5 py-2 text-left text-xs hover:border-primary dark:border-white/10">
                      <span className="block truncate font-semibold">{product.name}</span>
                      <span className="block tabular-nums text-zinc-500 dark:text-white/50">{formatMoney(product.price_cents, currency)}</span>
                    </button>
                  ))}
                </div>
              </div>
              <div className="shrink-0 space-y-2 border-t border-zinc-200 px-4 py-3 dark:border-white/10">
                {suggestsForGuests(capabilities.profile) ? (
                  <GuestSuggestions
                    storeId={storeId}
                    customerId={selected.customer_id}
                    productIds={[
                      ...selected.items.filter((item) => item.voided_at === null).map((item) => item.product_id),
                      ...draft.map((line) => line.product.id),
                    ]}
                    disabled={busy}
                    onAdd={(suggestion) => {
                      const delta = suggestion.modifiers.reduce((sum, choice) => sum + choice.price_delta_cents, 0);
                      void write(
                        () =>
                          ordersApi.addItems(selected, userId, [
                            {
                              id: crypto.randomUUID(),
                              product_id: suggestion.product_id,
                              quantity: 1,
                              unit_price_cents: suggestion.price_cents + delta,
                              modifiers: suggestion.modifiers,
                              ...(seat !== null ? { seat } : {}),
                            },
                          ]),
                        `${suggestion.name} added.`,
                      );
                    }}
                  />
                ) : null}
                <p className="flex items-baseline justify-between text-sm">
                  <span className="font-semibold">Open to pay</span>
                  <span className="text-2xl font-bold tabular-nums text-primary">{formatMoney(selected.open_cents, currency)}</span>
                </p>
                <div className="grid grid-cols-3 gap-2">
                  <button type="button" disabled={busy || draft.length === 0} onClick={() => void addAndMaybeSend(false)} className={`${ui.secondaryAction} h-11 rounded-2xl text-xs`}>
                    <Plus size={15} aria-hidden="true" /> Add
                  </button>
                  <button type="button" disabled={busy || (draft.length === 0 && !selected.items.some((item) => !item.sent_at && !item.voided_at))}
                    onClick={() => (draft.length > 0 ? void addAndMaybeSend(true) : void sendToKitchen(selected))}
                    className={`${ui.secondaryAction} h-11 rounded-2xl text-xs`}>
                    <Send size={15} aria-hidden="true" /> Send
                  </button>
                  <button type="button" disabled={busy || unpaid.length === 0} onClick={() => void write(() => ordersApi.bill(selected, userId), "Bill requested.")} className={`${ui.secondaryAction} h-11 rounded-2xl text-xs`}>
                    <Receipt size={15} aria-hidden="true" /> Bill
                  </button>
                </div>
                {splitOn && seats.length > 1 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {seats.map((value) => (
                      <button key={value} type="button" onClick={() => pay(unpaid.filter((item) => item.seat === value).map((item) => item.id), `seat ${value} of #${selected.number}`)}
                        className="h-8 rounded-full bg-zinc-200/70 px-3 text-xs font-semibold dark:bg-white/10">
                        Pay seat {value}
                      </button>
                    ))}
                  </div>
                ) : null}
                <div className="flex gap-2">
                  {tablesOn ? (
                    <button type="button" disabled={busy} onClick={() => setMoving(selected)} className={`${ui.secondaryAction} h-12 w-14 shrink-0 flex-col rounded-2xl text-[10px]`}>
                      <MoveRight size={16} aria-hidden="true" /> Move
                    </button>
                  ) : null}
                  {orders.length > 1 ? (
                    <button type="button" disabled={busy} onClick={() => setMergeFrom(selected)} className={`${ui.secondaryAction} h-12 w-14 shrink-0 flex-col rounded-2xl text-[10px]`}>
                      <Merge size={16} aria-hidden="true" /> Merge
                    </button>
                  ) : null}
                  {splitOn ? (
                    <button type="button" disabled={busy || unpaid.length === 0} onClick={() => setSplitting(true)} className={`${ui.secondaryAction} h-12 w-14 shrink-0 flex-col rounded-2xl text-[10px]`}>
                      <Split size={16} aria-hidden="true" /> Split
                    </button>
                  ) : null}
                  <button type="button" disabled={busy || unpaid.length === 0} onClick={() => pay(unpaid.map((item) => item.id), `order #${selected.number}`)} className={`${ui.primaryAction} h-12 flex-1 rounded-full`}>
                    <CreditCard size={18} aria-hidden="true" /> {selected.table_id ? "Pay & Settle Table" : "Pay"} {formatMoney(selected.open_cents, currency)}
                  </button>
                </div>
              </div>
            </>
          )}
        </aside>
      }
    >
      <div className="space-y-4 p-5">
        {notice ? (
          <p role="status" className="rounded-2xl bg-zinc-100 px-4 py-2.5 text-sm dark:bg-white/[0.06]">
            {notice}
          </p>
        ) : null}
        {channelsOn ? (
          <IncomingDeliveries
            orders={incoming}
            currency={currency}
            busy={busy}
            onAccept={(order, minutes) => void write(() => channelsApi.accept(order, userId, minutes), `#${order.number} accepted: ready in ${minutes} min.`).then((done) => {
              if (done && capabilities.enabled.has(Capability.Kds)) void printKitchenTickets(done.id);
            })}
            onReject={(order, reason) => void write(() => channelsApi.reject(order, userId, reason), `#${order.number} rejected.`)}
          />
        ) : null}
        {moving ? (
          <p className="rounded-2xl border border-sky-400/50 bg-sky-500/10 px-4 py-2.5 text-sm">
            Move #{moving.number} to which free table?{" "}
            <button type="button" className="font-semibold underline" onClick={() => setMoving(null)}>Cancel</button>
          </p>
        ) : null}
        {mergeFrom ? (
          <p className="rounded-2xl border border-primary/50 bg-primary/10 px-4 py-2.5 text-sm">
            Merge #{mergeFrom.number} into which order? Tap a table or tab.{" "}
            <button type="button" className="font-semibold underline" onClick={() => setMergeFrom(null)}>Cancel</button>
          </p>
        ) : null}

        {tablesOn && floor ? (
          <section aria-label="Floor plan">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap gap-1.5" role="group" aria-label="Floor">
                <button type="button" aria-pressed={areaId === "all"} onClick={() => setAreaId("all")}
                  className={`h-9 rounded-full px-4 text-sm font-semibold ${areaId === "all" ? "bg-primary text-white" : "bg-zinc-100 dark:bg-white/10"}`}>
                  All Tables
                </button>
                {floor.areas.map((item) => (
                  <button key={item.id} type="button" aria-pressed={item.id === areaId} onClick={() => setAreaId(item.id)}
                    className={`h-9 rounded-full px-4 text-sm font-semibold ${item.id === areaId ? "bg-primary text-white" : "bg-zinc-100 dark:bg-white/10"}`}>
                    {item.name}
                  </button>
                ))}
              </div>
              <div className="flex flex-wrap gap-1.5" aria-label="Table summary">
                <span className="rounded-full bg-zinc-100 px-3 py-1.5 text-xs font-semibold dark:bg-white/10">Total {visibleTables.length}</span>
                <span className="rounded-full bg-amber-500/15 px-3 py-1.5 text-xs font-semibold text-amber-800 dark:text-amber-200">Occupied {occupiedTables}</span>
                <span className="rounded-full bg-emerald-500/15 px-3 py-1.5 text-xs font-semibold text-emerald-800 dark:text-emerald-200">Available {visibleTables.length - occupiedTables}</span>
              </div>
              {floor.areas.length === 0 ? <p className="text-sm text-zinc-500">No dining areas yet. Add them in the portal under Inventory › Floor plan.</p> : null}
            </div>
            {visibleTables.length > 0 ? (
              <div className={`overflow-visible rounded-3xl border border-zinc-200 bg-zinc-950 dark:border-white/10 ${floorTableGridClass}`} aria-label="Floor plan tables">
                {visibleTables.map((table) => {
                  return (
                    <FloorTableCard
                      key={table.id}
                      tableId={table.id}
                      label={table.label}
                      seats={table.seats}
                      covers={table.covers}
                      seatedAt={table.seated_at}
                      openCents={table.open_cents}
                      currency={currency}
                      status={table.status}
                      selected={Boolean(selectedId && table.order_id === selectedId)}
                      disabled={busy}
                      onClick={() => {
                        const order = orders.find((item) => item.id === table.order_id);
                        if (moving) {
                          if (!order) {
                            const from = moving;
                            setMoving(null);
                            void write(() => ordersApi.move(from, userId, table.id), `#${from.number} moved to ${table.label}.`);
                          }
                          return;
                        }
                        if (mergeFrom) {
                          if (order && order.id !== mergeFrom.id) {
                            const from = mergeFrom;
                            setMergeFrom(null);
                            void write(() => ordersApi.merge(from, order, userId), `#${from.number} merged into ${table.label}.`);
                          }
                          return;
                        }
                        if (order) setSelectedId(order.id);
                        else setSeating(table);
                      }}
                    />
                  );
                })}
              </div>
            ) : null}
          </section>
        ) : null}

        <section aria-label="Open tabs">
          <h2 className="mb-2 text-sm font-semibold">{tablesOn ? "Tabs without a table" : "Open tabs"}</h2>
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {(tablesOn ? tabs : orders.filter((order) => order.channel_status !== "PENDING")).map((order) => {
              const phase = orderPhase(order);
              return (
              <button key={order.id} type="button" onClick={() => {
                if (mergeFrom) {
                  if (order.id !== mergeFrom.id) {
                    const from = mergeFrom;
                    setMergeFrom(null);
                    void write(() => ordersApi.merge(from, order, userId), `#${from.number} merged into #${order.number}.`);
                  }
                  return;
                }
                setSelectedId(order.id);
              }}
                className={`rounded-2xl border p-3 text-left ${order.id === selectedId ? "border-primary" : "border-zinc-200 dark:border-white/10"}`}>
                <span className="flex items-baseline justify-between gap-2">
                  <span className="font-semibold">{order.table_label ? `Table ${order.table_label}` : order.name || `#${order.number}`}</span>
                  <span className="text-sm font-bold tabular-nums">{formatMoney(order.open_cents, currency)}</span>
                </span>
                <span className="mt-1 block text-xs text-zinc-500 dark:text-white/50">
                  {order.service_type === "DELIVERY" ? `${order.channel_name ?? "Delivery"} ${order.external_ref ?? ""}` : order.service_type === "TAKEAWAY" ? "Takeaway" : "Dine-in"} · {order.items.filter((item) => !item.voided_at).length} lines · {minutesSince(order.opened_at)} min
                  {phase ? ` · ${ORDER_PROGRESS_LABEL[phase]}` : ""}
                </span>
              </button>
              );
            })}
            {(tablesOn ? tabs : orders.filter((order) => order.channel_status !== "PENDING")).length === 0 ? <p className="text-sm text-zinc-500 dark:text-white/50">No open tabs.</p> : null}
          </div>
        </section>
      </div>

      {quantityFor ? (
        <QuantityModal
          product={quantityFor}
          onClose={() => setQuantityFor(null)}
          onConfirm={(quantity) => {
            addDraft(quantityFor, [], [], quantity);
            return true;
          }}
        />
      ) : null}
      {modifierFor ? (
        <ModifierPickerModal product={modifierFor} groups={groupsFor(menu, modifierFor.id)} currency={currency}
          onClose={() => setModifierFor(null)}
          onConfirm={(choices, quantity) => {
            addDraft(modifierFor, choices, [], quantity);
            setModifierFor(null);
          }} />
      ) : null}
      {comboFor ? (
        <ComboBuilderModal product={comboFor} slots={combosFor(menu, comboFor.id)} currency={currency}
          onClose={() => setComboFor(null)}
          onConfirm={(components, quantity) => {
            addDraft(comboFor, [], components, quantity);
            setComboFor(null);
          }} />
      ) : null}

      {seating ? (
        <GuestCountModal
          table={seating}
          onClose={() => setSeating(null)}
          onConfirm={(covers) => {
            const table = seating;
            setSeating(null);
            void openTab("DINE_IN", table, covers);
          }}
        />
      ) : null}

      {keyingIn ? <KeyInDeliveryModal channels={channels} onClose={() => setKeyingIn(false)} onSubmit={(id, ref, name) => void keyIn(id, ref, name)} /> : null}

      {splitting && selected ? (
        <SplitChecksModal
          order={selected}
          currency={currency}
          onClose={() => setSplitting(false)}
          onPayCheck={(itemIds, label) => {
            setSplitting(false);
            pay(itemIds, label);
          }}
          onPayEqually={(guests) => {
            setSplitting(false);
            pay(unpaid.map((item) => item.id), `order #${selected.number}, ${guests} ways`, guests);
          }}
        />
      ) : null}

      {voiding && selected ? (
        voiding.item?.sent_at ? (
          <ManagerApprovalModal
            reasons={[`Void ${voiding.item.quantity} × ${voiding.item.product_name} already sent to the kitchen`]}
            subtitle="A manager allowed to void sent items must approve. Add the reason in the note."
            verify={(username, pin) => verifyManager(session, username, pin, Permission.PosVoidSentItem)}
            onClose={() => setVoiding(null)}
            onApproved={(approver, note) => {
              const item = voiding.item!;
              setVoiding(null);
              void write(() => ordersApi.voidItem(selected, item.id, userId, note || "Voided after sending", approver.id), "Line voided.");
            }}
          />
        ) : (
          <div className="modal-backdrop" role="presentation">
            <form className="modal-card max-w-sm space-y-3" onSubmit={(event) => {
              event.preventDefault();
              const item = voiding.item!;
              setVoiding(null);
              void write(() => ordersApi.voidItem(selected, item.id, userId, voiding.reason.trim() || "Removed before sending", null), "Line removed.");
            }}>
              <h2 className="text-lg font-semibold">Remove {voiding.item?.product_name}?</h2>
              <input autoFocus value={voiding.reason} onChange={(event) => setVoiding({ ...voiding, reason: event.target.value })} placeholder="Reason (optional)" className="modal-input" />
              <div className="flex justify-end gap-2">
                <button type="button" className="modal-cancel" onClick={() => setVoiding(null)}>Cancel</button>
                <button type="submit" className="modal-save">Remove</button>
              </div>
            </form>
          </div>
        )
      ) : null}
    </PageFrame>
  );
}
